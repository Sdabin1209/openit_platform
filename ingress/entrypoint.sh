#!/bin/sh
# 공개 입구 시작: 환경을 계약 PublicIngressEnv 로 검증하고(위반 64), 마운트된 영역 Exposure 선언들에서 경로 표(routes.caddy)를, 기기 토큰 폴더에서 devices.caddy 를, GATEWAY_HOSTS 에서 허용 호스트 목록을 만든 뒤 caddy 를 실행한다.
# 선언이 계약을 어기면 시작하지 않는다(종료 65). 비밀 값은 출력하지 않는다.
set -eu
# 부명령 export-root <폴더>: internal 모드가 쓰는 사설 CA 의 루트 인증서(공개)를 <폴더>/root_ca.crt 로 내보낸다. 감시·키오스크·직원 PC 가 공개 입구를 믿는 길이다(MonitoringEnv.MONITORING_ROOT_CA 는 여러 PEM 을 이어 붙인 파일을 받는다).
# 같은 /data 볼륨을 써야 한다(docker run --volumes-from <공개 입구> ... export-root /out): 루트는 첫 기동 때 /data 에 생긴다. 환경·선언 검증 없이 동작한다.
if [ "${1:-}" = export-root ]; then
  R=/data/caddy/pki/authorities/local/root.crt; O=${2:?사용: export-root <출력 폴더>}
  [ -r "$R" ] || { echo "ingress: 사설 CA 루트가 아직 없다($R): 공개 입구를 internal 모드로 한 번 기동한 /data 볼륨을 써야 한다" >&2; exit 1; }
  cp "$R" "$O/root_ca.crt" && chmod 644 "$O/root_ca.crt"; exit $?
fi
eval "$(envcheck /etc/openit/schemas/PublicIngressEnv.schema.json)" || exit 64
mkdir -p /tmp/openit
[ -d "$INGRESS_EXPOSURES" ] || { echo "ingress: Exposure 선언 폴더가 없다: $INGRESS_EXPOSURES" >&2; exit 64; }
if [ "$GATEWAY_TLS_MODE" = files ]; then [ -r "$INGRESS_TLS_DIR/tls.crt" ] && [ -r "$INGRESS_TLS_DIR/tls.key" ] || { echo "ingress: files 모드인데 $INGRESS_TLS_DIR/tls.{crt,key} 가 없다" >&2; exit 64; }; fi
/opt/gw/bin/python /usr/local/bin/gen-ingress-routes.py /etc/openit/exposures-builtin "$INGRESS_EXPOSURES" > /tmp/openit/routes.caddy || { echo "ingress: 경로 표를 만들지 못했다(선언이 계약을 어겼거나 입력이 틀렸다)" >&2; exit 65; }
( umask 077; /opt/gw/bin/python /usr/local/bin/gen-devices.py "$INGRESS_DEVICE_TOKENS_DIR" > /tmp/openit/devices.caddy ) || { echo "ingress: 기기 토큰 폴더가 계약 형식이 아니다: $INGRESS_DEVICE_TOKENS_DIR" >&2; exit 65; }
# 파생 값은 이미지가 만든다: 오류 본문의 pipeline_schema_version(계약 패키지 현행 값)과 CSRF 허용 호스트 목록(GATEWAY_HOSTS 에서)
export PIPELINE_SCHEMA_VERSION=$(/opt/gw/bin/python -c 'import boundary_contracts as b;print(b.PIPELINE_SCHEMA_VERSION)')
export GATEWAY_HOST_NAMES=$(/opt/gw/bin/python /usr/local/bin/gen-host-names.py "$GATEWAY_HOSTS") || exit 65
case "${1:-run}" in
  run) exec caddy run --config /etc/caddy/Caddyfile ;;
  validate) exec caddy validate --config /etc/caddy/Caddyfile ;;   # 운영자 점검: 준비까지 같은 길로 한 뒤 설정만 검증한다
  *) echo "ingress: 알 수 없는 부명령: $1 (run|validate)" >&2; exit 64 ;;
esac
