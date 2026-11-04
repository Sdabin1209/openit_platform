# platform 백업 저장소(restic rest-server, https, HTTP 기본 인증 RFC 7617, 영역별 경로·자격; RUNTIME R10.1, ADR 0011). 공식 rest-server 이미지(digest 고정).
# 입력(docs/COMPONENTS.md): /run/tls/{tls.crt,tls.key}(ro), /run/secrets/areas/<영역>(영역별 자격 한 줄, ro), /data(rw 볼륨, uid 65534), /tmp(tmpfs). 환경 변수는 선택(OPENIT_BACKUP_PORT 기본 8000).
ARG REST_SERVER_IMAGE=docker.io/restic/rest-server@sha256:d2aff06f47eb38637dff580c3e6bce4af98f386c396a25d32eb6727ec96214a5
FROM ${REST_SERVER_IMAGE}
ARG COMMIT=unknown
ARG BOUNDARY_TAG=unknown
LABEL io.openit.service="backup-store" io.openit.revision="${COMMIT}" io.openit.contracts.boundary="${BOUNDARY_TAG}" io.openit.contracts.survey-schema="n/a" io.openit.model-runtime="n/a"
COPY --chmod=755 entrypoint.sh /usr/local/bin/openit-backup-store-entrypoint.sh
USER 65534
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/openit-backup-store-entrypoint.sh"]
