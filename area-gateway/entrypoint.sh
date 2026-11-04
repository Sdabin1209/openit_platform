#!/bin/sh
# 영역 게이트웨이 시작: 마운트된 Exposure 선언에서 Envoy 설정을 만들고 envoy 를 exec 한다. 선언이 계약을 어기면 시작하지 않는다(종료 코드 != 0). 비밀 값 없음.
set -eu
# 환경은 계약 AreaGatewayEnv 로 검증하고 기본값을 채운다(위반 64)
ENVOUT=$(envcheck /etc/openit/schemas/AreaGatewayEnv.schema.json) || exit 64   # 명령 치환 안의 실패는 eval 에 가려지므로 먼저 받아 종료 코드를 본다
eval "$ENVOUT"
if [ "${1:-}" = health ]; then   # 이미지 HEALTHCHECK: 나가는 쪽 출구(loopback)가 TCP 로 받고, 들어오는 쪽을 열었으면(인증서 폴더가 있으면) 들어오는 포트도 받는다
  tcp() { timeout 3 bash -c "exec 3<>/dev/tcp/127.0.0.1/$1" 2>/dev/null; }
  tcp "$AREA_GATEWAY_EGRESS_PORT" && { [ ! -d "$AREA_GATEWAY_CERT_DIR" ] || tcp "$AREA_GATEWAY_INGRESS_PORT"; }
  exit $?
fi
EXPOSURE=$AREA_GATEWAY_EXPOSURE
[ -r "$EXPOSURE" ] || { echo "area-gateway: Exposure 선언을 읽지 못했다: $EXPOSURE" >&2; exit 64; }
# 들어오는 쪽은 인증서 폴더가 마운트되어 있을 때만 연다(입력에서 정해진다). 마운트가 없으면 나가는 쪽 전용(compose 밖 학습 서버 등): 인증서 없는 입구를 두지 않는다
NOING=""; [ -d "$AREA_GATEWAY_CERT_DIR" ] || NOING="--no-ingress"
/opt/gw/bin/python /usr/local/bin/gen-area-gateway-config.py --exposure "$EXPOSURE" \
  --upstream "$AREA_GATEWAY_UPSTREAM" \
  --ingress-port "$AREA_GATEWAY_INGRESS_PORT" --egress-port "$AREA_GATEWAY_EGRESS_PORT" \
  $NOING --sds-out /tmp/openit-sds.yaml --sds-path /tmp/openit-sds.yaml > /tmp/openit-envoy.yaml || { echo "area-gateway: 설정을 만들지 못했다(선언이 계약을 어겼거나 입력이 틀렸다)" >&2; exit 65; }
exec envoy -c /tmp/openit-envoy.yaml
