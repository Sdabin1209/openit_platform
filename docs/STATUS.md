# platform 상태

한 일: 영역 게이트웨이(Envoy), 공개 입구(생성 경로 표, R3.12·R10.4·431/414), 사람 인증(실제 Keycloak 스모크), 계약 v3.4.9 고정, 새 clone 시험.
남은 일: 감시·백업 저장소·step-ca(브랜치 wo-platform-ops, 두 번째 담당), 공개 입구 `/healthz` 스모크 스크립트 단독화, 두 번째 환경 확인, ADR 0004~ (그 구성요소).
막힌 것: 없음. 알려진 한계: 속도 제한·인증 확인 한도 값은 측정하지 않았다(ADR 0002). 431/414 본문은 전송 계층의 평문(계약 허용).

## 2026-11-08 계약 4 전환

- 기기 토큰 생성기를 제거하고 인증서 CN·serial을 매 요청 DeviceAllowlist로 확인한다. 부모 디렉터리 마운트로 원자적 교체를 반영하며 목록 오류는 503, 정상 목록 복원 뒤 회복한다(ADR 0013).
- Keycloak 사용자 프로필·공개 입구·사용자 등록 잡이 HumanUserId와 IdentityUsersConfig를 따른다. 영역 게이트웨이는 IPv6 loopback을 처리하고 백업 결과는 표준 JSON 인코딩 뒤 계약으로 검사한다.
- 확인: BC4.0.2 전체 92 pass, skip0. 실제 Keycloak·mTLS 회전/폐기·장애 회복·8종 이미지 스모크 통과. BC4.0.4 정식 설치/pip check 및 기기 확인기 단위 9 pass 완료.
- 최종 전체: BC4.0.4에서 `.venv/bin/python -m pytest --tb=short --maxfail=4 -rs -o addopts="" -q` 92 pass, skip0, rc0(1383.28s). 최종 `bash scripts/smoke.sh`도 rc0으로 통과했다(8종 이미지 라벨·비root, 해당 구성요소 기동/상태 확인). 실제 Keycloak 로그인은 앞선 동일 구현의 별도 스모크 결과이며 이 스모크에서 중복 실행하지 않는다. 구현 커밋을 헤드에 보내 교차검토한다. 전체 프로젝트 E2E 미실행.
