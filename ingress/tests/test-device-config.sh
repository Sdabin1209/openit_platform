#!/usr/bin/env bash
# 실제 Caddy 공개 입구: DeviceConfig가 마운트되면 200, 없으면 상류의 404를 보존한다.
set -euo pipefail
source "$(dirname "$0")/../../scripts/lib.sh"
source "$ROOT/ingress/tests/stack-lib.sh"
stack_init device-config kiosk-frontend survey-service
rc=1
trap 'stack_cleanup "$rc"' EXIT
mkdir -p "$T/public-config"
printf '{"allow_remote_stt":false,"question_set_id":"general"}\n' > "$T/public-config/config.json"
printf '{\n admin off\n skip_install_trust\n auto_https off\n}\nhttps://:443 {\n tls /pki/leaf.crt /pki/leaf.key\n root * /public-config\n file_server\n}\n' > "$PKI/static.caddy"
docker run -d --name "$CU" --network "$NET" --network-alias kiosk-frontend \
  -v "$PKI/static.caddy:/etc/caddy/Caddyfile:ro" -v "$PKI:/pki:ro" \
  -v "$T/public-config:/public-config:ro" "$GWI" caddy run --config /etc/caddy/Caddyfile >/dev/null
extra=()
if [ "${CONFIG_FORCE_404_MUTATE:-0}" = 1 ]; then
  "$PY" - "$ROOT/ingress/config/Caddyfile" "$T/blocked.Caddyfile" <<'PY'
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text()
text = text.replace('\timport gateway_tls', '\troute {\n\t\trespond /config.json 404\n\t}\n\timport gateway_tls', 1)
Path(sys.argv[2]).write_text(text)
PY
  extra=(-v "$T/blocked.Caddyfile:/etc/caddy/Caddyfile:ro")
fi
start_gateway "$CN" -e GATEWAY_TLS_MODE=files \
  -v "$PKI/leaf.crt:/etc/openit/ingress-tls/tls.crt:ro" -v "$PKI/leaf.key:/etc/openit/ingress-tls/tls.key:ro" "${extra[@]}"
P=$(docker port "$CN" 8443/tcp | head -1 | sed 's/.*://')
if "$PY" - "$P" "$T" <<'PY'
import http.client
import json
from pathlib import Path
import ssl
import sys
import time
from boundary_contracts import validator
port, root = int(sys.argv[1]), Path(sys.argv[2])
context = ssl.create_default_context(cafile=str(root / 'pki/root_ca.crt'))
until = time.monotonic() + 45
while True:
    c = http.client.HTTPSConnection('localhost', port, context=context, timeout=8)
    try:
        c.request('GET', '/healthz')
        r = c.getresponse(); r.read()
        if r.status == 200:
            break
    except (OSError, http.client.HTTPException):
        pass
    finally:
        c.close()
    assert time.monotonic() < until, 'gateway startup deadline'
    time.sleep(.1)
c = http.client.HTTPSConnection('localhost', port, context=context, timeout=8)
try:
    c.request('GET', '/config.json')
    response = c.getresponse(); data = response.read()
    assert response.status == 200, f'public DeviceConfig: expected 200, got {response.status}'
    body = json.loads(data)
    validator('DeviceConfig').validate(body)
    assert body == {'allow_remote_stt': False, 'question_set_id': 'general'}
    (root / 'public-config/config.json').unlink()
    c.request('GET', '/config.json')
    response = c.getresponse(); response.read()
    assert response.status == 404, 'missing public configuration must remain 404'
finally:
    c.close()
PY
then
  rc=0
  echo "PASS 공개 DeviceConfig: 마운트 200·없음 404, TLS 검증"
else
  echo "FAIL 공개 DeviceConfig"
fi
exit "$rc"
