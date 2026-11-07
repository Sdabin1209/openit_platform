#!/usr/bin/env bash
# 사람 인증을 진짜 Keycloak + oauth2-proxy + platform 공개 입구로 확인하는 스모크 시험(U82, head ADR 0014). 사용: bash identity/tests/test-idp-smoke.sh
# identity/compose.dev.yaml 로 keycloak-db, keycloak, oauth2-proxy 와 두 서비스의 영역 게이트웨이(TLS), 공개 입구만 띄운다. 이웃 영역 없음: 인증을 통과한 요청은 상류 부재로 503/504 가 된다. 끝나면 지운다.
# 이미지는 지금 이 리포에서 빌드한다(영역 게이트웨이, 공개 입구, Keycloak optimized). 값(암호·토큰)은 출력하지 않는다. 실패하면 로그를 $KEEP_DIR 에 남긴다.
set -uo pipefail
source "$(dirname "$0")/../../scripts/lib.sh"
ID=$$; P=platform-idp-$ID; W=$(mktemp -d); export SECRETS_DIR=$W/secrets IDP_SECRETS=$W/idp PKI_DIR=$W/pki
cd "$ROOT"; set -a; source locks/images.lock; set +a
FAILS=0; N=0
ok() { N=$((N+1)); local n=$1; shift; if out=$("$@" 2>&1); then echo "  PASS $n"; else echo "  FAIL $n :: $(echo "$out" | tail -2 | tr '\n' ' ' | cut -c1-220)"; FAILS=$((FAILS+1)); fi; }
dcp() { "$DOCKER" compose -p "$P" -f "$ROOT/identity/compose.dev.yaml" "$@"; }
cleanup() {
  if [ "$FAILS" != 0 ] || [ "${KEEP:-0}" = 1 ]; then mkdir -p "${KEEP_DIR:-$ROOT/build/logs/idp-$ID}"; for s in identity identity-gw identity-proxy identity-proxy-gw gateway identity-db; do dcp logs --no-color "$s" > "${KEEP_DIR:-$ROOT/build/logs/idp-$ID}/$s.log" 2>&1; done; echo "로그를 남겼다: ${KEEP_DIR:-$ROOT/build/logs/idp-$ID}"; fi
  dcp down -v --remove-orphans >/dev/null 2>&1
  "$DOCKER" rmi "$GW_IMG" "$ING_IMG" "$IDP_IMG" "$PRX_IMG" "$DB_IMG" >/dev/null 2>&1; rm -rf "$W"
}
trap cleanup EXIT
# 공개 URL(발급자·콜백)에 포트가 들어가 기동 전에 정해야 한다: Docker 배정은 쓸 수 없고, 고른 포트를 Docker 로 실제 게시해 본 것만 쓴다
# (빈 포트라도 Windows 예약 범위면 Docker 가 못 연다, 2026-11-07 교차검증). 확인 이미지는 이 리포가 digest 로 고정한 PostgreSQL 기반 이미지
PROBE_IMG=$(sed -n 's/^ARG POSTGRES_IMAGE=//p' "$ROOT/identity/Dockerfile.db" | head -1); PORT=""
for _t in 1 2 3 4 5 6 7 8; do _p=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')
  "$DOCKER" run --rm -p "127.0.0.1:$_p:1" --entrypoint true "$PROBE_IMG" >/dev/null 2>&1 && { PORT=$_p; break; }
