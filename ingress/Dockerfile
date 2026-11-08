# platform 공개 입구(사람·기기의 게이트웨이, ADR 0002): Caddy(속도 제한 모듈 포함 빌드) + 이 영역의 설정. 경로 표는 시작할 때 마운트된 영역 Exposure 선언들에서 생성한다(S9).
# 입력은 계약 PublicIngressEnv(환경 변수의 이름·기본값, 기동 때 envcheck 가 검증: 위반이면 종료 64)와 마운트: INGRESS_EXPOSURES(영역 Exposure 선언 폴더, 위반·중복 65), INGRESS_DEVICE_ALLOWLIST_FILE(DeviceAllowlist JSON),
#   INGRESS_UPSTREAM_TOKENS_DIR(Exposure.upstream_token 이름마다 파일 하나), INGRESS_ROOT_CA, files 모드는 INGRESS_TLS_DIR. 호스트 이름 목록·스키마 버전 같은 파생 값은 이미지가 만든다. /tmp,/data,/config 는 tmpfs.
ARG RESTIC_IMAGE=docker.io/restic/restic@sha256:4cf4a61ef9786f4de53e9de8c8f5c040f33830eb0a10bf3d614410ee2fcb6120
ARG CADDY_BUILDER=docker.io/library/caddy:2.11.7-builder
ARG CADDY_IMAGE=docker.io/library/caddy@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f
ARG GO_BUILDER=docker.io/library/caddy@sha256:c4cd20eaa0b69112fd5d4f721ffc9671687e1d5d0b155c8620cf7546dbef94c0
FROM ${GO_BUILDER} AS envcheck
COPY --from=common . /src/
RUN cd /src && CGO_ENABLED=0 go build -trimpath -buildvcs=false -o /envcheck ./cmd/envcheck
FROM ${CADDY_BUILDER} AS build
RUN xcaddy build v2.11.7 --with github.com/mholt/caddy-ratelimit
FROM ${RESTIC_IMAGE} AS restic
FROM ${CADDY_IMAGE}
ARG COMMIT=unknown
ARG BOUNDARY_TAG=unknown
ARG JOBS_JSON
USER 0
COPY --from=build /usr/bin/caddy /usr/bin/caddy
# 왜 파일 capability 제거: 공개 입구는 8443 을 열고(1024 이상) cap_drop ALL 로 뜬다. 파일 capability(cap_net_bind_service)가 남아 있으면 커널이 exec 를 거부한다(측정함: Operation not permitted)
RUN apk add --no-cache python3 py3-pip libcap-utils >/dev/null && setcap -r /usr/bin/caddy && python3 -m venv /opt/gw
COPY --from=boundary_contracts . /tmp/boundary
RUN /opt/gw/bin/pip install -q --no-cache-dir /tmp/boundary && rm -rf /tmp/boundary
LABEL io.openit.jobs="${JOBS_JSON}" io.openit.service="public-ingress" io.openit.revision="${COMMIT}" io.openit.contracts.boundary="${BOUNDARY_TAG}" io.openit.contracts.survey-schema="n/a" io.openit.model-runtime="n/a"
COPY config/ /etc/caddy/
COPY --from=envcheck /envcheck /usr/local/bin/envcheck
# 데이터 주인 백업·복구 잡(gateway-data = /data): restic 은 잠금 digest 의 공식 이미지에서, 잡 본체는 common/backup-job.sh
COPY --from=restic /usr/bin/restic /usr/local/bin/restic
COPY --from=common --chmod=755 backup-job.sh /usr/local/bin/platform-backup-job
# 오프라인 검증은 전이 참조(_common·CommonEnv·잡 Env 포함)까지 필요하므로 계약 패키지의 스키마 묶음을 함께 넣는다.
COPY --from=boundary_contracts boundary_contracts/schemas/ /etc/openit/schemas/
COPY gen-ingress-routes.py device-auth.py gen-host-names.py gen-device-id-re.py /usr/local/bin/
COPY schemas/ /usr/local/bin/schemas/
COPY entrypoint.sh /usr/local/bin/ingress-entrypoint.sh
# 인증 없는 요청의 기대 응답 점검(공개 입구 동작의 정본: 선언에서 기대 행을 만든다). 배포는 띄운 스택에 docker run --entrypoint selfcheck-unauth 로 실행만 한다
COPY selfcheck-unauth.py /usr/local/bin/selfcheck-unauth.py
COPY selfcheck-unauth.sh /usr/local/bin/selfcheck-unauth
# 상태 폴더는 Docker 표준 VOLUME 으로 선언한다: /data 에 internal 모드의 사설 CA(루트가 바뀌면 신뢰하는 쪽이 모두 깨진다)와 인증서가 남는다, /config 는 Caddy 자동 설정
RUN mkdir -p /data /config /etc/openit/root-out && chown 10001:10001 /data /config /etc/openit/root-out && chmod 0755 /etc/openit/root-out   # 루트 내보내기 폴더(INGRESS_ROOT_EXPORT_DIR 기본값)도 이름 있는 볼륨의 첫 마운트 복사로 이미지 사용자 소유가 된다
VOLUME ["/data", "/config"]
# 건강 확인(Docker 표준 HEALTHCHECK): 공개 입구 자신의 /healthz(R5.1). 간격·재시도는 측정하지 않은 값이다
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 CMD ["/usr/local/bin/ingress-entrypoint.sh", "health"]
USER 10001
ENTRYPOINT ["/usr/local/bin/ingress-entrypoint.sh"]
