#!/usr/bin/env bash
# 시험용 PKI 한 벌: 루트 하나와 서버 인증서 하나(SAN: 서비스 이름 전부 + 127.0.0.1). 시험 전용, 2일 유효. 사용: gen-test-pki.sh <폴더>
# 산출: <폴더>/root_ca.crt, certs/tls.{crt,key}(영역 게이트웨이·identity-db·공개 입구 files 모드가 같은 파일을 쓴다).
set -euo pipefail
D=${1:?폴더}; mkdir -p "$D/certs"
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$D/root.key" -out "$D/root_ca.crt" -subj "/CN=openit-test-root" -days 2 >/dev/null 2>&1
openssl req -newkey rsa:2048 -nodes -keyout "$D/certs/tls.key" -out "$D/leaf.csr" -subj "/CN=openit-test-leaf" >/dev/null 2>&1
printf 'subjectAltName=DNS:identity,DNS:identity-proxy,DNS:identity-db,DNS:gateway,DNS:localhost,IP:127.0.0.1\n' > "$D/san.ext"
openssl x509 -req -in "$D/leaf.csr" -CA "$D/root_ca.crt" -CAkey "$D/root.key" -CAcreateserial -out "$D/certs/tls.crt" -days 2 -extfile "$D/san.ext" >/dev/null 2>&1
chmod 644 "$D/root_ca.crt" "$D/certs/"*