done
[ -n "$PORT" ] || { echo "Docker 가 게시할 수 있는 빈 포트를 찾지 못했다" >&2; exit 1; }
export SECRETS_GID
export PUBLIC_PORT=$PORT PUBLIC_URL=https://localhost:$PORT GATEWAY_HOSTS="localhost:8443"
export IDENTITY_DIR=$ROOT/identity EXPOSURES_DIR=$ROOT/ingress/tests/exposures
GW_IMG=platform-area-gateway:idp-$ID; ING_IMG=platform-ingress:idp-$ID; IDP_IMG=platform-identity:idp-$ID; PRX_IMG=platform-identity-proxy:idp-$ID; DB_IMG=platform-identity-db:idp-$ID
export AREA_GATEWAY_IMAGE=$GW_IMG INGRESS_IMAGE=$ING_IMG IDENTITY_IMAGE=$IDP_IMG IDENTITY_PROXY_IMAGE=$PRX_IMG IDENTITY_DB_IMAGE=$DB_IMG
echo "== 준비 (비밀·PKI·이미지)"
bash ingress/scripts/gen-test-secrets.sh "$SECRETS_DIR" >/dev/null 2>&1 || { echo "시험 비밀을 만들지 못했다"; exit 1; }
bash identity/scripts/gen-idp-secrets.sh "$IDP_SECRETS" || exit 1
bash identity/scripts/gen-test-pki.sh "$PKI_DIR" || exit 1
DEVICE_PKI_DIR=$W/dpki bash ingress/scripts/device-pki.sh init >/dev/null 2>&1 || exit 1; export DEVICE_CA=$W/dpki/ca.crt   # 기기 CA(필수 입력)
BSRC=$(bash scripts/fetch-boundary-src.sh "$W/boundary-src") || exit 1
BV=$("$PY" -c 'import importlib.metadata as m;print(m.version("boundary-contracts"))')
for v in "|$GW_IMG" "public-ingress|$ING_IMG" "identity|$IDP_IMG" "identity-proxy|$PRX_IMG" "identity-db|$DB_IMG"; do
  var=""; [ -n "${v%%|*}" ] && var=",\"variant\":\"${v%%|*}\""   # 영역 게이트웨이는 variant 없음
  printf '{"source_dir":"%s","revision":"abcdef1","versions":{"boundary":"v%s"}%s,"dependency_sources":{"boundary":"%s"},"image_tag":"%s"}' "$ROOT" "$BV" "$var" "$BSRC" "${v##*|}" > "$W/req.json"
  bash scripts/build-image.sh "$W/req.json" >/dev/null 2>"$W/build.err" || { tail -3 "$W/build.err"; echo "이미지를 만들지 못했다: ${v##*|}"; exit 1; }
done
echo "== 기동 (identity-db -> identity -> identity-proxy -> 공개 입구)"
dcp up -d --wait --wait-timeout 300 identity identity-gw >"$W/up1.log" 2>&1; ok "identity(Keycloak) healthy (realm openit 가져오기 포함)" test "$(dcp ps -q identity | xargs -r $DOCKER inspect --format '{{.State.Health.Status}}')" = healthy
dcp up -d --wait --wait-timeout 120 identity-proxy identity-proxy-gw gateway >"$W/up2.log" 2>&1; ok "공개 입구가 응답한다(/healthz)" bash -c "for i in \$(seq 1 30); do curl -sk -m 3 --resolve localhost:$PORT:127.0.0.1 -o /dev/null -w '%{http_code}' https://localhost:$PORT/healthz | grep -q 200 && exit 0; sleep 1; done; exit 1"   # 준비 확인: 응답이 올 때까지(재시도 덧붙임이 아니라 기동 대기)
KCC=$(dcp ps -q identity)
ok "identity 프로세스 환경에 비밀 값이 없다(파일만, D84)" bash -c "! docker exec $KCC cat /proc/1/environ | tr '\0' '\n' | grep -qF \"\$(cat $IDP_SECRETS/db-identity)\" && ! docker exec $KCC cat /proc/1/environ | tr '\0' '\n' | grep -qF \"\$(cat $IDP_SECRETS/identity-client-secret)\""
# 사용자 등록 잡(라벨 io.openit.jobs 의 register-users, 계약 IdentityUsersConfig): deploy 가 하는 그대로 라벨의 argv·config 경로·비밀 파일로 돌린다. 시험이 Keycloak 도구를 쓰지 않는다.
JOBARGV=$("$DOCKER" image inspect "$IDP_IMG" --format '{{index .Config.Labels "io.openit.jobs"}}' | python3 -c 'import json,sys;j=json.load(sys.stdin)["jobs"][0];print("\n".join(j["argv"]))')
JOBCFG=$("$DOCKER" image inspect "$IDP_IMG" --format '{{index .Config.Labels "io.openit.jobs"}}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["jobs"][0]["config"]["container_path"])')
cat > "$W/usersjob.sh" <<JOB
#!/usr/bin/env bash
# usersjob.sh <설정 JSON> [관리자 암호 파일]: 라벨이 선언한 잡을 deploy 가 연결하는 것(설정 파일, 비밀 파일, 루트 인증서, identity 가 있는 네트워크)과 함께 돌린다
mapfile -t A < <(printf '%s' '$JOBARGV')
exec $DOCKER run --rm --network ${P}_auth --user 1000:1000 --group-add $SECRETS_GID --read-only --tmpfs /tmp -v $PKI_DIR/root_ca.crt:/ca.pem:ro -v "\${2:-$IDP_SECRETS/identity-admin-password}":/run/secrets/adminpw:ro \\
  -v $SECRETS_DIR/tokens:/pw:ro -v $W:/wk:ro -v "\$1":$JOBCFG:ro -e IDENTITY_ROOT_CA=/ca.pem -e IDENTITY_ADMIN_PASSWORD_FILE=/run/secrets/adminpw $IDP_IMG "\${A[@]}"   # deploy 와 같다: 진입점은 그대로 두고 잡 argv 전체를 command 로 준다(CONVENTIONS 13절)
