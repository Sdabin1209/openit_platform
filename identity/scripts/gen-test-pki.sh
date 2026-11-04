#!/usr/bin/env bash
# 시험용 PKI 한 벌: 루트 하나와 서버 인증서 하나(SAN: 서비스 이름 전부 + 127.0.0.1). 시험 전용, 2일 유효. 사용: gen-test-pki.sh <폴더> <SECRETS_DIR>
# 산출: <폴더>/root_ca.crt, certs/tls.{crt,key}(영역 게이트웨이용), pg/server.{crt,key}(postgres 용, 소유권은 시험 스크립트가 맞춘다), pg_hba.conf. 게이트웨이 키는 <SECRETS_DIR>/tokens/gateway-tls-key.
set -euo pipefail
D=${1:?폴더}; S=${2:?SECRETS_DIR}; mkdir -p "$D/certs" "$D/pg" "$S/tokens"
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$D/root.key" -out "$D/root_ca.crt" -subj "/CN=openit-test-root" -days 2 >/dev/null 2>&1
openssl req -newkey rsa:2048 -nodes -keyout "$D/certs/tls.key" -out "$D/leaf.csr" -subj "/CN=openit-test-leaf" >/dev/null 2>&1
printf 'subjectAltName=DNS:keycloak,DNS:oauth2-proxy,DNS:keycloak-db,DNS:gateway,DNS:localhost,IP:127.0.0.1\n' > "$D/san.ext"
openssl x509 -req -in "$D/leaf.csr" -CA "$D/root_ca.crt" -CAkey "$D/root.key" -CAcreateserial -out "$D/certs/tls.crt" -days 2 -extfile "$D/san.ext" >/dev/null 2>&1
cp "$D/certs/tls.crt" "$D/pg/server.crt"; cp "$D/certs/tls.key" "$D/pg/server.key"
cp "$D/certs/tls.key" "$S/tokens/gateway-tls-key"
chmod 644 "$D/root_ca.crt" "$D/certs/"* "$D/pg/server.crt"; chmod 640 "$S/tokens/gateway-tls-key"; chgrp "${SECRETS_GID:-$(id -g)}" "$S/tokens/gateway-tls-key" 2>/dev/null || true
printf 'local all all trust\nhost all all 127.0.0.1/32 trust\nhostssl all all 0.0.0.0/0 scram-sha-256\n' > "$D/pg_hba.conf"   # 네트워크 접속은 TLS + 암호만. local/127.0.0.1 은 컨테이너 안 점검용
