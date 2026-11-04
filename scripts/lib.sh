#!/usr/bin/env bash
# platform 공통 셸 함수(source 해서 쓴다). 이 영역 시험·스크립트가 deploy 의 lib.sh 에 기대지 않게 필요한 것만 둔다(구조 규칙 1).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER=${DOCKER:-docker}
PY="$ROOT/.venv/bin/python"; DEPLOY_PY=$PY   # kiosk-add-device.sh 가 쓰는 이름
SECRETS_GID="${SECRETS_GID:-$(id -g)}"
die() { echo "오류: $*" >&2; exit 1; }
gateway_public_url() {
  local first=${GATEWAY_HOSTS:-localhost:8443, 127.0.0.1:8443} p=${GATEWAY_PUBLIC_TLS_PORT:-8443}
  first=${first%%,*}; first=${first// /}; first=${first%:*}
  [[ "$first" =~ ^[A-Za-z0-9.-]+$ ]] || die "GATEWAY_HOSTS 첫 항목의 호스트 이름 규칙 위반: '$first'"
  [[ "$p" =~ ^[0-9]{2,5}$ ]] || die "GATEWAY_PUBLIC_TLS_PORT 형식 위반: '$p'"
  if [ "$p" = 443 ]; then echo "https://$first"; else echo "https://$first:$p"; fi
}
gateway_test_pki() {
  local d=$1; shift; local san="" n
  for n in "$@"; do san+="${san:+,}DNS:$n"; done
  openssl req -x509 -newkey rsa:2048 -nodes -keyout "$d/root.key" -out "$d/root_ca.crt" -subj "/CN=openit-test-root" -days 2 >/dev/null 2>&1 || return 1
  openssl req -newkey rsa:2048 -nodes -keyout "$d/leaf.key" -out "$d/leaf.csr" -subj "/CN=openit-test-leaf" >/dev/null 2>&1 || return 1
  printf 'subjectAltName=%s\n' "$san" > "$d/san.ext"
  openssl x509 -req -in "$d/leaf.csr" -CA "$d/root_ca.crt" -CAkey "$d/root.key" -CAcreateserial -out "$d/leaf.crt" -days 2 -extfile "$d/san.ext" >/dev/null 2>&1 || return 1
  chmod 644 "$d"/*
}
gateway_test_mounts() { # gateway_test_mounts <gateway_test_pki 폴더>: 게이트웨이 컨테이너에 더할 인자(루트 인증서, TLS 출처 조각)
  printf '%s\n' -v "$ROOT/ingress/config/gateway-tls:/etc/caddy/gateway-tls:ro" -v "$1/root_ca.crt:/etc/openit/pki/root_ca.crt:ro" -e GATEWAY_TLS_MODE=internal
}
secret_fix() { chmod 640 "$1"; chgrp "$SECRETS_GID" "$1" 2>/dev/null || true; }
