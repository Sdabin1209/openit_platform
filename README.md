# platform

문진 시스템의 공용 서비스 영역: 공개 입구(사람·기기), 사람 인증(oauth2-proxy·Keycloak), 인증서 발급(step-ca), 감시, 백업 저장소, 그리고 **영역 게이트웨이 이미지**. 브리프: `docs/brief.md`.

## 1. 영역 게이트웨이 이미지
`bash scripts/build-image.sh <BuildImageRequest JSON>` (환경 준비: `bash scripts/setup-env.sh`; 요청에 dependency_sources.boundary 필요). 이미지 입력(Exposure 마운트·환경 변수)은 `area-gateway/Dockerfile` 머리말과 ADR 0001. 근거: `docs/adr/0001-area-gateway-envoy.md`.

## 2. 공개 입구와 사람 인증
공개 입구: `bash scripts/build-image.sh`(variant `public-ingress`), 경로 표는 마운트된 Exposure 에서 생성(ADR 0002). 사람 인증: `identity/`(ADR 0003). 입력과 장애 영향: `docs/boundary.md`.

## 5. 시험 상태 (WSL2 한 환경에서만 확인, 두 번째 환경은 아직)
- `tests/test_area_gateway.py`(Docker 필요, 지금 빌드한 이미지로): 영역 게이트웨이 11건. `tests/test_ingress_routes.py`: 경로 표 생성 규칙 6건.
- `ingress/tests/test-gateway-auth.sh`: 공개 입구(가짜 oauth2-proxy) 인증 계약, R3.12, R10.4, 431/414.
- `identity/tests/test-idp-smoke.sh`: 실제 Keycloak·oauth2-proxy 로그인·역할·승인 대기·가입 승인.
- 감시·백업 저장소·인증서 발급(step-ca): `tests/test_monitoring.py`, `tests/test_backup_store.py`, `tests/test_step_ca.py`(Docker 필요). 배포 입력은 `docs/COMPONENTS.md`.

## ADR
- [0001 영역 게이트웨이: Envoy](docs/adr/0001-area-gateway-envoy.md)
- [0002 공개 입구: Caddy + 생성한 경로 표](docs/adr/0002-public-ingress-caddy.md)
- [0003 사람 인증: Keycloak + oauth2-proxy](docs/adr/0003-human-auth-keycloak-oauth2-proxy.md)
- [0010 감시](docs/adr/0010-monitoring-prometheus-one-image.md)
- [0011 백업 저장소](docs/adr/0011-backup-store-rest-server-private-repos.md)
- [0012 인증서 발급](docs/adr/0012-step-ca-entrypoint-subcommands.md)
