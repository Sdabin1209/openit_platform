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
# 인증서 갱신(step-ca renew 가 DB_TLS_DIR 의 파일을 바꾼다): 감시 루프가 내용이 바뀌면 복사본을 갱신하고 서버 설정을 다시 읽게 한다(재시작 없음, 점검 주기 30초: 갱신 시각 12h 전 갱신(ADR 0012)에 비해 충분히 짧다, 측정 안 함). 서버가 올라오기 전에는 psql 이 실패하므로 다음 주기에 다시 한다.
( last=$(cksum < "$DB_TLS_DIR/tls.crt"); while sleep 30; do cur=$(cksum < "$DB_TLS_DIR/tls.crt" 2>/dev/null) || continue
    [ "$cur" = "$last" ] && continue
    cp "$DB_TLS_DIR/tls.crt" "$T/server.crt" && ( umask 077; cat "$DB_TLS_DIR/tls.key" > "$T/server.key" ) && psql -X -q -U "${POSTGRES_USER:-postgres}" -d postgres -c "select pg_reload_conf()" >/dev/null 2>&1 && last=$cur
  done ) &
export DB_ACCOUNT_SECRETS_DIR POSTGRES_PASSWORD_FILE
exec docker-entrypoint.sh "$@" -c ssl=on -c "ssl_cert_file=$T/server.crt" -c "ssl_key_file=$T/server.key" -c ssl_min_protocol_version=TLSv1.2 -c "hba_file=$T/pg_hba.conf" \
  -c log_statement=none -c log_min_error_statement=panic -c log_min_duration_statement=-1 -c log_error_verbosity=terse -c log_parameter_max_length=0 -c log_parameter_max_length_on_error=0
