# platform 공개 입구(사람·기기의 게이트웨이, ADR 0002): Caddy(속도 제한 모듈 포함 빌드) + 이 영역의 설정. 경로 표는 시작할 때 마운트된 영역 Exposure 선언들에서 생성한다(S9).
# 배포 입력(영역 사이 계약이 아니다): /etc/openit/exposures/*.json(각 영역 Exposure, 계약 스키마 검증, 어기면 시작 안 함 종료 65), /etc/caddy/devices.caddy(기기 토큰 목록, 비밀),
#   /run/secrets/<상류 토큰 이름>(Exposure.upstream_token 이 가리키는 파일), /etc/openit/pki/root_ca.crt, 환경 GATEWAY_HOSTS·GATEWAY_TLS_MODE 등(GatewayEnv), /tmp tmpfs.
ARG CADDY_BUILDER=docker.io/library/caddy:2.11.7-builder
ARG CADDY_IMAGE=docker.io/library/caddy@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f
FROM ${CADDY_BUILDER} AS build
RUN xcaddy build v2.11.7 --with github.com/mholt/caddy-ratelimit
FROM ${CADDY_IMAGE}
ARG COMMIT=unknown
ARG BOUNDARY_TAG=unknown
USER 0
COPY --from=build /usr/bin/caddy /usr/bin/caddy
RUN apk add --no-cache python3 py3-pip >/dev/null && python3 -m venv /opt/gw
COPY --from=boundary_contracts . /tmp/boundary
RUN /opt/gw/bin/pip install -q --no-cache-dir /tmp/boundary && rm -rf /tmp/boundary
LABEL io.openit.service="public-ingress" io.openit.revision="${COMMIT}" io.openit.contracts.boundary="${BOUNDARY_TAG}" io.openit.contracts.survey-schema="n/a" io.openit.model-runtime="n/a"
COPY config/ /etc/caddy/
COPY gen-ingress-routes.py /usr/local/bin/gen-ingress-routes.py
COPY entrypoint.sh /usr/local/bin/ingress-entrypoint.sh
USER 10001
ENTRYPOINT ["/usr/local/bin/ingress-entrypoint.sh"]
