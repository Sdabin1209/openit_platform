#!/usr/bin/env bash
# 키오스크 기기 인증서(mTLS) 공개 입구 시험(PUBLIC_API F절 기본 기기 인증, ADR 0040, Docker·openssl 필요). 사용: bash ingress/tests/test-device-mtls.sh   (일회용 CA·임시 네트워크, 끝나면 모두 지운다)
# 지금 빌드한 공개 입구 이미지로: 기본(검증 꺼짐)과 켜짐 설정 검증, 신뢰 CA 의 인증서로 키오스크 경로 통과 + CN 이 X-Openit-Device 로 전달, 위조 헤더 덮어쓰기, 인증서 없으면 401(+Bearer), 다른 CA 인증서는 TLS 에서 거부,
# 직원 경로는 인증서 없이 계정 인증, 기기 토큰 경로(INGRESS_DEVICE_TOKENS_DIR 의 기기별 파일)에서도 위조 헤더가 지워진다. 키 값은 출력하지 않는다.
# 변이: MTLS_MUTATE=1 이면 검증을 끈 기본 조각으로 띄운다 -> 인증서 단언들이 실패해야 한다.
set -uo pipefail
source "$(dirname "$0")/../../scripts/lib.sh"; source "$ROOT/ingress/tests/stack-lib.sh"
command -v openssl >/dev/null || { echo "openssl 이 필요하다"; exit 1; }
stack_init devmtls survey-service
N=0; F=0
trap 'stack_cleanup $F' EXIT
pass() { N=$((N+1)); echo "  PASS $1"; }; fail() { N=$((N+1)); F=$((F+1)); echo "  FAIL $1"; }
DP=$T/dpki; export DEVICE_PKI_DIR=$DP
bash "$ROOT/ingress/scripts/device-pki.sh" init >/dev/null 2>&1 && bash "$ROOT/ingress/scripts/device-pki.sh" issue kiosk-lobby-1 >/dev/null 2>&1 && pass "일회용 CA·기기 인증서 발급(openssl)" || fail "device-pki 발급"
[ "$(stat -c %a "$DP")" = 700 ] && [ "$(stat -c %a "$DP/ca.key")" = 600 ] && [ "$(stat -c %a "$DP/kiosk-lobby-1.key")" = 600 ] && pass "폴더 700, 키 파일 600" || fail "키 파일 권한"
bash "$ROOT/ingress/scripts/device-pki.sh" issue 'bad id' >/dev/null 2>&1 && fail "형식에 안 맞는 기기 ID 를 발급했다" || pass "기기 ID 형식(^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$)에 안 맞으면 발급 거부"
openssl verify -CAfile "$DP/ca.crt" "$DP/kiosk-lobby-1.crt" >/dev/null 2>&1 && openssl x509 -in "$DP/kiosk-lobby-1.crt" -noout -subject | grep -q 'CN *= *kiosk-lobby-1' && pass "발급한 인증서가 일회용 CA 로 검증되고 주체 CN 이 기기 ID 다" || fail "발급 인증서 검증"
bash "$ROOT/ingress/scripts/device-pki.sh" gateway-config >/dev/null 2>&1
! grep -v '^[[:space:]]*#' "$ROOT/ingress/config/device-tls.caddy" | grep -q '^[[:space:]]*client_auth' && pass "기본 조각(device-tls.caddy)은 검증이 꺼져 있다(client_auth 없음)" || fail "기본 조각이 검증을 켠다"
grep -q 'mode verify_if_given' "$DP/device-tls.caddy" && grep -q 'trusted_ca_cert_file /etc/caddy/device-ca.pem' "$DP/device-tls.caddy" && pass "켠 조각은 신뢰 CA 파일 하나(/etc/caddy/device-ca.pem)만 믿는다" || fail "켠 조각 내용"
# 생성된 경로 표 구조: 모든 프록시가 X-Openit-Dn 을 지우고, 기기 헤더는 지우거나(토큰·직원 경로) 인증서 CN 으로 덮어쓴다(인증서 경로)
docker run --rm --entrypoint /opt/gw/bin/python -v "$ROOT/ingress/tests/exposures:/ex:ro" "$ING" /usr/local/bin/gen-ingress-routes.py /etc/openit/exposures-builtin /ex > "$T/routes.caddy" 2>/dev/null
python3 - "$T/routes.caddy" "$ROOT/ingress/config/Caddyfile" <<'PY' && pass "생성된 모든 reverse_proxy 가 X-Openit-Dn 을 지우고 기기 헤더를 지우거나 CN 으로 덮어쓴다, 인증서 경로가 토큰 경로보다 먼저다" || fail "경로 표 헤더 처리"
import re, sys
t = open(sys.argv[1], encoding="utf-8").read(); cf = open(sys.argv[2], encoding="utf-8").read()
blocks = [m.start() for m in re.finditer(r"reverse_proxy https://", t)]
assert len(blocks) >= 4, f"프록시 {len(blocks)}개"
for b in blocks:
    body = t[b:b + 900]
    assert "header_up -X-Openit-Dn" in body, "X-Openit-Dn 을 지우지 않는 프록시"
    assert ("header_up -X-Openit-Device" in body) or ('header_up X-Openit-Device "{re.devcn.1}"' in body), "기기 헤더 처리가 없는 프록시"
