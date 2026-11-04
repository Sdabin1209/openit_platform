# 0002 공개 입구: Caddy + Exposure 에서 생성한 경로 표

- 상태: 채택
- 맥락: 사람·기기의 공개 입구는 영역마다 다른 경로 표(인증 종류, 역할, 상류 토큰, 본문 상한)를 지켜야 하는데, 손으로 쓴 Caddyfile 은 영역 선언과 어긋난다(구조 점검 S9). 계약은 R2.1·R3.12·R3.23·R3.24·R10.4 의 응답 모양을 정한다.
- 결정: Caddy(공식 이미지 digest `locks/images.lock`)에 속도 제한 모듈(`mholt/caddy-ratelimit`)을 xcaddy 로 더해 빌드한다. 경로 표 `routes.caddy` 는 시작할 때 `/etc/openit/exposures/*.json` 에서 `ingress/gen-ingress-routes.py` 가 만든다. 선언이 계약 스키마를 어기거나 같은 공개 경로·메서드를 두 영역이 열면 시작하지 않는다(종료 65). `denied`·`machine-token` 경로와 영역의 `/healthz`·`/readyz`·`/metrics` 는 내보내지 않는다(CONVENTIONS 13절, 3.4.7·3.4.9). 선언에 없는 경로는 404 BoundaryError.
- 사람 인증(Keycloak `/auth/*`, oauth2-proxy `/oauth2/*`)의 공개 경로 선언은 identity·identity-proxy 이미지의 라벨 `io.openit.exposure`(정본 `identity/exposure-<서비스>.json`)가 정본이고, deploy 가 다른 영역 선언과 같이 `INGRESS_EXPOSURES` 로 준다. 공개 입구 이미지에 같은 사실을 따로 두지 않는다(두 곳에 쓰면 어긋나고, 같은 경로를 두 서비스가 열면 시작 거부 규칙에도 걸린다). 같은 경로를 겹치는 메서드로 두 서비스가 열면 시작하지 않는다(메서드를 적지 않은 선언은 모든 메서드). `/oauth2/auth`(내부 forward_auth 길)와 Keycloak master realm 은 Caddyfile 이 먼저 404 로 닫는다.
- 오류 본문의 `pipeline_schema_version` 은 계약 패키지의 현행 값을 시작 때 읽는다(`PIPELINE_SCHEMA_VERSION`, 환경 `PIPELINE_SCHEMA_VERSION` 으로 Caddy 가 치환).
- 왜: Exposure 가 경로의 정본이므로 생성하면 어긋날 수 없다. Caddy 는 이미 이 입구가 쓰던 서버이고 forward_auth(oauth2-proxy)와 mTLS 기기 인증이 표준 설정이다. 생성된 표는 `route {}` 안에 둔다 — Caddy 가 `handle` 을 경로 길이로 다시 정렬해 `/staff/*` 가 `/*` 에 가려졌기 때문이다(시험으로 확인).
- 값:
  - `AUTH_CHECK_TIMEOUT` 2s(인증 확인이 이 한도를 넘으면 503 UU, R3.12): 표준값 없음, **측정하지 않았다**(시작값).
  - `LOGIN_RATE_EVENTS` 30회/분/클라이언트 주소(로그인·가입 경로만, R10.4): 일반적인 로그인 속도 제한 관행의 시작값, **측정하지 않았다**. 주소 하나에 NAT 뒤 여러 사람이 있으면 낮을 수 있다.
  - 본문 상한 기본 8MiB(R3.5), 경로별 `max_body_bytes` 가 있으면 그 값.
- 검토한 대안: Envoy(영역 게이트웨이는 이것, ADR 0001) — 사람 인증(forward_auth)·기기 mTLS 를 이미 Caddy 로 검증한 설정이 있어 옮길 이득이 없다. 속도 제한 없이 두기 — R10.4 위반.
- 결과: 얻는 것은 선언과 입구의 일치. 감수하는 것은 xcaddy 빌드(약 2분)와 외부 모듈 하나. 414/431 은 Go net/http 가 앞단에서 평문 본문으로 답한다 — 계약이 허용한다(CONVENTIONS 92행).
- 되돌리는 조건: 모듈 유지가 끊기거나 Caddy 가 경로 정렬 동작을 바꿀 때.
