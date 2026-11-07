#!/usr/bin/env bash
# 실제 공개 입구의 CA 검증·허용 목록·회전·폐기. 서버 CA/SNI 검증을 끄지 않는다.
set -euo pipefail
source "$(dirname "$0")/../../scripts/lib.sh"
source "$ROOT/ingress/tests/stack-lib.sh"
stack_init device-mtls survey-service identity-proxy
rc=1
trap 'stack_cleanup "$rc"' EXIT
validate_code() {
  local expected=$1 label=$2 actual; shift 2
  if docker run --rm --network "$NET" $(gateway_test_mounts "$PKI") \
    --user 10001:10001 --group-add "$SECRETS_GID" --read-only --tmpfs /tmp:uid=10001,gid=10001 \
    -e GATEWAY_HOSTS=localhost:8443 -e GATEWAY_TLS_MODE=files \
    -e INGRESS_DEVICE_ALLOWLIST_FILE=/etc/openit/devices/allowlist.json \
    -v "$DEVCA:/etc/openit/device-ca.pem:ro" -v "$T/devices:/etc/openit/devices:ro" \
    -v "$PKI/leaf.crt:/etc/openit/ingress-tls/tls.crt:ro" -v "$PKI/leaf.key:/etc/openit/ingress-tls/tls.key:ro" \
    -v "$ROOT/ingress/tests/exposures:/etc/openit/exposures:ro" -v "$T/tokens:/run/secrets:ro" \
    "$@" "$ING" validate >"$T/validate.log" 2>&1; then actual=0; else actual=$?; fi
  [ "$actual" = "$expected" ] || { echo "FAIL $label: expected=$expected actual=$actual"; exit 1; }
  echo "PASS $label"
}
validate_code 0 "정상 CA와 허용 목록의 이미지 validate"
validate_code 64 "CA 없음은 종료 64" -e INGRESS_DEVICE_CA_FILE=/etc/openit/missing.pem
printf 'not a PEM certificate\n' > "$T/notpem"
validate_code 64 "PEM 아닌 CA는 종료 64" -v "$T/notpem:/etc/openit/notpem:ro" -e INGRESS_DEVICE_CA_FILE=/etc/openit/notpem
validate_code 65 "허용 목록 없음은 종료 65" -e INGRESS_DEVICE_ALLOWLIST_FILE=/etc/openit/devices/missing.json
printf 'invalid JSON\n' > "$T/devices/allowlist.json"
validate_code 65 "잘못된 JSON 허용 목록은 종료 65"
printf '{"schema_version":1,"devices":[{"device_id":"kiosk-1","serials":["a"]},{"device_id":"kiosk-1","serials":["b"]}]}\n' > "$T/devices/allowlist.json"
validate_code 65 "중복 device_id는 종료 65"
printf '{"schema_version":1,"devices":[]}\n' > "$T/devices/allowlist.json"
docker run --rm --entrypoint /opt/gw/bin/python -v "$ROOT/ingress/tests/exposures:/ex:ro" "$ING" /usr/local/bin/gen-ingress-routes.py /ex > "$T/routes.caddy"
"$PY" - "$T/routes.caddy" "$ROOT/ingress/config/Caddyfile" <<'PY'
import sys
count = 0
for filename in sys.argv[1:]:
    lines = open(filename, encoding="utf-8").read().splitlines()
    for index, line in enumerate(lines):
        if not line.strip().startswith("reverse_proxy https://"):
            continue
        depth, body = 1, []
        for nested in lines[index + 1:]:
            text = nested.split("#", 1)[0].strip()
            depth += int(text.endswith(" {")) - int(text == "}")
            if depth == 0:
                break
            body.append(text)
        assert depth == 0, "unclosed proxy block"
        assert "header_up -X-Openit-Dn" in body, "proxy forwards untrusted DN"
        assert "header_up -X-Openit-Device" in body or 'header_up X-Openit-Device "{re.devcn.1}"' in body, "proxy forwards untrusted device"
        count += 1
assert count >= 4, "proxy coverage missing"
print("PASS 모든 상류 프록시의 DN 제거·기기 신원 제거/덮어쓰기")
PY
for label in old new; do
  DEVICE_PKI_DIR="$T/dpki" bash "$ROOT/ingress/scripts/device-pki.sh" issue kiosk-1 >/dev/null 2>&1
  cp "$T/dpki/kiosk-1.crt" "$T/dpki/$label.crt"
  cp "$T/dpki/kiosk-1.key" "$T/dpki/$label.key"
done
DEVICE_PKI_DIR="$T/rogue" bash "$ROOT/ingress/scripts/device-pki.sh" init >/dev/null 2>&1
DEVICE_PKI_DIR="$T/rogue" bash "$ROOT/ingress/scripts/device-pki.sh" issue kiosk-1 >/dev/null 2>&1
if [ "${MTLS_MUTATE:-0}" = 1 ]; then DEVCA_MOUNT="$T/rogue/ca.crt"; fi
start_upstream "$ROOT/ingress/tests/gateway-oidc/echo-upstream.py" survey-service
EXTRA_CONTAINERS="$CU-auth $CU-auth-tls"
docker run -d --name "$CU-auth" --network "$NET" --network-alias identity-proxy \
  -e FAKE_ACCOUNTS=/accounts -v "$ROOT/ingress/tests/gateway-oidc/accounts.test.conf:/accounts:ro" \
  -v "$ROOT/ingress/tests/gateway-oidc/fake-oauth2-proxy.py:/f.py:ro" "$UTIL" python /f.py >/dev/null
printf '{\n admin off\n skip_install_trust\n auto_https off\n}\nhttps://:443 {\n tls /pki/leaf.crt /pki/leaf.key\n reverse_proxy 127.0.0.1:4180\n}\n' > "$PKI/auth-front.caddy"
docker run -d --name "$CU-auth-tls" --network "container:$CU-auth" \
  -v "$PKI/auth-front.caddy:/etc/caddy/Caddyfile:ro" -v "$PKI:/pki:ro" "$GWI" caddy run --config /etc/caddy/Caddyfile >/dev/null
start_gateway "$CN" -e GATEWAY_TLS_MODE=files -v "$PKI/leaf.crt:/etc/openit/ingress-tls/tls.crt:ro" -v "$PKI/leaf.key:/etc/openit/ingress-tls/tls.key:ro"
P=$(docker port "$CN" 8443/tcp | head -1 | sed 's/.*://')
if "$PY" "$ROOT/ingress/tests/device_mtls_check.py" "$P" "$T"; then
  rc=0
  echo "PASS 실제 Caddy mTLS: TLS·인증서 없음·위조·회전·동일 연결 폐기·잘못된 목록·복구"
else
  echo "FAIL 실제 Caddy mTLS"
fi
exit "$rc"
