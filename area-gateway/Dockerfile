# 영역 게이트웨이 이미지(platform, ADR 0001): 들어오는 쪽 TLS 종단(서비스 이름 인증서) + 나가는 쪽 HTTP CONNECT 터널(허용 목록은 그 영역의 Exposure.egress).
# 제품은 Envoy 공식 이미지(digest 고정). 이 이미지는 시작할 때 마운트된 Exposure 선언에서 Envoy 설정을 만들고 envoy 를 실행한다(entrypoint): 영역마다 이미지가 같고 입력만 다르다.
# 이미지 입력(배포 입력, 영역 사이 계약이 아니다):
#   /etc/openit/exposure.json   그 영역의 Exposure 선언(계약 스키마로 검증, 어기면 시작하지 않고 종료 코드 != 0)
#   /certs/tls.crt, /certs/tls.key   서비스 이름 인증서(파일이 바뀌면 재시작 없이 다시 읽는다)
#   AREA_GATEWAY_UPSTREAM       기본 상류(영역 안 컴포넌트) host:port. 기본 127.0.0.1:8080
#   AREA_GATEWAY_INGRESS_PORT   들어오는 쪽 TLS 포트. 기본 443
#   AREA_GATEWAY_EGRESS_PORT    나가는 쪽 CONNECT 포트(127.0.0.1 에만 연다). 기본 3128
#   /tmp (tmpfs)                만든 설정을 쓴다(읽기 전용 루트에서 돈다)
ARG ENVOY_IMAGE=envoyproxy/envoy@sha256:127e33c48c60be9a148cf9256d52e734ceda28aa344145023933116c7e524beb
FROM ${ENVOY_IMAGE}
ARG COMMIT=unknown
ARG BOUNDARY_TAG=unknown
USER 0
# 설정 생성기용 파이썬: 계약 패키지는 요청의 dependency_sources(소스 트리)에서만 설치한다(빌드 중 이웃 리포·SSH 없음). apt 는 Ubuntu 공식 저장소.
RUN apt-get -o APT::Sandbox::User=root update -qq \
 && apt-get -o APT::Sandbox::User=root install -y -qq --no-install-recommends python3 python3-pip python3-venv \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m venv /opt/gw
COPY --from=boundary_contracts . /tmp/boundary
RUN /opt/gw/bin/pip install -q --no-cache-dir /tmp/boundary && rm -rf /tmp/boundary
COPY gen-area-gateway-config.py /usr/local/bin/gen-area-gateway-config.py
COPY entrypoint.sh /usr/local/bin/area-gateway-entrypoint.sh
LABEL io.openit.service="area-gateway" \
      io.openit.revision="${COMMIT}" \
      io.openit.contracts.boundary="${BOUNDARY_TAG}" \
      io.openit.contracts.survey-schema="n/a" \
      io.openit.model-runtime="n/a"
USER 101
EXPOSE 443
ENTRYPOINT ["/usr/local/bin/area-gateway-entrypoint.sh"]
