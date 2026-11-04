#!/bin/sh
# 공개 입구 시작: 마운트된 영역 Exposure 선언들에서 경로 표(routes.caddy)를 만들고 caddy 를 실행한다. 선언이 계약을 어기면 시작하지 않는다(종료 65). 비밀 값 없음.
set -eu
DIR=${INGRESS_EXPOSURES:-/etc/openit/exposures}
mkdir -p /tmp/openit
[ -d "$DIR" ] || { echo "ingress: Exposure 선언 폴더가 없다: $DIR" >&2; exit 64; }
/opt/gw/bin/python /usr/local/bin/gen-ingress-routes.py "${INGRESS_BUILTIN:-/etc/openit/exposures-builtin}" "$DIR" > /tmp/openit/routes.caddy || { echo "ingress: 경로 표를 만들지 못했다(선언이 계약을 어겼거나 입력이 틀렸다)" >&2; exit 65; }
# 오류 본문의 pipeline_schema_version 은 계약 패키지의 현행 값이다(Caddyfile 과 생성된 표가 {$PIPELINE_SCHEMA_VERSION} 로 읽는다)
export PIPELINE_SCHEMA_VERSION=$(/opt/gw/bin/python -c 'import boundary_contracts as b;print(b.PIPELINE_SCHEMA_VERSION)')
exec caddy run --config /etc/caddy/Caddyfile
