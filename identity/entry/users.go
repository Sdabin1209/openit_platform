package main

// 사용자 등록 잡(계약 IdentityUsersConfig, JobsDeclaration 의 잡 register-users): realm openit 에 사용자와 역할 그룹을 만들고, 이미 있으면 같은 상태로 맞춘다(멱등, D39).
// deploy 는 Keycloak 의 도구·경로·관리 계정을 모른다: 이 잡이 identity 서비스(https://identity, 영역 안 통신)의 관리 REST API(Keycloak 표준)를 부른다.
// 암호는 password_file 에서(D84), 값은 어떤 출력에도 쓰지 않는다. 종료 코드: 0 성공, 75 identity 에 닿지 못함(재시도 가능), 1 그 밖의 실패, 64 입력 위반.

import (
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strings"
	"time"
)

type userSpec struct {
	Username     string   `json:"username"`
	Email        string   `json:"email"`
	Groups       []string `json:"groups"`
	PasswordFile string   `json:"password_file"`
	Enabled      *bool    `json:"enabled"`
}

type kc struct {
	base  string
	token string
	hc    *http.Client
}

type unreachable struct{ err error }

func (u unreachable) Error() string { return "identity 에 닿지 못했다" }

func (k *kc) do(method, path string, body any, want ...int) ([]byte, http.Header, error) {
	var rd io.Reader
	ctype := ""
	switch b := body.(type) {
	case nil:
	case url.Values:
		rd, ctype = strings.NewReader(b.Encode()), "application/x-www-form-urlencoded"
	default:
		j, _ := json.Marshal(b)
		rd, ctype = bytes.NewReader(j), "application/json"
	}
	req, _ := http.NewRequest(method, k.base+path, rd)
	if ctype != "" {
		req.Header.Set("Content-Type", ctype)
	}
	if k.token != "" {
		req.Header.Set("Authorization", "Bearer "+k.token)
	}
	resp, err := k.hc.Do(req)
	if err != nil {
		return nil, nil, unreachable{err}
	}
	defer resp.Body.Close()
	out, _ := io.ReadAll(resp.Body)
	for _, w := range want {
		if resp.StatusCode == w {
			return out, resp.Header, nil
		}
	}
	return nil, nil, fmt.Errorf("%s %s -> %d", method, strings.SplitN(path, "?", 2)[0], resp.StatusCode)
}

