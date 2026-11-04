# platform 인증서 발급(사설 PKI, step-ca; ADR 0012). 공식 step-ca 이미지(digest 고정) + 부명령 진입점(serve·root·token·cert). 입력은 docs/COMPONENTS.md.
ARG STEP_CA_IMAGE=docker.io/smallstep/step-ca@sha256:a8308bddba866f5fccb2740c8bb2e5dea8cdde4b5856058539a7f5170894a9c0
ARG RESTIC_IMAGE=docker.io/restic/restic@sha256:4cf4a61ef9786f4de53e9de8c8f5c040f33830eb0a10bf3d614410ee2fcb6120
ARG GO_BUILDER=docker.io/library/caddy@sha256:c4cd20eaa0b69112fd5d4f721ffc9671687e1d5d0b155c8620cf7546dbef94c0
FROM ${GO_BUILDER} AS envcheck
# 환경 검증 도구(common/envcheck, 정적 바이너리): 기동 때 계약 Env 스키마로 환경을 검증하고 기본값을 채운다
COPY --from=common . /src/
RUN cd /src && CGO_ENABLED=0 go build -trimpath -buildvcs=false -o /envcheck ./cmd/envcheck
FROM ${RESTIC_IMAGE} AS restic
FROM ${STEP_CA_IMAGE}
ARG COMMIT=unknown
ARG BOUNDARY_TAG=unknown
ARG JOBS_JSON
LABEL io.openit.jobs="${JOBS_JSON}" io.openit.service="step-ca" io.openit.revision="${COMMIT}" io.openit.contracts.boundary="${BOUNDARY_TAG}" io.openit.contracts.survey-schema="n/a" io.openit.model-runtime="n/a"
COPY --from=envcheck /envcheck /usr/local/bin/envcheck
# 데이터 주인 백업·복구 잡(pki-ca = /home/step): restic 은 잠금 digest 의 공식 이미지에서
COPY --from=restic /usr/bin/restic /usr/local/bin/restic
COPY --from=common --chmod=755 backup-job.sh /usr/local/bin/platform-backup-job
COPY --from=boundary_contracts schemas/CommonEnv.schema.json /etc/openit/schemas/
COPY --from=boundary_contracts schemas/StepCaEnv.schema.json /etc/openit/schemas/
COPY image/entrypoint.sh /usr/local/bin/openit-step-ca-entrypoint.sh
COPY --chmod=755 image/step-cert-perms.sh /usr/local/bin/step-cert-perms
# 상태 폴더는 Docker 표준 VOLUME 으로 선언한다(배치는 이미지 선언을 읽어 마운트하고 경로를 따로 알지 않는다): CA 키·설정 /home/step, (발급 토큰·인증서 폴더는 STEP_TOKENS_DIR·STEP_CERTS_DIR 로 받는 실행별 마운트다)
VOLUME ["/home/step"]
# 키 파일 그룹(StepCaEnv.STEP_CERT_GID 기본 10100): step 이 이 그룹의 구성원이라 root 없이 chgrp 할 수 있다. 다른 gid 는 deploy 의 group_add 로 보조 그룹을 받는다
USER root
RUN addgroup -g 10100 openit-certs && addgroup step openit-certs
USER step
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 CMD ["/usr/local/bin/openit-step-ca-entrypoint.sh", "health"]
ENTRYPOINT ["/usr/local/bin/openit-step-ca-entrypoint.sh"]
