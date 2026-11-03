# platform

문진 시스템의 공용 서비스 영역: 공개 입구(사람·기기), 사람 인증(oauth2-proxy·Keycloak), 인증서 발급(step-ca), 감시, 백업 저장소, 그리고 **영역 게이트웨이 이미지**. 브리프: `docs/brief.md`.

## 1. 영역 게이트웨이 이미지
`bash scripts/build-image.sh <BuildImageRequest JSON>` (환경 준비: `bash scripts/setup-env.sh`; 요청에 dependency_sources.boundary 필요). 이미지 입력(Exposure 마운트·환경 변수)은 `area-gateway/Dockerfile` 머리말과 ADR 0001. 근거: `docs/adr/0001-area-gateway-envoy.md`.

## 5. 시험 상태
- `tests/test_area_gateway.py`(Docker 필요): 10건 통과 — 들어오는 쪽 TLS 종단·서비스 이름 인증서, 나가는 쪽 허용 상대 터널, 선언 밖 403 BoundaryError, 변이(egress 에서 빼면 거절), 출구 리스너가 loopback 전용, upstream_port 경로별 상류, 413 본문 상한, 잘못된/없는 선언은 시작 안 함.
- 공개 입구·사람 인증·인증서 발급·감시·백업 저장소: deploy 에서 옮기는 중(미완).

## ADR
- [0001 영역 게이트웨이: Envoy](docs/adr/0001-area-gateway-envoy.md)
