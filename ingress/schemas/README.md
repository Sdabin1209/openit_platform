# platform 스키마 안내

이 폴더의 스키마는 platform 안에서만 도는 것이다(공개 입구 안 Caddy와 기기 확인기 사이, `DeviceAuthRequest`). 계약 칸은 `x-contract` 로 위임하고 사본을 두지 않는다. `serial_decimal` 의 패턴은 계약에 같은 뜻의 칸이 없는 Caddy 속성(10진 일련번호)이라 여기서 정의한다(근거: 설명란, ADR 0013·0016).

## 스키마 밖 조건
계약 스키마로 표현되지 않아 코드가 거부하는 조건과 그 이유다(D117). 계약 5.0.0 에서 `validate("Exposure", …)` 로 직접 확인했다: 아래 1·2 는 계약이 받아들이는 값이다.

| # | 어디 | 조건 | 거부 동작 | 이유 / 근거 |
|---|---|---|---|---|
| 1 | `area-gateway/gen-area-gateway-config.py` `route_action` | `timeouts_ms.read >= response_header`(생략 시 사슬 기본값) | 종료 65 | 짧으면 헤더 대기 중 계약 밖 408 이 난다. 교차 필드 관계라 JSON Schema 로 표현하지 못한다. ADR 0014 |
| 2 | 같은 곳 | `response_header - dial >= 2ms` | 종료 65 | 영역 게이트웨이의 내부 헤더 대기가 공개 입구 상한보다 엄격히 짧아야 한다(여유 1ms 를 빼도 0 이 되면 Envoy 무제한). ADR 0014 R2 |
| 3 | `ingress/gen-ingress-routes.py` | `auth.kind == device` 인데 `upstream_token` 없음 | 종료 65 | 계약 스키마가 조건부 필수로 두지 않았다. 기기 경로는 서비스 토큰 없이 영역으로 갈 수 없다(PUBLIC_API F절). 계약에 칸을 요청할 후보 |
| 4 | 같은 곳 | 같은 공개 경로를 두 서비스가 연다 / 한 경로·메서드에 인증 종류가 섞인다 | 종료 | 여러 선언 파일 사이의 유일성이라 파일 하나를 검증하는 스키마가 표현하지 못한다 |
| 5 | `ingress/device-auth.py` | `device_id` 중복 | 시작 거부, 시작 뒤에는 503 | 계약 DeviceAllowlist 설명이 "스키마로 표현할 수 없는 유일성, 소비자가 강제한다"고 정했다 |
| 6 | `ingress/entrypoint.sh` | 기기 CA 파일이 PEM 인증서가 아님 | 종료 64 | 값이 아니라 파일 내용 상태(스키마 대상 아님). 틀린 파일로 mTLS 가 모든 기기를 거부하는 것을 시작 때 알린다 |
| 7 | `identity/entry/main.go` | `IDENTITY_DB_URL_FILE` 내용이 암호가 든 libpq URI | 종료 64 | 환경 값이 아니라 비밀 파일의 내용이다(스키마는 파일 경로만 안다) |

계약이 정한 조건은 코드에 두지 않는다. 이번에 지운 것: `ingress/gen-host-names.py` 의 GATEWAY_HOSTS 형식 검사(PublicIngressEnv 패턴이 entrypoint 의 envcheck 에서 먼저 거부한다).
