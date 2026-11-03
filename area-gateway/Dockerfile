# 영역 게이트웨이 이미지(platform, ADR 0001): 들어오는 쪽 TLS 종단(서비스 이름 인증서) + 나가는 쪽 HTTP CONNECT 터널(허용 목록은 그 영역의 Exposure.egress).
# 제품은 Envoy 공식 이미지(digest 고정)다. 설정은 영역마다 다르므로 이미지에 넣지 않고 배치가 /etc/envoy/envoy.yaml(+ sds.yaml, /certs)로 준다:
# 설정은 scripts/gen-area-gateway-config.py 가 그 영역의 Exposure 선언에서 만든다. 비루트, 읽기 전용 루트에서 돈다.
ARG ENVOY_IMAGE=envoyproxy/envoy@sha256:127e33c48c60be9a148cf9256d52e734ceda28aa344145023933116c7e524beb
FROM ${ENVOY_IMAGE}
ARG COMMIT=unknown
ARG BOUNDARY_TAG=unknown
LABEL io.openit.service="area-gateway" \
      io.openit.revision="${COMMIT}" \
      io.openit.contracts.boundary="${BOUNDARY_TAG}" \
      io.openit.contracts.survey-schema="n/a" \
      io.openit.model-runtime="n/a"
USER 101
EXPOSE 443 3128
ENTRYPOINT ["envoy"]
CMD ["-c", "/etc/envoy/envoy.yaml"]