JOB
chmod +x "$W/usersjob.sh"; export USERSJOB=$W/usersjob.sh
python3 - "$ROOT/ingress/tests/gateway-oidc/accounts.test.conf" "$W/users.json" <<'PY'
import json, sys
users = []
for line in open(sys.argv[1]):
    f = line.split()
    if not f or f[0].startswith("#"): continue
    users.append({"username": f[0], "groups": [] if f[1] == "-" else f[1].split(","), "password_file": f"/pw/idp-test-{f[0]}-password"})
json.dump({"users": users}, open(sys.argv[2], "w"))
PY
chmod 644 "$W/users.json"
ok "사용자 등록 잡이 시험 사용자를 만든다(라벨의 argv·config 경로 그대로)" bash "$USERSJOB" "$W/users.json"
ok "멱등: 같은 설정으로 다시 돌려도 성공한다" bash "$USERSJOB" "$W/users.json"
ok "변이: 관리자 암호가 틀리면 잡이 실패한다" bash -c '! bash "$1" "$2" "$3" >/dev/null 2>&1' _ "$USERSJOB" "$W/users.json" "$IDP_SECRETS/db-identity"
"$DOCKER" exec "$KCC" /opt/keycloak/bin/kcadm.sh config credentials --server http://127.0.0.1:8080/auth --realm master --user kcadmin --password "$(cat "$IDP_SECRETS/identity-admin-password")" --config /tmp/kcadm.config >/dev/null 2>&1   # 시험의 확인용(이벤트 조회)
python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));d["users"]=[{"username":"reconcile-e2e","groups":["staff","clinician"],"password_file":"/pw/idp-test-staff-e2e-password"}];json.dump(d,open(sys.argv[2],"w"))' "$W/users.json" "$W/rec1.json"
python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));d["users"][0]["groups"]=["staff"];json.dump(d,open(sys.argv[2],"w"))' "$W/rec1.json" "$W/rec2.json"
chmod 644 "$W"/rec*.json; bash "$USERSJOB" "$W/rec1.json" >/dev/null 2>&1; bash "$USERSJOB" "$W/rec2.json" >/dev/null 2>&1
ok "상태를 맞춘다: 그룹을 줄인 설정으로 다시 돌리면 남은 그룹이 staff 뿐이다" bash -c 'u=$($0 exec -i $1 /opt/keycloak/bin/kcadm.sh get users -r openit -q username=reconcile-e2e --fields id --format csv --noquotes --config /tmp/kcadm.config | tr -d "\r\n"); g=$($0 exec -i $1 /opt/keycloak/bin/kcadm.sh get users/$u/groups -r openit --fields name --format csv --noquotes --config /tmp/kcadm.config | tr -d "\r" | sort | tr "\n" ","); [ "$g" = "staff," ]' "$DOCKER" "$KCC"
echo "== 로그인·역할 (공개 입구 경유)"
export W PORT KCC USERSJOB; PYTHONPATH=identity/tests "$PY" -I -W ignore - <<'PY' || FAILS=$((FAILS+1))
import json, os, sys, subprocess, urllib.parse
sys.path.insert(0, "identity/tests")
from idp_client import Client
W, PORT = os.environ["W"], os.environ["PORT"]; S = os.environ["SECRETS_DIR"]
base = f"https://localhost:{PORT}"
c = Client(base, os.environ["PKI_DIR"] + "/root_ca.crt")
fails = 0
def chk(name, cond, detail=""):
    global fails
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else f" :: {detail}")); fails += 0 if cond else 1
def pw(u): return open(f"{S}/tokens/idp-test-{u}-password").read().strip()
def req(user, method, path, **kw):
    jar = sessions[user]; return c.raw(method, path, jar=jar, **kw)
