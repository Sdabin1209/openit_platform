# platform 감시 이미지(ADR 0010). 공식 Prometheus 이미지(digest 고정)에 같은 방식으로 고정한 alertmanager·blackbox_exporter·node_exporter·json_exporter 의 정적 바이너리를 더하고
# 이 영역의 설정·규칙을 넣는다. 한 이미지, 컨테이너마다 역할 하나(`prometheus|alertmanager|blackbox|node|json`): 배치는 설정 파일 경로를 알 필요가 없다(구조 규칙 1). 입력은 docs/COMPONENTS.md.
ARG PROMETHEUS_IMAGE=docker.io/prom/prometheus@sha256:63805ebb8d2b3920190daf1cb14a60871b16fd38bed42b857a3182bc621f4996
ARG ALERTMANAGER_IMAGE=docker.io/prom/alertmanager@sha256:27c475db5fb156cab31d5c18a4251ac7ed567746a2483ff264516437a39b15ba
ARG BLACKBOX_IMAGE=docker.io/prom/blackbox-exporter@sha256:a50c4c0eda297baa1678cd4dc4712a67fdea713b832d43ce7fcc5f9bea05094d
ARG NODE_EXPORTER_IMAGE=docker.io/prom/node-exporter@sha256:d00a542e409ee618a4edc67da14dd48c5da66726bbd5537ab2af9c1dfc442c8a
ARG JSON_EXPORTER_IMAGE=quay.io/prometheuscommunity/json-exporter@sha256:3a777171d39ad435cb39519e84e0a8b5c63c7e716cc06011f8140cfaabfc1baf
ARG GO_BUILDER=docker.io/library/caddy@sha256:c4cd20eaa0b69112fd5d4f721ffc9671687e1d5d0b155c8620cf7546dbef94c0
FROM ${GO_BUILDER} AS envcheck
# 환경 검증 도구(common/envcheck, 정적 바이너리): 기동 때 계약 Env 스키마로 환경을 검증하고 기본값을 채운다
COPY --from=common . /src/
RUN cd /src && CGO_ENABLED=0 go build -trimpath -buildvcs=false -o /envcheck ./cmd/envcheck
FROM ${ALERTMANAGER_IMAGE} AS alertmanager
FROM ${BLACKBOX_IMAGE} AS blackbox
FROM ${NODE_EXPORTER_IMAGE} AS node
FROM ${JSON_EXPORTER_IMAGE} AS json
FROM ${PROMETHEUS_IMAGE}
ARG COMMIT=unknown
ARG BOUNDARY_TAG=unknown
LABEL io.openit.service="monitoring" io.openit.revision="${COMMIT}" io.openit.contracts.boundary="${BOUNDARY_TAG}" io.openit.contracts.survey-schema="n/a" io.openit.model-runtime="n/a"
COPY --from=alertmanager /bin/alertmanager /bin/amtool /bin/
COPY --from=blackbox /bin/blackbox_exporter /bin/
COPY --from=node /bin/node_exporter /bin/
COPY --from=json /bin/json_exporter /bin/
COPY --from=envcheck /envcheck /usr/local/bin/envcheck
COPY --from=boundary_contracts schemas/MonitoringEnv.schema.json /etc/openit/schemas/
COPY config/prometheus.yml config/alertmanager.yml config/blackbox.yml config/json-exporter.yml /etc/openit/monitoring/
COPY config/rules /etc/openit/monitoring/rules
COPY --chmod=755 entrypoint.sh /usr/local/bin/openit-monitoring.sh
# 상태 폴더는 Docker 표준 VOLUME 으로 선언한다: 시계열 /prometheus, 경보 상태 /alertmanager
USER root
RUN mkdir -p /prometheus /alertmanager && chown 65534:65534 /prometheus /alertmanager
VOLUME ["/prometheus", "/alertmanager"]
USER 65534
ENTRYPOINT ["/usr/local/bin/openit-monitoring.sh"]
CMD ["prometheus"]
