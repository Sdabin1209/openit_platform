#!/bin/bash
# 첫 초기화 때 DatabaseDeclaration(/etc/openit/database.json)의 계정마다 계정·데이터베이스를 만든다: owner 는 그 데이터베이스 소유(슈퍼유저·DB 생성·역할 생성 권한 없음), PUBLIC 의 CONNECT 를 거둔다.
# 암호는 DB_ACCOUNT_SECRETS_DIR/<계정> 파일(한 줄, 비밀 D84)에서 psql 변수로 읽는다: 인자·환경·출력에 값이 없다.
set -Eeuo pipefail
SDIR=${DB_ACCOUNT_SECRETS_DIR:-/run/secrets/db}
for acc in $(grep -o '"name":"[a-z0-9_]*"' /etc/openit/database.json | cut -d'"' -f4); do
  [ -s "$SDIR/$acc" ] || { echo "identity-db: 계정 $acc 의 암호 파일이 없다: $SDIR/$acc" >&2; exit 1; }
  PWFILE="$SDIR/$acc" psql -v ON_ERROR_STOP=1 --no-psqlrc -X -q -U "${POSTGRES_USER:-postgres}" -d postgres -v acc="$acc" <<'SQL'
\set pw `tr -d '\r\n' < "$PWFILE"`
CREATE ROLE :"acc" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'pw';
CREATE DATABASE :"acc" OWNER :"acc";
REVOKE ALL ON DATABASE :"acc" FROM PUBLIC;
SQL
done