func usersJob(args []string) {
	if len(args) != 1 {
		die(64, "사용: identity-entry users <설정 파일>")
	}
	raw, err := os.ReadFile(args[0])
	if err != nil {
		die(64, "설정 파일을 읽지 못했다: %s", args[0])
	}
	var cfg struct {
		Users []userSpec `json:"users"`
	}
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&cfg); err != nil || len(cfg.Users) == 0 {
		die(64, "설정 파일이 IdentityUsersConfig 모양이 아니다")
	}
	nameRE, abs := regexp.MustCompile(`^[a-z0-9][a-z0-9._-]{1,62}$`), regexp.MustCompile(`^/`)
	for _, u := range cfg.Users {
		if !nameRE.MatchString(u.Username) || !abs.MatchString(u.PasswordFile) {
			die(64, "사용자 항목이 IdentityUsersConfig 를 어겼다(username·password_file)")
		}
	}
	// 입력은 label 의 secret_files/env 로 deploy 가 준 것만 쓴다(IdentityEnv 의 이름)
	caPath, adminFile := os.Getenv("IDENTITY_ROOT_CA"), os.Getenv("IDENTITY_ADMIN_PASSWORD_FILE")
	if caPath == "" || adminFile == "" {
		die(64, "IDENTITY_ROOT_CA, IDENTITY_ADMIN_PASSWORD_FILE 이 필요하다")
	}
	pool := x509.NewCertPool()
	pem, err := os.ReadFile(caPath)
	if err != nil || !pool.AppendCertsFromPEM(pem) {
		die(64, "루트 인증서를 읽지 못했다")
	}
	k := &kc{base: "https://identity", hc: &http.Client{Timeout: 30 * time.Second, Transport: &http.Transport{TLSClientConfig: &tls.Config{RootCAs: pool}}}}
	fail := func(err error) {
		if _, ok := err.(unreachable); ok {
			die(75, "%v", err)
		}
		die(1, "%v", err)
	}
	// 관리 토큰: master realm 의 부트스트랩 관리자(IDENTITY_ADMIN_PASSWORD_FILE)
	body, _, err := k.do("POST", "/auth/realms/master/protocol/openid-connect/token", url.Values{"grant_type": {"password"}, "client_id": {"admin-cli"}, "username": {"kcadmin"}, "password": {readSecret(adminFile)}}, 200)
	if err != nil {
		fail(err)
	}
	var tok struct {
		AccessToken string `json:"access_token"`
	}
	json.Unmarshal(body, &tok)
	k.token = tok.AccessToken
	// 그룹 이름 -> id
	body, _, err = k.do("GET", "/auth/admin/realms/openit/groups?max=200", nil, 200)
	if err != nil {
		fail(err)
	}
	var gl []struct{ ID, Name string }
	json.Unmarshal(body, &gl)
	gid := map[string]string{}
	for _, g := range gl {
		gid[g.Name] = g.ID
	}
	created, updated := 0, 0
	for _, u := range cfg.Users {
		// Keycloak 26 의 기본 사용자 프로필은 이메일·이름이 비면 첫 로그인에서 "프로필 갱신" 단계를 요구한다: 설정에 없는 값은 사용자 이름에서 채워 로그인이 곧바로 된다
		email := u.Email
		if email == "" {
			email = u.Username + "@users.invalid"
		}
		rep := map[string]any{"username": u.Username, "enabled": true, "emailVerified": true, "email": email, "firstName": "OpenIt", "lastName": u.Username, "requiredActions": []string{}}
		body, _, err := k.do("GET", "/auth/admin/realms/openit/users?exact=true&username="+url.QueryEscape(u.Username), nil, 200)
		if err != nil {
			fail(err)
		}
		var found []struct{ ID string }
		json.Unmarshal(body, &found)
		id := ""
		if len(found) == 0 {
			_, h, err := k.do("POST", "/auth/admin/realms/openit/users", rep, 201)
			if err != nil {
				fail(err)
			}
			id = h.Get("Location")[strings.LastIndex(h.Get("Location"), "/")+1:]
			created++
		} else {
			id = found[0].ID
			if _, _, err := k.do("PUT", "/auth/admin/realms/openit/users/"+id, rep, 204); err != nil {
				fail(err)
			}
			updated++
		}
		if _, _, err := k.do("PUT", "/auth/admin/realms/openit/users/"+id+"/reset-password", map[string]any{"type": "password", "value": readSecret(u.PasswordFile), "temporary": false}, 204); err != nil {
			fail(err)
		}
		// 역할 그룹을 원하는 집합과 같게: enabled=false 는 승인 대기(그룹 없음, 로그인은 되고 모든 사람 경로는 403 ACCOUNT_PENDING_APPROVAL)
		want := map[string]bool{}
		if u.Enabled == nil || *u.Enabled {
			for _, g := range u.Groups {
				want[g] = true
			}
		}
		body, _, err = k.do("GET", "/auth/admin/realms/openit/users/"+id+"/groups", nil, 200)
		if err != nil {
			fail(err)
		}
		var cur []struct{ ID, Name string }
		json.Unmarshal(body, &cur)
		have := map[string]bool{}
		for _, g := range cur {
			have[g.Name] = true
			if !want[g.Name] {
				if _, _, err := k.do("DELETE", "/auth/admin/realms/openit/users/"+id+"/groups/"+g.ID, nil, 204); err != nil {
					fail(err)
				}
			}
		}
		for g := range want {
			if have[g] {
				continue
			}
			if gid[g] == "" {
				die(1, "realm 에 없는 역할 그룹: %s", g)
			}
			if _, _, err := k.do("PUT", "/auth/admin/realms/openit/users/"+id+"/groups/"+gid[g], nil, 204); err != nil {
				fail(err)
			}
		}
	}
	fmt.Printf("identity-users: 사용자 %d명 맞춤(새로 %d, 기존 %d)\n", len(cfg.Users), created, updated)
}
