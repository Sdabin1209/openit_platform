// identity-entry: platform 사람 인증 이미지(identity=Keycloak, identity-proxy=oauth2-proxy, identity-db 의 전 단계)의 진입점. 계약 입력(IdentityEnv·IdentityProxyEnv)만 받고
// Keycloak 의 KC_*·realm 가져오기 파일·--config-file, oauth2-proxy 의 OAUTH2_PROXY_* 는 여기서 만든다(구조 규칙 1·6: 배치가 제품 내부 설정을 쓰지 않는다).
// 비밀은 파일로만 받는다(D84): 값은 환경 변수·로그에 넣지 않고 0600 파일(tmpfs)로 제품에 넘긴다. 위반이면 종료 64.
// 사용: identity-entry keycloak | proxy
package main

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"net/url"
	"os"
	"strings"
	"syscall"

	"openit/platform/common/envcheck"
)

//go:embed realm.template.json
var realmTemplate []byte

const (
	holderClient = "OPENIT_GATEWAY_CLIENT_SECRET" // realm 템플릿의 자리표시(환경 변수 이름 모양: 설정에 값이 인라인되지 않게)
	holderAdmin  = "OPENIT_INITIAL_ADMIN_PASSWORD"
)

func die(code int, f string, a ...any) {
	fmt.Fprintf(os.Stderr, "identity-entry: "+f+"\n", a...)
	os.Exit(code)
}

func readSecret(path string) string {
	b, err := os.ReadFile(path)
	if err != nil {
		die(64, "비밀 파일을 읽지 못했다: %s", path)
	}
	v := strings.TrimRight(string(b), "\r\n")
	if v == "" {
		die(64, "비밀 파일이 비었다: %s", path)
	}
	return v
}

func publicURL(env map[string]string) string {
	u, err := url.Parse(env["IDENTITY_PUBLIC_URL"])
	if err != nil || u.Scheme != "https" || u.Host == "" || (u.Path != "" && u.Path != "/") {
		die(64, "IDENTITY_PUBLIC_URL 은 https://<호스트>[:포트] 이어야 한다")
	}
	return "https://" + u.Host
}

