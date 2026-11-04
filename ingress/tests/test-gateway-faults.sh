#!/usr/bin/env bash
# 게이트웨이 장애·중계 단독 시험(RUNTIME R2.1·R3.1·R3.2·R3.3·R3.5·R3.6·R4.1, Docker 필요). 사용: bash ingress/tests/test-gateway-faults.sh
# 지금 빌드한 공개 입구 이미지를 띄우고 상류(survey-service)를 제어되는 가짜(gateway-oidc/fault-upstream.py, TLS 앞단 포함)로 둔다. 환자 경로(POST /v1/sessions, 기기 토큰 = tokens/devices/auth-1)로 부른다.
# 모든 단언은 상태 코드 + 본문 + 필요한 머리글을 함께 본다. 값(토큰)은 출력하지 않는다. 504 시험은 상류 한도(55초)를 실제로 기다려 약 90초 걸린다.
# 변이(단언이 실제로 잡는지): FAULTS_MUTATE=503 연결 거부 응답을 200 으로, FAULTS_MUTATE=413 본문 상한을 10배로 푼다(둘 다 이 시험이 실패해야 한다). FAULTS_QUICK=1 은 느린 504 시험을 건너뛴다(변이 실행용).
set -uo pipefail
source "$(dirname "$0")/../../scripts/lib.sh"; source "$ROOT/ingress/tests/stack-lib.sh"
stack_init gwfault survey-service identity identity-proxy
FAILS=0; N=0
trap 'stack_cleanup $FAILS' EXIT
chk() { local n=$1; shift; N=$((N+1)); if "$@" >/dev/null 2>&1; then echo "  PASS $n"; else echo "  FAIL $n"; FAILS=$((FAILS+1)); fi; }
CF_FILE=
if [ -n "${FAULTS_MUTATE:-}" ]; then
  docker run --rm --entrypoint cat "$ING" /etc/caddy/Caddyfile > "$T/Caddyfile.mut"
  case "$FAULTS_MUTATE" in
    503) sed -i 's/respond `{"code":"UPSTREAM_UNAVAILABLE"}` 503/respond `{"code":"UPSTREAM_UNAVAILABLE"}` 200/' "$T/Caddyfile.mut";;
    413) sed -i 's/8388608/83886080/g; s/max_size 8MiB/max_size 80MiB/' "$T/Caddyfile.mut";;
    *) echo "알 수 없는 변이: $FAULTS_MUTATE"; exit 2;;
  esac
  cmp -s "$T/Caddyfile.mut" <(docker run --rm --entrypoint cat "$ING" /etc/caddy/Caddyfile) && { echo "변이가 설정을 바꾸지 못했다"; exit 2; }
  CF_FILE=$T/Caddyfile.mut