assert 'request_header X-Openit-Dn "dn={http.request.tls.client.subject}"' in cf and "@device_cert header_regexp devcn X-Openit-Dn" in cf and "{0,127}" in cf
assert t.index("handle @device_cert") < t.index("handle @device_ok"), "인증서 경로가 토큰 경로보다 먼저여야 한다"
PY
DEVICE_PKI_DIR="$T/pki2" bash "$ROOT/ingress/scripts/device-pki.sh" init >/dev/null 2>&1; DEVICE_PKI_DIR="$T/pki2" bash "$ROOT/ingress/scripts/device-pki.sh" issue rogue-1 >/dev/null 2>&1   # 신뢰하지 않는 다른 CA
TLS_CONF=$DP/device-tls.caddy; [ "${MTLS_MUTATE:-0}" = 1 ] && TLS_CONF=$ROOT/ingress/config/device-tls.caddy   # 변이: 검증을 끈 기본 조각
MNT=(-v "$TLS_CONF:/etc/caddy/device-tls.caddy:ro" -v "$DP/device-ca.pem:/etc/caddy/device-ca.pem:ro")
docker run --rm "${MNT[@]}" $(gateway_test_mounts "$PKI") --user 10001:10001 --group-add "$SECRETS_GID" --read-only --tmpfs /tmp:uid=10001,gid=10001 -v "$DATAVOL:/data" --tmpfs /config:uid=10001,gid=10001 -e "GATEWAY_HOSTS=localhost:8443,127.0.0.1:8443" -v "$ROOT/ingress/tests/exposures:/etc/openit/exposures:ro" -v "$T/tokens:/run/secrets:ro" "$ING" validate >/dev/null 2>&1 && pass "설정 검증 통과(이 시험의 조각: $([ "${MTLS_MUTATE:-0}" = 1 ] && echo 꺼짐 || echo 켜짐))" || fail "설정 검증"
start_upstream "$ROOT/ingress/tests/gateway-oidc/echo-upstream.py" survey-service
start_gateway $CN "${MNT[@]}"
P=$(wait_port $CN) || { # 클라이언트 인증을 쓰는 사이트는 Host 와 SNI 가 같아야 한다(421): 이름으로 붙는다
  P=""; for i in $(seq 1 40); do P=$(docker port $CN 8443/tcp 2>/dev/null | head -1 | sed 's/.*://'); [ -n "$P" ] && curl -sk -o /dev/null -m 2 --resolve "localhost:$P:127.0.0.1" "https://localhost:$P/healthz" && break; sleep 0.5; done; }
[ -n "$P" ] || { echo "게이트웨이가 뜨지 않았다"; docker logs $CN 2>&1 | tail -5; exit 1; }
cv() { curl -sk -m 8 --resolve "localhost:$P:127.0.0.1" -D "$T/h.out" -o "$T/b.out" -w '%{http_code}' "$@"; }
U="https://localhost:$P"
dev() { python3 -c 'import json,sys;h=json.load(open(sys.argv[1])).get("headers",{});print((h.get("X-Openit-Device") or ["<없음>"])[0])' "$T/b.out" 2>/dev/null; }
c=$(cv --cert "$DP/kiosk-lobby-1.crt" --key "$DP/kiosk-lobby-1.key" -X POST "$U/v1/sessions"); d=$(dev)
[ "$c" = 200 ] && [ "$d" = kiosk-lobby-1 ] && pass "신뢰 CA 의 인증서 -> 키오스크 경로 통과, 서비스가 받은 X-Openit-Device=kiosk-lobby-1(CN)" || fail "인증서 통과/CN 전달 (코드 $c, 헤더 '$d')"
c=$(cv --cert "$DP/kiosk-lobby-1.crt" --key "$DP/kiosk-lobby-1.key" -H "X-Openit-Device: attacker" -X POST "$U/v1/sessions"); d=$(dev)
[ "$c" = 200 ] && [ "$d" = kiosk-lobby-1 ] && pass "위조 X-Openit-Device: attacker 는 인증서 CN 으로 덮어쓰인다" || fail "위조 헤더 덮어쓰기 (코드 $c, 헤더 '$d')"
c=$(cv -X POST "$U/v1/sessions"); w=$(grep -ic '^www-authenticate: bearer' "$T/h.out")
[ "$c" = 401 ] && [ "$w" = 1 ] && pass "인증서 없음 -> 401 + WWW-Authenticate: Bearer" || fail "인증서 없음 (코드 $c)"
c=$(cv -H "X-Openit-Device: attacker" -X POST "$U/v1/sessions")
[ "$c" = 401 ] && pass "인증서 없이 위조 헤더만 보내도 401" || fail "무인증서 위조 헤더 (코드 $c)"
curl -sk -m 8 --resolve "localhost:$P:127.0.0.1" --cert "$T/pki2/rogue-1.crt" --key "$T/pki2/rogue-1.key" -o /dev/null "$U/v1/sessions" -X POST; rc=$?
[ "$rc" != 0 ] && pass "신뢰하지 않는 CA 의 인증서는 TLS 에서 거부된다(curl 종료 $rc)" || fail "다른 CA 인증서가 받아들여졌다"
c=$(cv "$U/staff/"); { [ "$c" = 503 ] || [ "$c" = 401 ] || [ "$c" = 302 ]; } && pass "직원 경로는 기기 인증서와 무관하게 사람 인증을 요구한다(이 시험에는 identity-proxy 가 없어 닫힌다: $c)" || fail "직원 경로 (코드 $c)"
TOK=$(cat "$T/tokens/devices/e2e")
c=$(cv -H "Authorization: Bearer $TOK" -H "X-Openit-Device: attacker" -X POST "$U/v1/sessions"); d=$(dev)
[ "$c" = 200 ] && [ "$d" = "<없음>" ] && pass "기기 토큰 경로(기기별 파일): 위조 X-Openit-Device 는 지워지고 서비스에 전달되지 않는다" || fail "토큰 경로 위조 헤더 (코드 $c, 헤더 '$d')"
echo; [ $F = 0 ] && echo "통과: 기기 인증서(mTLS) 공개 입구 시험 $N건" || { echo "실패: $F건 ($N건)"; exit 1; }
