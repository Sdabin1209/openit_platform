#!/usr/bin/env bash
# 공개 입구 단독 시험용 비밀 폴더를 만든다(시험 전용 무작위 값, 값은 출력하지 않는다). 사용: gen-test-secrets.sh <폴더>
# 제품의 비밀은 deploy 가 배치할 때 만든다(platform 은 비밀 값을 만들지 않는다). 이 폴더에는 Caddyfile 이 {file./run/secrets/<이름>} 으로 읽는 토큰 파일 전부와 시험 기기 4대가 있다.
set -euo pipefail
source "$(dirname "$0")/../../scripts/lib.sh"; source "$ROOT/ingress/scripts/gateway-lib.sh"
D=${1:?폴더}; mkdir -p "$D/tokens"; chmod 750 "$D" "$D/tokens"; chgrp "$SECRETS_GID" "$D" "$D/tokens" 2>/dev/null || true   # 왜: 컨테이너 사용자는 group_add 로 이 그룹을 얻어 비밀 파일을 읽는다(640). 폴더가 700 이면 읽지 못한다; : > "$D/.test-fixtures"
for n in $(python3 -c 'import glob,json;print(" ".join(sorted({r["upstream_token"] for f in glob.glob("%s/ingress/tests/exposures/*.json" % __import__("sys").argv[1]) for r in json.load(open(f))["routes"] if r.get("upstream_token")})))' "$ROOT") $(grep -oh '{file\./run/secrets/[a-z0-9-]*}' "$ROOT"/ingress/config/Caddyfile "$ROOT"/ingress/config/*.caddy | sed 's/.*secrets\///; s/}//' | sort -u) kiosk-device-e2e kiosk-device-e2e-a kiosk-device-e2e-b kiosk-device-e2e-c; do
  [ -s "$D/tokens/$n" ] || ( umask 077; gw_rnd > "$D/tokens/$n" ); secret_fix "$D/tokens/$n"
done
while read -r acc _; do case "$acc" in ""|\#*) continue;; esac; [ -s "$D/tokens/idp-test-$acc-password" ] || ( umask 077; gw_rnd > "$D/tokens/idp-test-$acc-password" ); done < "$ROOT/ingress/tests/gateway-oidc/accounts.test.conf"
gw_write_devices "$D"