fi
DEVTOK=$(cat "$T/tokens/devices/auth-1")
start_upstream "$ROOT/ingress/tests/gateway-oidc/fault-upstream.py" survey-service
if [ -n "$CF_FILE" ]; then start_gateway $CN -v "$CF_FILE:/etc/caddy/Caddyfile:ro"; else start_gateway $CN; fi
CP=$(wait_port $CN) || { echo "게이트웨이가 뜨지 않았다"; docker logs $CN 2>&1 | tail -n 5; exit 1; }
URL="https://127.0.0.1:$CP/v1/sessions"
# req <fault> [추가 curl 인자...]: 상태 코드는 stdout, 머리글은 $T/h, 본문은 $T/b
req() { local f=$1; shift; curl -sk -m 100 -o "$T/b" -D "$T/h" -w '%{http_code}' -X POST -H "Authorization: Bearer $DEVTOK" -H "X-Fault: $f" -H 'Content-Type: application/json' -d '{"k":1}' "$@" "$URL"; }
hdr() { grep -i "^$1:" "$T/h" | head -n 1 | sed 's/^[^:]*: *//' | tr -d '\r'; }
# ---- R2.1: 앱이 낸 4xx·5xx BoundaryError 와 413 은 상태·본문·앱이 정한 머리글 그대로 ----
c=$(req err403); chk "R2.1 앱 403 BoundaryError: 상태·본문·X-Test-Custom 그대로" bash -c '[ "$1" = 403 ] && grep -q "\"code\": \"PERMISSION_DENIED\"" "$2/b" && grep -qi "^x-test-custom: v-403" "$2/h"' _ "$c" "$T"
c=$(req err500); chk "R2.1 앱 500 BoundaryError 는 503 으로 바뀌지 않고 그대로" bash -c '[ "$1" = 500 ] && grep -q "\"code\": \"INTERNAL\"" "$2/b" && grep -qi "^x-test-custom: v-500" "$2/h"' _ "$c" "$T"
c=$(req err503); chk "R2.1 앱이 직접 낸 503 UNAVAILABLE 은 본문·Retry-After(3) 그대로(게이트웨이 UPSTREAM_UNAVAILABLE 로 덮이지 않는다)" bash -c '[ "$1" = 503 ] && grep -q "\"code\": \"UNAVAILABLE\"" "$2/b" && grep -qi "^retry-after: 3" "$2/h"' _ "$c" "$T"
c=$(req err413); chk "R2.1 앱이 낸 413 은 그대로(상태·본문 INVALID_RECORD)" bash -c '[ "$1" = 413 ] && grep -q "\"code\": \"INVALID_RECORD\"" "$2/b"' _ "$c" "$T"
c=$(req ok); chk "R2.1 정상 200 본문·X-Test-Custom 그대로" bash -c '[ "$1" = 200 ] && grep -q "\"mode\": \"ok\"" "$2/b" && grep -qi "^x-test-custom: v-ok" "$2/h"' _ "$c" "$T"
# ---- R2.1(개정): 앱이 정한 Cache-Control·보안 머리글은 그대로, 앱이 안 정한 것만 게이트웨이가 더한다 ----
c=$(req app-headers); chk "R2.1 앱이 정한 Cache-Control(max-age=60)·X-Frame-Options(SAMEORIGIN)·Referrer-Policy(origin)가 그대로" bash -c '[ "$1" = 200 ] && grep -qi "^cache-control: max-age=60" "$2/h" && grep -qi "^x-frame-options: SAMEORIGIN" "$2/h" && grep -qi "^referrer-policy: origin" "$2/h"' _ "$c" "$T"
chk "R2.1 앱이 안 정한 보안 머리글은 게이트웨이가 더한다(X-Content-Type-Options: nosniff, Strict-Transport-Security)" bash -c 'grep -qi "^x-content-type-options: nosniff" "$1/h" && grep -qi "^strict-transport-security:" "$1/h"' _ "$T"
c=$(req ok); chk "R2.1 앱이 Cache-Control 을 안 정했으면 게이트웨이의 no-store 가 붙는다" bash -c 'grep -qi "^cache-control: no-store" "$1/h"' _ "$T"
# ---- R3.5: 본문 상한 초과 -> 413 + BoundaryError(INVALID_RECORD), 503 아님 ----
c=$(head -c 9437184 /dev/zero | curl -sk -m 60 -o "$T/b" -D "$T/h" -w '%{http_code}' -X POST -H "Authorization: Bearer $DEVTOK" -H 'Content-Type: text/plain' --data-binary @- "$URL")
chk "R3.5 Content-Length 가 8MiB 초과: 413 + INVALID_RECORD(details.max_body_bytes) + application/json" bash -c '[ "$1" = 413 ] && grep -q "INVALID_RECORD" "$2/b" && grep -q "max_body_bytes" "$2/b" && grep -qi "^content-type: application/json" "$2/h"' _ "$c" "$T"
c=$(head -c 9437184 /dev/zero | curl -sk -m 60 -o "$T/b" -D "$T/h" -w '%{http_code}' -X POST -H "Authorization: Bearer $DEVTOK" -H 'Content-Type: text/plain' -H 'Transfer-Encoding: chunked' --data-binary @- "$URL")
chk "R3.5 전송 중(chunked)에 8MiB 초과: 413 (503 아님)" bash -c '[ "$1" = 413 ]' _ "$c"
# ---- R3.6: 요청 줄·헤더가 너무 큼 -> 414·431 (본문은 전송 계층이 정한다: CONVENTIONS 92행) ----
c=$(python3 "$ROOT/ingress/tests/raw_big.py" "$CP" header); chk "R3.6 헤더 1.2MB: 431 (현재 값 $c)" bash -c '[ "$1" = 431 ]' _ "$c"
c=$(python3 "$ROOT/ingress/tests/raw_big.py" "$CP" line); chk "R3.6 요청 줄(URI) 1.2MB: 414 또는 431 (현재 값 $c)" bash -c '[ "$1" = 414 ] || [ "$1" = 431 ]' _ "$c"
# ---- R3.1·R3.2 연결 거부: 상류가 닿지 않을 때 503 + UPSTREAM_UNAVAILABLE + Retry-After + application/json (504·빈 502 아님), R4.1 복구 ----
docker stop $CU-tls >/dev/null 2>&1
c=$(req ok)
chk "R3.1·R3.2 상류 멈춤: 503 + {\"code\":\"UPSTREAM_UNAVAILABLE\"}" bash -c '[ "$1" = 503 ] && grep -q "\"code\":\"UPSTREAM_UNAVAILABLE\"" "$2/b"' _ "$c" "$T"
chk "R3.1·R3.2 상류 멈춤: Retry-After 와 application/json 머리글" bash -c 'grep -qi "^retry-after: [0-9]" "$1/h" && grep -qi "^content-type: application/json" "$1/h"' _ "$T"
chk "R3.1·R3.2 본문에 상류 주소·내부 문구가 없다" bash -c '! grep -Eqi "survey-service|dial|tcp|lookup|connection refused|127\.0\.0\.1" "$1/b"' _ "$T"
ra=$(hdr Retry-After); docker start $CU-tls >/dev/null 2>&1; t0=$SECONDS; okc=000
for i in $(seq 1 30); do okc=$(req ok); [ "$okc" = 200 ] && break; sleep 0.5; done   # 복구 확인: 응답이 200 이 될 때까지의 시간이 곧 측정 대상이다
chk "R4.1 상류가 돌아오면 같은 주소로 다시 200 (복구까지 $((SECONDS-t0))초, Retry-After ${ra:-?}초 이내)" bash -c '[ "$1" = 200 ] && [ "$2" -le "${3:-2}" ]' _ "$okc" "$((SECONDS-t0))" "${ra:-2}"
# ---- R3.3: 상류 한도 안에 답이 없으면 504 + UPSTREAM_UNAVAILABLE ----
if [ "${FAULTS_QUICK:-0}" != 1 ]; then
  LIM=$(python3 -c 'import json;print([r["timeouts_ms"]["response_header"] for r in json.load(open("'"$ROOT"'/ingress/tests/exposures/survey-service.json"))["routes"] if "/v1/sessions" in r["paths"]][0]//1000)')   # 선언된 상류 한도(초)
  c=$(req sleep -H "X-Sleep: $((LIM+25))")
  chk "R3.3 상류 무응답(한도 ${LIM}초): 504 + {\"code\":\"UPSTREAM_UNAVAILABLE\"} + Retry-After" bash -c '[ "$1" = 504 ] && grep -q "\"code\":\"UPSTREAM_UNAVAILABLE\"" "$2/b" && grep -qi "^retry-after: [0-9]" "$2/h"' _ "$c" "$T"
fi
echo; [ $FAILS = 0 ] && echo "통과: 게이트웨이 장애·중계 시험 ${N}건" || { echo "실패: ${FAILS}건 / ${N}건"; exit 1; }