st, h, b = c.raw("GET", "/v1/staff/alerts"); chk("인증 없는 API 는 401 + Bearer realm", st == 401 and h.get("www-authenticate", "").startswith('Bearer realm="openit"'), (st, h.get("www-authenticate")))
st, h, b = c.raw("GET", "/staff/", headers={"Accept": "text/html"}); chk("인증 없는 화면(html)은 로그인으로 302", st == 302 and h.get("location", "").startswith("/oauth2/start"), (st, h.get("location")))
sessions = {}
for u in ("staff-e2e", "operator-e2e", "multi-e2e", "clinician-e2e", "pending-e2e"):
    sessions[u] = c.login(u, pw(u)); chk(f"{u} 로그인으로 세션 쿠키를 얻는다", bool(sessions[u]))
st, h, b = req("staff-e2e", "GET", "/v1/staff/alerts"); chk("staff 로그인 -> 직원 API 통과(상류 없음 502/503/504)", st in (502, 503, 504), st)
st, h, b = req("staff-e2e", "POST", "/v1/activate", data=b"{}", headers={"Origin": base, "Content-Type": "application/json"}); chk("staff -> operator 경로 403", st == 403, st)
st, h, b = req("operator-e2e", "POST", "/v1/activate", data=b"{}", headers={"Origin": base, "Content-Type": "application/json"}); chk("operator -> 활성화 통과", st in (502, 503, 504), st)
st, h, b = req("multi-e2e", "GET", "/v1/cases"); chk("한 사람이 역할 둘(reviewer, clinician): reviewer 경로 통과", st in (502, 503, 504), st)
st, h, b = req("multi-e2e", "GET", "/v1/results"); chk("같은 사람: clinician 경로도 통과", st in (502, 503, 504), st)
st, h, b = req("clinician-e2e", "GET", "/v1/staff/alerts"); chk("clinician -> 직원 API 403", st == 403, st)
st, h, b = req("clinician-e2e", "GET", "/v1/staff/push-config"); chk("clinician -> 푸시 설정 통과", st in (502, 503, 504), st)
st, h, b = req("pending-e2e", "GET", "/v1/staff/alerts"); chk("승인 대기(그룹 없음) -> 403 ACCOUNT_PENDING_APPROVAL", st == 403 and b"ACCOUNT_PENDING_APPROVAL" in b, (st, b[:100]))
st, h, b = req("multi-e2e", "GET", "/oauth2/userinfo"); ui = json.loads(b) if st == 200 else {}
chk("/oauth2/userinfo: 사용자 이름과 그룹 목록", st == 200 and ui.get("preferredUsername") == "multi-e2e" and sorted(ui.get("groups", [])) == ["clinician", "reviewer"], (st, ui))
st, h, b = c.raw("GET", "/auth/realms/openit/.well-known/openid-configuration"); cfg = json.loads(b) if st == 200 else {}
chk("Keycloak discovery 의 발급자는 밖에 보이는 주소", cfg.get("issuer") == base + "/auth/realms/openit", cfg.get("issuer"))
st, h, b = c.raw("GET", "/auth/realms/master/.well-known/openid-configuration"); chk("master realm 은 밖에 닫혀 있다(404)", st == 404, st)
rd = "/auth/realms/openit/protocol/openid-connect/logout?client_id=openit-gateway&post_logout_redirect_uri=" + urllib.parse.quote(base + "/", safe="")
st, h, b = req("staff-e2e", "GET", "/oauth2/sign_out?rd=" + urllib.parse.quote(rd, safe="")); chk("/oauth2/sign_out?rd=<Keycloak 로그아웃> 이 막히지 않는다", st in (302, 303) and "/openid-connect/logout" in h.get("location", ""), (st, h.get("location")))
newpw = "Newuser-pw-" + os.urandom(6).hex()
jar, why = c.register("newbie-e2e", newpw); chk("가입 신청(자가 등록)이 되고 바로 로그인된다", bool(jar), why)
sessions["newbie-e2e"] = jar
st, h, b = req("newbie-e2e", "GET", "/v1/staff/alerts") if jar else (0, {}, b""); chk("가입 직후(그룹 없음)는 403 ACCOUNT_PENDING_APPROVAL", st == 403 and b"ACCOUNT_PENDING_APPROVAL" in b, (st, b[:80]))
def kcadm(*a):
    r = subprocess.run(["docker", "exec", "-i", os.environ["KCC"], "/opt/keycloak/bin/kcadm.sh", *a, "--config", "/tmp/kcadm.config"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout
open(os.environ["W"] + "/newpw", "w").write(newpw); os.chmod(os.environ["W"] + "/newpw", 0o644)
json.dump({"users": [{"username": "newbie-e2e", "groups": ["staff"], "password_file": "/wk/newpw"}]}, open(os.environ["W"] + "/approve.json", "w")); os.chmod(os.environ["W"] + "/approve.json", 0o644)
rc = subprocess.run(["bash", os.environ["USERSJOB"], os.environ["W"] + "/approve.json"], capture_output=True).returncode
chk("admin 이 staff 그룹을 부여한다(승인 = 사용자 등록 잡을 groups:[staff] 로 다시 돌림)", rc == 0)
sessions["newbie-e2e"] = c.login("newbie-e2e", newpw)
st, h, b = req("newbie-e2e", "GET", "/v1/staff/alerts"); chk("승인 뒤 다시 로그인하면 직원 API 가 통과한다", st in (502, 503, 504), (st, b[:80]))
rc, out = kcadm("get", "events", "-r", "openit", "-q", "type=LOGIN", "-q", "max=5"); chk("로그인 이벤트가 기록된다", rc == 0 and '"type" : "LOGIN"' in out, out[:120])
rc, out = kcadm("get", "realms/openit", "--fields", "eventsExpiration"); chk("로그인 기록 보존 365일(31536000초)", "31536000" in out, out)
print(f"  Python 확인 {fails} 건 실패"); sys.exit(1 if fails else 0)
PY
echo "== 이미지 HEALTHCHECK (identity, identity-proxy, identity-db, 영역 게이트웨이, 공개 입구)"
hstat() { "$DOCKER" inspect -f '{{.State.Health.Status}}' "$(dcp ps -q "$1")" 2>/dev/null; }
hwait() { local want=$2 i; for i in $(seq 1 60); do [ "$(hstat "$1")" = "$want" ] && return 0; sleep 3; done; return 1; }   # 준비 확인: 건강 확인 자체가 신호다
for svc in identity identity-proxy identity-db identity-gw identity-proxy-gw gateway; do ok "$svc: 이미지 HEALTHCHECK 가 healthy" hwait $svc healthy; done
"$DOCKER" pause "$(dcp ps -q identity-proxy)" >/dev/null; "$DOCKER" pause "$(dcp ps -q gateway)" >/dev/null
ok "변이: identity-proxy 가 응답하지 않으면 unhealthy" hwait identity-proxy unhealthy
ok "변이: 공개 입구가 응답하지 않으면 unhealthy" hwait gateway unhealthy
"$DOCKER" unpause "$(dcp ps -q identity-proxy)" >/dev/null; "$DOCKER" unpause "$(dcp ps -q gateway)" >/dev/null
for svc in identity-proxy gateway; do ok "$svc: 되살리면 다시 healthy" hwait $svc healthy; done
echo "== 출구 경유 (RUNTIME R1.8: identity-proxy 가 identity 를 부르는 호출은 영역 게이트웨이의 CONNECT 출구로만 나간다)"
STAFFPW="$SECRETS_DIR/tokens/idp-test-staff-e2e-password"
lc() { "$PY" -I -W ignore identity/tests/login_check.py "$PORT" "$PKI_DIR/root_ca.crt" staff-e2e "$STAFFPW"; }
python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));d["egress"]=[];json.dump(d,open(sys.argv[2],"w"))' identity/exposure-identity-proxy.json "$W/proxy-noegress.json"
ok "기준: 출구가 identity 를 허용하면 로그인이 된다" test "$(lc)" = OK
PROXY_EXPOSURE=$W/proxy-noegress.json dcp up -d --force-recreate identity-proxy-gw >/dev/null 2>&1
ok "변이: 출구가 identity 를 허용하지 않으면(egress 선언 비움 -> CONNECT 403) 같은 로그인이 실패한다 = 호출이 출구를 거친다" test "$(lc)" = FAIL
dcp up -d --force-recreate identity-proxy-gw >/dev/null 2>&1
ok "복구: 선언을 되돌리면 로그인이 다시 된다" test "$(lc)" = OK
echo; [ $FAILS = 0 ] && echo "통과: IdP 스모크 시험" || { echo "실패: $FAILS건"; exit 1; }
