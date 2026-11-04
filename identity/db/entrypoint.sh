#!/bin/sh
# identity-db 진입점(D126): 환경을 계약 AreaDatabaseEnv 로 검증하고(위반 64), 서버 TLS 파일을 postgres 소유 0600 으로 /tmp(tmpfs)에 옮기고, 접속 규칙(pg_hba)을 만들어 공식 진입점으로 넘긴다.
# 접속 규칙: 네트워크는 TLS + 암호(scram)만, 소켓(컨테이너 안)만 신뢰한다. 계정은 첫 초기화 때 10-accounts.sh 가 DatabaseDeclaration(/etc/openit/database.json)대로 만든다.
set -eu
eval "$(envcheck /etc/openit/schemas/AreaDatabaseEnv.schema.json)" || exit 64
[ -r "$DB_TLS_DIR/tls.crt" ] && [ -r "$DB_TLS_DIR/tls.key" ] || { echo "identity-db: $DB_TLS_DIR/tls.{crt,key} 가 없다(서버 TLS 필수)" >&2; exit 64; }
[ -r "$POSTGRES_PASSWORD_FILE" ] || { echo "identity-db: POSTGRES_PASSWORD_FILE 이 가리키는 파일이 없다" >&2; exit 64; }
T=/tmp/pgtls; mkdir -p "$T"; chmod 700 "$T"
cp "$DB_TLS_DIR/tls.crt" "$T/server.crt"; ( umask 077; cat "$DB_TLS_DIR/tls.key" > "$T/server.key" )   # 키는 서버 사용자 소유 0600 이어야 postgres 가 연다
printf 'local all all trust\nhostssl all all 0.0.0.0/0 scram-sha-256\nhostssl all all ::/0 scram-sha-256\n' > "$T/pg_hba.conf"
export DB_ACCOUNT_SECRETS_DIR POSTGRES_PASSWORD_FILE
exec docker-entrypoint.sh "$@" -c ssl=on -c "ssl_cert_file=$T/server.crt" -c "ssl_key_file=$T/server.key" -c ssl_min_protocol_version=TLSv1.2 -c "hba_file=$T/pg_hba.conf" \
  -c log_statement=none -c log_min_error_statement=panic -c log_min_duration_statement=-1 -c log_error_verbosity=terse -c log_parameter_max_length=0 -c log_parameter_max_length_on_error=0