func keycloak() {
	env, bad := envcheck.Load("/etc/openit/schemas/IdentityEnv.schema.json")
	if len(bad) > 0 {
		die(64, "IdentityEnv 위반: %s", strings.Join(bad, "; "))
	}
	pub := publicURL(env)
	dbURL, err := url.Parse(readSecret(env["IDENTITY_DB_URL_FILE"]))
	if err != nil || dbURL.User == nil || dbURL.Host == "" || strings.TrimPrefix(dbURL.Path, "/") == "" {
		die(64, "IDENTITY_DB_URL_FILE 은 libpq URI(postgresql://<계정>:<암호>@<호스트>:<포트>/<DB>)여야 한다")
	}
	dbPass, _ := dbURL.User.Password()
	if dbPass == "" {
		die(64, "IDENTITY_DB_URL_FILE 에 암호가 없다")
	}
	// realm 가져오기 파일: 템플릿에 공개 주소·클라이언트 비밀·첫 관리자 암호를 채운다(realm·클라이언트·역할 그룹은 이미지가 정한다)
	var realm map[string]any
	if err := json.Unmarshal(realmTemplate, &realm); err != nil {
		die(70, "realm 템플릿이 깨졌다")
	}
	cl := realm["clients"].([]any)[0].(map[string]any)
	if cl["secret"] != holderClient {
		die(70, "realm 템플릿의 클라이언트 비밀 자리표시가 바뀌었다")
	}
	cl["secret"] = readSecret(env["IDENTITY_CLIENT_SECRET_FILE"])
	cl["redirectUris"] = []any{pub + "/oauth2/callback"}
	cl["attributes"].(map[string]any)["post.logout.redirect.uris"] = pub + "/"
	usr := realm["users"].([]any)[0].(map[string]any)
	cred := usr["credentials"].([]any)[0].(map[string]any)
	if cred["value"] != holderAdmin {
		die(70, "realm 템플릿의 첫 관리자 암호 자리표시가 바뀌었다")
	}
	cred["value"] = readSecret(env["IDENTITY_INITIAL_ADMIN_PASSWORD_FILE"])
	out, _ := json.MarshalIndent(realm, "", "  ")
	must(os.WriteFile("/opt/keycloak/data/import/openit-realm.json", out, 0o600), "realm 파일을 쓰지 못했다(/opt/keycloak/data/import 는 쓰기 가능 tmpfs 여야 한다)")
	// --config-file: 비밀은 환경 변수가 아니라 이 파일로(프로세스 환경에 값이 없다, D84)
	must(os.MkdirAll("/tmp/identity", 0o700), "임시 폴더를 만들지 못했다(/tmp 는 쓰기 가능 tmpfs 여야 한다)")
	conf := fmt.Sprintf("db-password=%s\nbootstrap-admin-password=%s\n", dbPass, readSecret(env["IDENTITY_ADMIN_PASSWORD_FILE"]))
	must(os.WriteFile("/tmp/identity/keycloak.conf", []byte(conf), 0o600), "설정 파일을 쓰지 못했다")
	port := dbURL.Port()
	if port == "" {
		port = "5432"
	}
	jdbc := fmt.Sprintf("jdbc:postgresql://%s:%s/%s?sslmode=verify-full&sslrootcert=%s", dbURL.Hostname(), port, strings.TrimPrefix(dbURL.Path, "/"), env["IDENTITY_ROOT_CA"])
	e := append(cleanEnv(),
		"KC_DB=postgres", "KC_DB_URL="+jdbc, "KC_DB_USERNAME="+dbURL.User.Username(),
		"KC_BOOTSTRAP_ADMIN_USERNAME=kcadmin",
		"KC_HTTP_HOST=127.0.0.1", "KC_HTTP_ENABLED=true", "KC_HTTP_RELATIVE_PATH=/auth", // 평문은 루프백만(R1.1): TLS 는 같은 pod 의 영역 게이트웨이가 끝낸다
		"KC_HOSTNAME="+pub+"/auth", "KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true", "KC_PROXY_HEADERS=xforwarded",
		"KC_HEALTH_ENABLED=true", "KC_CACHE=local", "KC_LOG=console")
	must(syscall.Exec("/opt/keycloak/bin/kc.sh", []string{"kc.sh", "--config-file=/tmp/identity/keycloak.conf", "start", "--optimized", "--import-realm"}, e), "kc.sh 를 실행하지 못했다")
}

