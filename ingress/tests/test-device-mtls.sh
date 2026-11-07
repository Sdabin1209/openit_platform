#!/usr/bin/env bash
# 실제 공개 입구의 CA 검증·허용 목록·회전·폐기. 서버 CA/SNI 검증을 끄지 않는다.
set -euo pipefail
source "$(dirname "$0")/../../scripts/lib.sh"
source "$ROOT/ingress/tests/stack-lib.sh"
stack_init device-mtls survey-service
rc=1
trap 'stack_cleanup "$rc"' EXIT
for label in old new; do
  DEVICE_PKI_DIR="$T/dpki" bash "$ROOT/ingress/scripts/device-pki.sh" issue kiosk-1 >/dev/null 2>&1
  cp "$T/dpki/kiosk-1.crt" "$T/dpki/$label.crt"
  cp "$T/dpki/kiosk-1.key" "$T/dpki/$label.key"
done
DEVICE_PKI_DIR="$T/rogue" bash "$ROOT/ingress/scripts/device-pki.sh" init >/dev/null 2>&1
DEVICE_PKI_DIR="$T/rogue" bash "$ROOT/ingress/scripts/device-pki.sh" issue kiosk-1 >/dev/null 2>&1
if [ "${MTLS_MUTATE:-0}" = 1 ]; then DEVCA_MOUNT="$T/rogue/ca.crt"; fi
start_upstream "$ROOT/ingress/tests/gateway-oidc/echo-upstream.py" survey-service
start_gateway "$CN" -e GATEWAY_TLS_MODE=files -v "$PKI/leaf.crt:/etc/openit/ingress-tls/tls.crt:ro" -v "$PKI/leaf.key:/etc/openit/ingress-tls/tls.key:ro"
P=$(docker port "$CN" 8443/tcp | head -1 | sed 's/.*://')
if "$PY" "$ROOT/ingress/tests/device_mtls_check.py" "$P" "$T"; then
  rc=0
  echo "PASS 실제 Caddy mTLS: TLS·인증서 없음·위조·회전·동일 연결 폐기·잘못된 목록·복구"
else
  echo "FAIL 실제 Caddy mTLS"
fi
exit "$rc"
