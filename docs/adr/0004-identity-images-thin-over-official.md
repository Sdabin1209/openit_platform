# 0004 사람 인증 이미지: 공식 이미지 위의 얇은 platform 이미지

- 상태: 채택(계약 3.4.10 에 따름. ADR 0003 의 "공식 이미지를 그대로 쓴다"를 이 점에서 대체한다)
- 맥락: deploy 가 `KC_*`(약 15개)·`OAUTH2_PROXY_*`(약 25개)·Keycloak `--config-file` 문법·realm 가져오기 파일을 직접 만들었다. 구조 규칙 1·6 위반이다 — 영역은 서로의 구조를 모르고 영역 간 입력은 계약 스키마로만 받는다.
- 결정: `identity`(Keycloak 위), `identity-proxy`(oauth2-proxy 위), `identity-db`(postgres:16 위) 세 이미지를 만든다. 입력은 계약 `IdentityEnv`·`IdentityProxyEnv`·`AreaDatabaseEnv` 뿐이다. 진입점 `identity-entry`(Go 정적 바이너리)가 제품 내부 설정을 만든다: realm 가져오기 파일(공개 주소·클라이언트 비밀·첫 관리자 암호 채움), `--config-file`(DB 암호·관리자 암호, 0600 tmpfs), `KC_*`, `OAUTH2_PROXY_*`.
- 왜 Go 인가: oauth2-proxy 이미지는 distroless 라 셸·파이썬이 없고, Keycloak 은 ubi-micro 라 파이썬이 없다. 정적 바이너리 하나가 두 이미지에서 같게 돈다. 계약 스키마 검증은 `common/envcheck` 라이브러리를 같이 쓴다(스키마 정본은 계약, 복사 없음).
- 왜 identity-db 는 셸인가: 공식 postgres 이미지에 셸이 있고 초기화(계정 생성)는 psql 이 가장 직접적이다. 계정 목록은 라벨 `io.openit.database`(DatabaseDeclaration)와 같은 파일 `/etc/openit/database.json` 에서 읽고, 시험이 둘이 같음을 확인한다.
- 값: 세션 최대 수명 8h(OWASP Session Management 의 업무일 길이 예시)·갱신 5m(Keycloak 액세스 토큰 5분과 맞춤)은 스키마 기본값이고 측정하지 않았다(ADR 0003).
- 검토한 대안: 공식 이미지 그대로 + 계약에 KC_* 를 올리기 — 제품 내부 이름이 영역 간 계약이 되어 제품 교체가 계약 변경이 된다. 파이썬을 이미지에 넣기 — ubi-micro·distroless 에 패키지 관리자가 없다.
- 결과: 얻는 것은 deploy 가 Keycloak·oauth2-proxy 를 몰라도 되는 것. 감수하는 것은 이미지 세 개와 Go 빌드 단계. identity-db 는 첫 초기화 때만 계정을 만든다(암호 교체는 아직 없다).
- 되돌리는 조건: 계약이 제품 내부 설정을 입력으로 바꿀 때.