func proxy() {
	env, bad := envcheck.Load("/etc/openit/schemas/IdentityProxyEnv.schema.json")
	if len(bad) > 0 {
		die(64, "IdentityProxyEnv 위반: %s", strings.Join(bad, "; "))
	}
	pub := publicURL(env)
	// 영역 밖(identity)으로 가는 모든 호출은 자기 영역 게이트웨이의 CONNECT 출구로 나간다(RUNTIME R1.8): 계약 CommonEnv.OPENIT_EGRESS_PROXY 는 loopback http:// 이어야 하고 없으면 시작하지 않는다.
	common, badc := envcheck.Load("/etc/openit/schemas/CommonEnv.schema.json")
	if len(badc) > 0 {
		die(64, "CommonEnv 위반: %s", strings.Join(badc, "; "))
	}
	egress := common["OPENIT_EGRESS_PROXY"]
	if egress == "" {
		die(64, "OPENIT_EGRESS_PROXY 가 없다: identity 로 가는 호출은 영역 게이트웨이의 CONNECT 출구로만 나간다(R1.8)")
	}
	// 비밀 값은 읽어 보지 않고 존재만 확인한다: oauth2-proxy 가 *_FILE 로 직접 읽는다(환경에 값이 없다). 줄바꿈 없는 값이어야 한다는 것은 deploy 가 만드는 쪽의 규칙이다
	for _, f := range []string{"IDENTITY_CLIENT_SECRET_FILE", "IDENTITY_COOKIE_SECRET_FILE"} {
		if _, err := os.Stat(env[f]); err != nil {
			die(64, "%s 가 가리키는 파일이 없다", f)
		}
	}
	issuer := pub + "/auth/realms/openit"
	e := append(cleanEnv(),
		"OAUTH2_PROXY_PROVIDER=oidc",            // keycloak-oidc 가 아니다: 그 공급자는 realm 역할을 role:<이름> 그룹으로 섞어 역할 헤더에 잡음이 들어간다(deploy 스모크가 잡았다)
		"OAUTH2_PROXY_CLIENT_ID=openit-gateway", // HumanAuthEndpoints.client_id
		"OAUTH2_PROXY_CLIENT_SECRET_FILE="+env["IDENTITY_CLIENT_SECRET_FILE"], "OAUTH2_PROXY_COOKIE_SECRET_FILE="+env["IDENTITY_COOKIE_SECRET_FILE"],
		"OAUTH2_PROXY_SKIP_OIDC_DISCOVERY=true", // 발급자(iss)는 밖에 보이는 주소이고 서버끼리는 서비스 이름(identity)으로 부른다
		"OAUTH2_PROXY_OIDC_ISSUER_URL="+issuer, "OAUTH2_PROXY_LOGIN_URL="+issuer+"/protocol/openid-connect/auth",
		"OAUTH2_PROXY_REDEEM_URL=https://identity/auth/realms/openit/protocol/openid-connect/token",
		"OAUTH2_PROXY_OIDC_JWKS_URL=https://identity/auth/realms/openit/protocol/openid-connect/certs",
		"OAUTH2_PROXY_REDIRECT_URL="+pub+"/oauth2/callback", "OAUTH2_PROXY_PROVIDER_CA_FILES="+env["IDENTITY_ROOT_CA"], "SSL_CERT_FILE="+env["IDENTITY_ROOT_CA"],
		"OAUTH2_PROXY_HTTP_ADDRESS=127.0.0.1:4180", // 평문은 루프백만(R1.1)
		"OAUTH2_PROXY_UPSTREAMS=static://202", "OAUTH2_PROXY_REVERSE_PROXY=true", "OAUTH2_PROXY_SET_XAUTHREQUEST=true",
		"OAUTH2_PROXY_OIDC_GROUPS_CLAIM=groups", "OAUTH2_PROXY_EMAIL_DOMAINS=*",
		"OAUTH2_PROXY_INSECURE_OIDC_ALLOW_UNVERIFIED_EMAIL=true", // 이메일 발송 설정이 없어 가입 이메일을 검증하지 않는다(가입 승인은 admin 이 한다)
		"OAUTH2_PROXY_SCOPE=openid profile email", "OAUTH2_PROXY_CODE_CHALLENGE_METHOD=S256",
		"OAUTH2_PROXY_COOKIE_NAME=_openit_session", "OAUTH2_PROXY_COOKIE_SECURE=true", "OAUTH2_PROXY_COOKIE_SAMESITE=lax",
		"OAUTH2_PROXY_COOKIE_EXPIRE="+env["IDENTITY_SESSION_MAX"], "OAUTH2_PROXY_COOKIE_REFRESH="+env["IDENTITY_SESSION_REFRESH"],
		"OAUTH2_PROXY_SKIP_PROVIDER_BUTTON=true", "OAUTH2_PROXY_AUTH_LOGGING=true",
		// Go 표준 net/http 의 프록시 환경 변수(ProxyFromEnvironment): https 호출(토큰 교환·키 조회)은 출구로, loopback 상류(4180 등)는 프록시를 거치지 않는다
		"HTTPS_PROXY="+egress, "NO_PROXY=127.0.0.1,localhost,::1")
	must(syscall.Exec("/bin/oauth2-proxy", []string{"oauth2-proxy"}, e), "oauth2-proxy 를 실행하지 못했다")
}

func must(err error, msg string) {
	if err != nil {
		die(70, "%s: %v", msg, err)
	}
}

// cleanEnv: 현재 환경에서 IDENTITY_ 입력 이름을 뺀다(제품에 넘길 필요가 없다).
func cleanEnv() []string {
	var out []string
	for _, kv := range os.Environ() {
		if !strings.HasPrefix(kv, "IDENTITY_") && !strings.HasPrefix(kv, "OPENIT_EGRESS_PROXY=") {
			out = append(out, kv)
		}
	}
	return out
}

func main() {
	if len(os.Args) < 2 {
		die(64, "사용: identity-entry keycloak|proxy")
	}
	switch os.Args[1] {
	case "keycloak":
		keycloak()
	case "proxy":
		proxy()
	default:
		die(64, "알 수 없는 부명령: %s", os.Args[1])
	}
}
