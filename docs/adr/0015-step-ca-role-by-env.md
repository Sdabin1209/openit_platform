# 0015. step-ca 이미지의 역할은 부명령이 아니라 환경 변수 STEP_ROLE 로 고른다

## 상태
채택(2026-11-05, 구현 커밋 e49ac67). [ADR 0012](0012-step-ca-entrypoint-subcommands.md)의 "진입점 `serve|root|token|cert|health` 부명령" 결정을 대체한다(Supersedes 0012 의 진입점 선택 부분). 0012 의 나머지 결정은 유효하다.

## 맥락
0012 는 같은 이미지가 부명령(`serve|root|token|cert <이름>`)으로 역할을 고르게 했다. 이 때문에 deploy 가 compose 의 `command` 로 이미지 부명령을 적었다. 계약 CHANGELOG 3.4.17 은 이를 구조 규칙 1 위반으로 규정한다: deploy 가 platform step-ca·감시 이미지의 역할을 compose command 로 고르고, user·healthcheck 도 직접 적었으며 헤드 경계 점검 규칙 8 이 77건을 찾았다. 역할을 고르는 계약 입력과 이미지가 HEALTHCHECK·USER 를 갖는다는 조항이 없었다.

## 결정
- 역할은 계약 `StepCaEnv.STEP_ROLE`(serve|root|token|cert)로 고른다. 이름 입력은 `STEP_CERT_NAME`(cert), `STEP_TOKEN_NAMES`(token), 키 그룹은 `STEP_CERT_GID`(기본 10100)다. 이름은 계약 3.4.17 이 정본이므로 여기에 값을 복사하지 않는다.
- 진입점(`pki/image/entrypoint.sh`)은 `StepCaEnv` 로 환경을 검증하고(`envcheck`, 위반 종료 64) `STEP_ROLE` 로 분기한다. 역할이 필요한 입력을 빠뜨리면(token 에 이름 없음, cert 에 이름 없음) 64 로 거부한다.
- 첫 인자 `health` 는 이미지 HEALTHCHECK 가 부르며 역할마다 의미가 다르다(serve=CA 응답, cert=만료 포함 검증, root=루트 파일 있음, token=토큰 있음). 첫 인자가 절대 경로면 잡 선언 argv 로 보고 그대로 실행한다(2026-11-06, 커밋 808410d).

## 왜
- 계약 CHANGELOG 3.4.17 의 CONVENTIONS 13절: 영역 이미지는 진입점·HEALTHCHECK·USER 를 갖고 역할은 Env 로 고른다. deploy 는 영역 이미지에 command·entrypoint·healthcheck·user 를 쓰지 않는다. 컴포넌트는 자기 입력 스키마 밖(이웃의 부명령 이름)을 알지 않는다(CLAUDE.md 구조 규칙 1·4).
- 이미지가 스스로 서므로 배치가 이미지 내부 구조를 알 필요가 없다.

## 검토한 대안과 버리는 이유
- 0012 의 부명령 유지: deploy 가 command 로 부명령을 적어야 하므로 위 77건의 위반이 계속된다.
- 역할마다 별도 이미지: 인증서 수명·검증 코드가 중복되고 이미지 수가 늘어난다. 이 대안을 비교한 기록은 찾지 못했다(이 ADR 이 추가로 든 것이다).

## 결과 / 되돌리는 조건
얻는 것: deploy 는 환경만 구성한다. 시험 `tests/test_step_ca.py`, `tests/test_env_contract.py` 가 STEP_ROLE 경로를 쓴다. 감수하는 것: 역할 추가가 계약 변경(StepCaEnv)을 요구한다. 계약이 역할 선택을 다시 부명령으로 바꾸면 새 ADR.
