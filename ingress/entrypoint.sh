#!/bin/sh
# 공개 입구 시작: 환경을 계약 PublicIngressEnv 로 검증하고(위반 64), 마운트된 영역 Exposure 선언들에서 경로 표(routes.caddy)를, GATEWAY_HOSTS 에서 허용 호스트 목록을 만든 뒤 caddy 를 실행한다.
# 선언이 계약을 어기면 시작하지 않는다(종료 65). 비밀 값은 출력하지 않는다.
set -eu
# 첫 인자가 절대 경로면 잡 선언 argv 다(계약 JobsDeclaration.argv: 이미지 안에서 실행할 명령). 서버 환경 검사 없이 그대로 실행한다(Docker 표준 진입점 관례).
# 서버 역할의 Env 검사를 잡에 걸면 잡에 없는 서버 입력을 요구하게 된다(2026-11-06 E2E 잡 실패에서)
case "${1:-}" in /*) exec "$@";; esac
# 부명령 health(이미지 HEALTHCHECK): 평문 루프백 포트의 /healthz 가 200 + {"status":"ok"} 이면 건강하다(R1.1: 평문은 루프백만). 환경·선언 준비 없이 동작한다.
if [ "${1:-}" = health ]; then wget -q -T 3 -O- http://127.0.0.1:8080/healthz | grep -q '"status":"ok"'; exit $?; fi
ENVOUT=$(envcheck /etc/openit/schemas/PublicIngressEnv.schema.json) || exit 64   # 명령 치환 안의 실패는 eval 에 가려지므로 먼저 받아 종료 코드를 본다
eval "$ENVOUT"
mkdir -p /tmp/openit
# 기기 인증서(mTLS, PUBLIC_API F절 기본 기기 인증): 기기 CA 파일(INGRESS_DEVICE_CA_FILE, 필수)로 검증 조각을 만든다. 파일이 없으면 기본 기기 인증이 조용히 꺼지므로 시작하지 않는다(종료 64).
[ -r "$INGRESS_DEVICE_CA_FILE" ] && grep -q "BEGIN CERTIFICATE" "$INGRESS_DEVICE_CA_FILE" || { echo "ingress: 기기 CA 파일이 없거나 PEM 인증서가 아니다: $INGRESS_DEVICE_CA_FILE" >&2; exit 64; }
# verify_if_given: 인증서를 낸 클라이언트는 이 CA 가 발급한 것이어야 핸드셰이크가 된다(아니면 TLS 오류). 인증서를 안 낸 클라이언트(직원 브라우저)는 통과해 토큰·계정 인증으로 간다.
printf '(device_client_auth) {\n\tclient_auth {\n\t\tmode verify_if_given\n\t\ttrusted_ca_cert_file %s\n\t}\n}\n' "$INGRESS_DEVICE_CA_FILE" > /tmp/openit/device-tls.caddy
# internal 모드의 사설 CA 루트(공개 인증서)를 INGRESS_ROOT_EXPORT_DIR/root_ca.crt 로 내보낸다(계약 PublicIngressEnv, RUNTIME OUT-FILE): deploy 가 이 폴더를 감시·키오스크·직원 PC 에 나눠 준다. 쓸 수 없으면 신뢰가 조용히 끊기므로 시작하지 않는다(종료 64).
if [ "$GATEWAY_TLS_MODE" = internal ]; then
  [ -d "$INGRESS_ROOT_EXPORT_DIR" ] && touch "$INGRESS_ROOT_EXPORT_DIR/.write-test" 2>/dev/null && rm -f "$INGRESS_ROOT_EXPORT_DIR/.write-test" || { echo "ingress: internal 모드인데 루트 내보내기 폴더에 쓸 수 없다: $INGRESS_ROOT_EXPORT_DIR" >&2; exit 64; }
fi
[ -d "$INGRESS_EXPOSURES" ] || { echo "ingress: Exposure 선언 폴더가 없다: $INGRESS_EXPOSURES" >&2; exit 64; }
if [ "$GATEWAY_TLS_MODE" = files ]; then [ -r "$INGRESS_TLS_DIR/tls.crt" ] && [ -r "$INGRESS_TLS_DIR/tls.key" ] || { echo "ingress: files 모드인데 $INGRESS_TLS_DIR/tls.{crt,key} 가 없다" >&2; exit 64; }; fi
/opt/gw/bin/python /usr/local/bin/gen-ingress-routes.py "$INGRESS_EXPOSURES" > /tmp/openit/routes.caddy || { echo "ingress: 경로 표를 만들지 못했다(선언이 계약을 어겼거나 입력이 틀렸다)" >&2; exit 65; }
/opt/gw/bin/python /usr/local/bin/device-auth.py "$INGRESS_DEVICE_ALLOWLIST_FILE" --check || exit 65
# 파생 값은 이미지가 만든다: 오류 본문의 pipeline_schema_version(계약 패키지 현행 값)과 CSRF 허용 호스트 목록(GATEWAY_HOSTS 에서)
export PIPELINE_SCHEMA_VERSION=$(/opt/gw/bin/python -c 'import boundary_contracts as b;print(b.PIPELINE_SCHEMA_VERSION)')
export GATEWAY_SITES=$(/opt/gw/bin/python /usr/local/bin/gen-host-names.py --sites "$GATEWAY_HOSTS") || exit 65   # Caddy 사이트 주소 목록(쉼표 뒤 공백 정규화)
export GATEWAY_HOST_NAMES=$(/opt/gw/bin/python /usr/local/bin/gen-host-names.py "$GATEWAY_HOSTS") || exit 65
export_root_loop() { # 루트는 첫 기동 때 /data 에 생기고 CA 가 바뀌면 달라진다: 생기거나 바뀔 때마다 같은 폴더에 쓰고 rename 으로 바꿔 넣는다(쓰는 도중 파일을 읽히지 않는다). 점검 주기 5초는 측정하지 않은 값이다
  R=/data/caddy/pki/authorities/local/root.crt; last=""
  while :; do
    if [ -r "$R" ]; then cur=$(cksum < "$R"); if [ "$cur" != "$last" ]; then cp "$R" "$INGRESS_ROOT_EXPORT_DIR/.root_ca.crt.tmp" && chmod 644 "$INGRESS_ROOT_EXPORT_DIR/.root_ca.crt.tmp" && mv -f "$INGRESS_ROOT_EXPORT_DIR/.root_ca.crt.tmp" "$INGRESS_ROOT_EXPORT_DIR/root_ca.crt" && last=$cur; fi; fi
    sleep 5
  done
}
case "${1:-run}" in
  run)
    /opt/gw/bin/python /usr/local/bin/device-auth.py "$INGRESS_DEVICE_ALLOWLIST_FILE" &
    auth_pid=$!
    # 소켓이 준비되기 전에 공개 입구가 요청을 받지 않는다. 프로세스 실패는 시작 실패다.
    while [ ! -S /tmp/openit/device-auth.sock ]; do kill -0 "$auth_pid" 2>/dev/null || exit 65; sleep 0.05; done
    if [ "$GATEWAY_TLS_MODE" = internal ]; then export_root_loop & fi
    exec caddy run --config /etc/caddy/Caddyfile ;;
  validate) exec caddy validate --config /etc/caddy/Caddyfile ;;   # 운영자 점검: 준비까지 같은 길로 한 뒤 설정만 검증한다
  *) echo "ingress: 알 수 없는 부명령: $1 (run|validate)" >&2; exit 64 ;;
esac
