# platform 영역 브리프 (헤드, 2026-11-04)

## 왜 이 영역이 있나
deploy 는 배치 도구다(이미지·설정을 놓고 띄운다). 실행 중 요청·데이터 경로에 끼는 공용 서비스는 이 영역이 소유한다(구조 점검 head/docs/STRUCTURE_AUDIT_2026-11-04.md S1~S8, S18~S20; 계약 boundary-contracts v3.4.4 CONVENTIONS 13절).

## 소유하는 것
- 공개 입구(사람·기기의 게이트웨이), 사람 인증(oauth2-proxy·Keycloak 과 그 데이터베이스), 인증서 발급(step-ca·발급·갱신), 감시(Prometheus·alertmanager·exporter), 백업 저장소.
- 영역 게이트웨이 이미지(들어오는 쪽 TLS 종단 + 나가는 쪽 CONNECT 터널, 허용 목록은 각 영역 Exposure.egress). 영역마다 하나씩 배치된다(배치는 deploy).

## 영역 사이 입출력(정본은 boundary-contracts v3.4.4)
RUNTIME R2.1·R3 전부(게이트웨이 열)·R3.12·R3.23·R3.24·R10.4·R10.6·R10.11(수집 쪽)·R1.8(출구), CONVENTIONS 6·13절, HumanAuthEndpoints·HumanUserInfo·GatewayError·Exposure·CommonEnv.

## 하지 않는 것
- 다른 영역의 데이터베이스(영역 컴포넌트다), 잡을 언제 띄우는가(deploy 배포 설정).
