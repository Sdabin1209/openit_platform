#!/bin/sh
# 영역 게이트웨이 시작: 마운트된 Exposure 선언에서 Envoy 설정을 만들고 envoy 를 exec 한다. 선언이 계약을 어기면 시작하지 않는다(종료 코드 != 0). 비밀 값 없음.
set -eu
EXPOSURE=${AREA_GATEWAY_EXPOSURE:-/etc/openit/exposure.json}
[ -r "$EXPOSURE" ] || { echo "area-gateway: Exposure 선언을 읽지 못했다: $EXPOSURE" >&2; exit 64; }
/opt/gw/bin/python /usr/local/bin/gen-area-gateway-config.py --exposure "$EXPOSURE" \
  --upstream "${AREA_GATEWAY_UPSTREAM:-127.0.0.1:8080}" \
  --ingress-port "${AREA_GATEWAY_INGRESS_PORT:-443}" --egress-port "${AREA_GATEWAY_EGRESS_PORT:-3128}" \
  --sds-out /tmp/openit-sds.yaml --sds-path /tmp/openit-sds.yaml > /tmp/openit-envoy.yaml || { echo "area-gateway: 설정을 만들지 못했다(선언이 계약을 어겼거나 입력이 틀렸다)" >&2; exit 65; }
exec envoy -c /tmp/openit-envoy.yaml
