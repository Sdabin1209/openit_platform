#!/usr/bin/env bash
# 사람 인증 시험용 비밀 파일을 계약 이름대로 만든다(시험 전용 무작위 값, 값은 출력하지 않는다). 사용: gen-idp-secrets.sh <폴더>
# 파일: identity-client-secret(identity 와 identity-proxy 가 같은 값), identity-cookie-secret(32자: oauth2-proxy 는 16·24·32바이트만 받는다), identity-admin-password, identity-initial-admin-password,
#       postgres-password, db-identity(DB 계정 identity 의 암호, AreaDatabaseEnv.DB_ACCOUNT_SECRETS_DIR/<계정>), identity-db-url(libpq URI, sslmode=verify-full: DatabaseDeclaration 의 url_env).
# 줄바꿈 없이 만든다: oauth2-proxy 는 *_FILE 내용을 다듬지 않고 쓴다(끝 줄바꿈이 비밀의 일부가 되어 invalid_client_credentials 가 났다).
set -euo pipefail
source "$(dirname "$0")/../../scripts/lib.sh"
D=${1:?폴더}; mkdir -p "$D"; chmod 750 "$D"; chgrp "$SECRETS_GID" "$D" 2>/dev/null || true
mk() { [ -s "$D/$1" ] || ( umask 077; python3 -c "import secrets;print(secrets.token_hex($2),end='')" > "$D/$1" ); secret_fix "$D/$1"; }
mk identity-client-secret 24; mk identity-cookie-secret 16; mk identity-admin-password 24; mk identity-initial-admin-password 24; mk postgres-password 24; mk db-identity 24
( umask 077; printf 'postgresql://identity:%s@identity-db:5432/identity?sslmode=verify-full' "$(cat "$D/db-identity")" > "$D/identity-db-url" ); secret_fix "$D/identity-db-url"
