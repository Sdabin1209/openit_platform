# platform 공개 입구(사람·기기의 게이트웨이, ADR 0002): Caddy(속도 제한 모듈 포함 빌드) + 이 영역의 설정. 경로 표는 시작할 때 마운트된 영역 Exposure 선언들에서 생성한다(S9).
# 입력은 계약 PublicIngressEnv(환경 변수의 이름·기본값, 기동 때 envcheck 가 검증: 위반이면 종료 64)와 마운트: INGRESS_EXPOSURES(영역 Exposure 선언 폴더, 위반·중복 65), INGRESS_DEVICE_TOKENS_DIR(기기마다 파일 하나),
#   INGRESS_UPSTREAM_TOKENS_DIR(Exposure.upstream_token 이름마다 파일 하나), INGRESS_ROOT_CA, files 모드는 INGRESS_TLS_DIR. 호스트 이름 목록·스키마 버전 같은 파생 값은 이미지가 만든다. /tmp,/data,/config 는 tmpfs.
ARG CADDY_BUILDER=docker.io/library/caddy:2.11.7-builder
ARG CADDY_IMAGE=docker.io/library/caddy@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f
ARG GO_BUILDER=docker.io/library/caddy@sha256:c4cd20eaa0b69112fd5d4f721ffc9671687e1d5d0b155c8620cf7546dbef94c0
FROM ${GO_BUILDER} AS envcheck
COPY --from=common . /src/
RUN cd /src && CGO_ENABLED=0 go build -trimpath -buildvcs=false -o /envcheck ./cmd/envcheck
FROM ${CADDY_BUILDER} AS build
RUN xcaddy build v2.11.7 --with github.com/mholt/caddy-ratelimit
FROM ${CADDY_IMAGE}
ARG COMMIT=unknown
ARG BOUNDARY_TAG=unknown
USER 0
COPY --from=build /usr/bin/caddy /usr/bin/caddy
# 왜 파일 capability 제거: 공개 입구는 8443 을 열고(1024 이상) cap_drop ALL 로 뜬다. 파일 capability(cap_net_bind_service)가 남아 있으면 커널이 exec 를 거부한다(측정함: Operation not permitted)
RUN apk add --no-cache python3 py3-pip libcap-utils >/dev/null && setcap -r /usr/bin/caddy && python3 -m venv /opt/gw
COPY --from=boundary_contracts . /tmp/boundary
RUN /opt/gw/bin/pip install -q --no-cache-dir /tmp/boundary && rm -rf /tmp/boundary
LABEL io.openit.service="public-ingress" io.openit.revision="${COMMIT}" io.openit.contracts.boundary="${BOUNDARY_TAG}" io.openit.contracts.survey-schema="n/a" io.openit.model-runtime="n/a"
COPY config/ /etc/caddy/
# 사람 인증(Keycloak, oauth2-proxy)의 공개 경로 선언: 공개 입구와 사람 인증은 둘 다 platform 컴포넌트라 그 사이 선언은 영역 안 계약이다(구조 규칙 5). 영역 선언과 함께 읽고 같은 충돌 규칙을 적용한다
COPY exposures-builtin/ /etc/openit/exposures-builtin/
COPY --from=envcheck /envcheck /usr/local/bin/envcheck
COPY --from=boundary_contracts schemas/PublicIngressEnv.schema.json /etc/openit/schemas/
COPY gen-ingress-routes.py gen-devices.py gen-host-names.py /usr/local/bin/
COPY entrypoint.sh /usr/local/bin/ingress-entrypoint.sh
# 인증 없는 요청의 기대 응답 점검(공개 입구 동작의 정본: 선언에서 기대 행을 만든다). 배포는 띄운 스택에 docker run --entrypoint selfcheck-unauth 로 실행만 한다
COPY selfcheck-unauth.py /usr/local/bin/selfcheck-unauth.py
COPY selfcheck-unauth.sh /usr/local/bin/selfcheck-unauth
# 상태 폴더는 Docker 표준 VOLUME 으로 선언한다: /data 에 internal 모드의 사설 CA(루트가 바뀌면 신뢰하는 쪽이 모두 깨진다)와 인증서가 남는다, /config 는 Caddy 자동 설정
RUN mkdir -p /data /config && chown 10001:10001 /data /config
VOLUME ["/data", "/config"]
USER 10001
ENTRYPOINT ["/usr/local/bin/ingress-entrypoint.sh"]
