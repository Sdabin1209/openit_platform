# platform 경계 문서

## 소유
공개 입구(사람·기기), 사람 인증(Keycloak, oauth2-proxy), 영역 게이트웨이 이미지, 인증서 발급(step-ca), 감시, 백업 저장소. 구성요소별 이미지: `scripts/build-image.sh` 의 variant(없음 = area-gateway, `public-ingress`, `monitoring`, `backup-store`, `step-ca`). Keycloak·oauth2-proxy 는 공식 이미지(영역 이미지 없음).

## 소비하는 계약
boundary-contracts v3.4.9(`requirements.txt` 고정): Exposure, BuildImageRequest/Result, ImageLabels, BoundaryError, HealthStatus. 시험은 고정 태그 소스를 `scripts/fetch-boundary-src.sh` 로 받는다(이웃 작업 트리에 기대지 않는다).

## 컴포넌트 입력 (영역 사이 계약이 아니라 platform 컴포넌트 계약)
**영역 게이트웨이**: `/etc/openit/exposure.json`(필수; 계약 위반 65, 없음 64), `/certs/tls.{crt,key}`, `/tmp` tmpfs. 환경: `AREA_GATEWAY_UPSTREAM`(127.0.0.1:8080), `AREA_GATEWAY_INGRESS_PORT`(443), `AREA_GATEWAY_EGRESS_PORT`(3128, loopback), `AREA_GATEWAY_EXPOSURE`, `AREA_GATEWAY_CERT_DIR`(기본 `/certs`). **`AREA_GATEWAY_CERT_DIR` 가 가리키는 폴더가 마운트되지 않으면 들어오는 쪽 listener 를 열지 않는 나가는 쪽 전용으로 동작한다**(ADR 0001 추가 결정). 사용자 101.
**공개 입구**: `/etc/openit/exposures/*.json`(65/64), `/etc/caddy/devices.caddy`, `/run/secrets/<upstream_token>`, `/etc/openit/pki/root_ca.crt`, TLS 출처 `GATEWAY_TLS_MODE`(internal|files|acme). 환경: `GATEWAY_HOSTS`, `GATEWAY_HOST_NAMES`, `AUTH_CHECK_TIMEOUT`, `LOGIN_RATE_EVENTS`, `INGRESS_EXPOSURES`. 사용자 10001, 포트 8443 / 평문 8080(`/healthz`).

## 장애 영향
- 공개 입구 정지: 사람·기기 모두 접근 불가(영역 사이 호출은 영향 없음).
- oauth2-proxy·Keycloak 정지: 사람 경로 503 UU(R3.12), 기기 경로는 영향 없음.
- 영역 게이트웨이 정지: 그 영역의 들어오는 호출과 나가는 호출이 모두 끊긴다.
