# platform 공개 입구(사람·기기의 게이트웨이, ADR 0002): Caddy 공식 이미지(digest 고정) + 이 영역의 설정. 경로 표는 각 영역의 Exposure 선언에서 생성한다(scripts/gen-ingress-routes.py).
# 배치가 주는 것: 비밀 파일(/run/secrets/*), 기기 토큰 조각 devices.caddy, 필요하면 기기 CA(device-ca.pem). 환경: GATEWAY_HOSTS·GATEWAY_TLS_MODE 등(GatewayEnv).
ARG CADDY_IMAGE=docker.io/library/caddy@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f
FROM ${CADDY_IMAGE}
ARG COMMIT=unknown
ARG BOUNDARY_TAG=unknown
LABEL io.openit.service="public-ingress" io.openit.revision="${COMMIT}" io.openit.contracts.boundary="${BOUNDARY_TAG}" io.openit.contracts.survey-schema="n/a" io.openit.model-runtime="n/a"
COPY config/ /etc/caddy/
USER 10001
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile"]
