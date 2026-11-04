#!/usr/bin/env bash
# Keycloak·oauth2-proxy 비밀 파일을 만든다(없을 때만, 값은 출력하지 않는다). 사용: gen-idp-secrets.sh <SECRETS_DIR>
# oauth2-proxy 는 *_file 내용을 다듬지 않고 쓰므로 client-secret·cookie-secret 은 줄바꿈 없이 만든다(deploy 스모크 시험에서 invalid_client_credentials 로 확인된 사실). cookie-secret 은 32자(16·24·32바이트만 받는다).
set -euo pipefail
source "$(dirname "$0")/../../scripts/lib.sh"
D=${1:?SECRETS_DIR}; mkdir -p "$D/tokens"; chmod 750 "$D" "$D/tokens"; chgrp "$SECRETS_GID" "$D" "$D/tokens" 2>/dev/null || true
mk() { [ -s "$D/tokens/$1" ] || ( umask 077; python3 -c "import secrets;print(secrets.token_hex($2),end='')" > "$D/tokens/$1" ); secret_fix "$D/tokens/$1"; }
mk db-keycloak-password 24; mk keycloak-bootstrap-admin-password 24; mk openit-initial-admin-password 24; mk oauth2-proxy-client-secret 24; mk oauth2-proxy-cookie-secret 16
( umask 077; printf 'db-password=%s\nbootstrap-admin-password=%s\n' "$(cat "$D/tokens/db-keycloak-password")" "$(cat "$D/tokens/keycloak-bootstrap-admin-password")" > "$D/keycloak-secrets.conf" ); secret_fix "$D/keycloak-secrets.conf"
