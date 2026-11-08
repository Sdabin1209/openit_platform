# platform

문진 시스템의 공용 서비스 영역: 공개 입구(사람·기기), 사람 인증(oauth2-proxy·Keycloak), 인증서 발급(step-ca), 감시, 백업 저장소, 그리고 **영역 게이트웨이 이미지**. 브리프: `docs/brief.md`.

## 1. 영역 게이트웨이 이미지
`bash scripts/build-image.sh <BuildImageRequest JSON>` (환경 준비: `bash scripts/setup-env.sh`; 요청에 dependency_sources.boundary 필요). 이미지 입력(Exposure 마운트·환경 변수)은 `area-gateway/Dockerfile` 머리말과 ADR 0001. 근거: `docs/adr/0001-area-gateway-envoy.md`.

## 2. 공개 입구와 사람 인증
공개 입구: `bash scripts/build-image.sh`(variant `public-ingress`), 경로 표는 마운트된 Exposure 에서 생성(ADR 0002). 사람 인증: `identity/`(ADR 0003). 입력과 장애 영향: `docs/boundary.md`.

## 5. 시험 상태 (WSL2 한 환경에서만 확인, 두 번째 환경은 아직)
- `tests/test_area_gateway.py`(Docker 필요, 지금 빌드한 이미지로): 영역 게이트웨이. `tests/test_ingress_routes.py`: 경로 표 생성 규칙. 시험 개수는 적지 않는다(`pytest --collect-only -q` 가 정본이고 문서에 쓰면 어긋난다).
- `ingress/tests/test-gateway-faults.sh`(R2.1 앱 응답 보존·R3.5 413·R3.6 431/414·R3.1/R3.2 상류 멈춤 503+Retry-After·R4.1 복구·R3.3 504)와 `ingress/tests/test-device-mtls.sh`(기기 인증서 mTLS, PUBLIC_API F절): 둘 다 `tests/test_ingress_shell.py` 로 test 줄기에 오르고 변이(503 매핑 제거, 413 상한 해제, 다른 CA 를 기기 CA 로 주는 mTLS 변이)가 실패하는지도 본다.
- `ingress/tests/test-gateway-auth.sh`: 공개 입구(가짜 oauth2-proxy) 인증 계약, R3.12, R10.4, 431/414.
- `identity/tests/test-idp-smoke.sh`: 실제 Keycloak·oauth2-proxy 로그인·역할·승인 대기·가입 승인.
- Go 시험(`common/envcheck`): `bash scripts/go-test.sh`(Docker 필요, 호스트 go 불필요).
- 감시·백업 저장소·인증서 발급(step-ca): `tests/test_monitoring.py`, `tests/test_backup_store.py`, `tests/test_step_ca.py`(Docker 필요). 배포 입력은 `docs/COMPONENTS.md`.

## ADR
- [0001 영역 게이트웨이: Envoy](docs/adr/0001-area-gateway-envoy.md)
- [0002 공개 입구: Caddy + 생성한 경로 표](docs/adr/0002-public-ingress-caddy.md)
- [0003 사람 인증: Keycloak + oauth2-proxy](docs/adr/0003-human-auth-keycloak-oauth2-proxy.md)
- [0010 감시](docs/adr/0010-monitoring-prometheus-one-image.md)
- [0011 백업 저장소](docs/adr/0011-backup-store-rest-server-private-repos.md)
- [0012 인증서 발급](docs/adr/0012-step-ca-entrypoint-subcommands.md)
- [0004 사람 인증 이미지: 공식 이미지 위의 얇은 이미지](docs/adr/0004-identity-images-thin-over-official.md)
- [0005 환경 검증: envcheck](docs/adr/0005-envcheck-contract-env-validation.md)
- [0013 계약 4: 기기 허용 목록과 사용자 ID](docs/adr/0013-계약-4-기기-허용목록과-사용자-ID.md)
- [0014 영역 게이트웨이 시간 제한](docs/adr/0014-area-gateway-exposure-timeouts.md)
- [0015 step-ca 역할은 환경 변수로 고른다(0012 일부 대체)](docs/adr/0015-step-ca-role-by-env.md)
- [0016 기기 허용 목록 ADR 보완(0013 Nygard 항목)](docs/adr/0016-device-allowlist-nygard-supplement.md)
- [0017 영역 게이트웨이 시간 시험은 정적으로(0014 검증 방법 대체)](docs/adr/0017-area-gateway-timeout-tests-static.md)
- [0018 계약 5.0.0 반영: 사본은 계약에서 읽거나 대조한다](docs/adr/0018-contract-5-adoption.md)
