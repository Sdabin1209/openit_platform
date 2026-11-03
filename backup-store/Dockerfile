# platform 백업 저장소(restic REST 서버, append-only, TLS, HTTP 기본 인증; RUNTIME R10.1, ADR 0005). 공식 rest-server 이미지(digest 고정). 인증서·htpasswd·데이터는 배치가 준다.
ARG REST_SERVER_IMAGE=docker.io/restic/rest-server@sha256:d2aff06f47eb38637dff580c3e6bce4af98f386c396a25d32eb6727ec96214a5
FROM ${REST_SERVER_IMAGE}
ARG COMMIT=unknown
ARG BOUNDARY_TAG=unknown
LABEL io.openit.service="backup-store" io.openit.revision="${COMMIT}" io.openit.contracts.boundary="${BOUNDARY_TAG}" io.openit.contracts.survey-schema="n/a" io.openit.model-runtime="n/a"
USER 65534
ENTRYPOINT ["rest-server"]
CMD ["--path", "/data", "--listen", ":8000", "--append-only", "--htpasswd-file", "/run/htpasswd", "--private-repos=false", "--tls", "--tls-cert", "/run/tls/tls.crt", "--tls-key", "/run/tls/tls.key"]
