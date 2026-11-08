#!/usr/bin/env bash
# platform 공통 셸 함수(source 해서 쓴다). 이 영역 시험·스크립트가 deploy 의 lib.sh 에 기대지 않게 필요한 것만 둔다(구조 규칙 1).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER=${DOCKER:-docker}
eval "$(bash "$ROOT/scripts/docker-env.sh")"   # docker 환경 한 곳(사용자 전역 ~/.docker 에 기대지 않는다)
PY="$ROOT/.venv/bin/python"   # 시험·생성 스크립트가 쓰는 파이썬(리포의 가상환경)
SECRETS_GID="${SECRETS_GID:-$(id -g)}"
die() { echo "오류: $*" >&2; exit 1; }
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
