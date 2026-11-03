# platform 감시(Prometheus + 규칙 + 대상 설정, ADR 0004). 공식 Prometheus 이미지(digest 고정)에 이 영역의 설정·규칙을 넣는다. alertmanager·exporter 는 공식 이미지를 그대로 쓴다(설정은 config/prometheus/).
ARG PROMETHEUS_IMAGE=docker.io/prom/prometheus@sha256:63805ebb8d2b3920190daf1cb14a60871b16fd38bed42b857a3182bc621f4996
FROM ${PROMETHEUS_IMAGE}
ARG COMMIT=unknown
ARG BOUNDARY_TAG=unknown
LABEL io.openit.service="monitoring" io.openit.revision="${COMMIT}" io.openit.contracts.boundary="${BOUNDARY_TAG}" io.openit.contracts.survey-schema="n/a" io.openit.model-runtime="n/a"
COPY config/prometheus/prometheus.yml /etc/prometheus/prometheus.yml
COPY config/prometheus/rules /etc/prometheus/rules
COPY config/prometheus/blackbox.yml config/prometheus/json-exporter.yml config/prometheus/alertmanager.yml /etc/prometheus/extra/
USER 65534
