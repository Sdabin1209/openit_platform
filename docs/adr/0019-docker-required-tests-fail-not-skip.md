# 0019. Docker 가 필요한 시험은 건너뛰지 않고 실패한다 / 최소 환경은 Docker 연결 이름을 전달한다

## 상태
채택(2026-11-09, codex C2 검토 P2).

## 맥락
`scripts/minenv.py` 가 `DOCKER_CONTEXT`·`DOCKER_TLS_VERIFY`·`DOCKER_CERT_PATH`·`SSH_AUTH_SOCK` 을 버려서, 다른 context·TLS·ssh 엔진에서 `have_docker()` 가 거짓이 되었다. 시험 파일의 `skipif(not have_docker())` 가 gateway·mTLS·변이 시험을 통째로 건너뛰고 rc=0 이 될 수 있었다. `scripts/smoke.sh` 의 허용 목록도 같았다.

## 결정
1. 허용 목록(`DOCKER_NAMES`)에 Docker CLI 공식 연결 변수 5개와 `SSH_AUTH_SOCK` 을 더한다. 값은 그대로 전달만 한다. `smoke.sh` 도 같은 이름을 넘긴다. `tests/test_minenv.py` 가 전달을 본다.
2. Docker 가 필요한 시험은 `skipif` 대신 fixture `docker_required`(tests/conftest.py)를 쓰고, 엔진에 닿지 못하면 실패한다.
3. `docker-env.sh` 가 빈 설정으로 바꾸면서 `DOCKER_CONTEXT` 를 풀어 `DOCKER_HOST` 로 준 경우 `DOCKER_CONTEXT` 는 내려놓는다(빈 설정에는 그 context 가 없다).

## 왜
- 표준: Docker CLI 문서의 환경 변수 `DOCKER_HOST`·`DOCKER_CONTEXT`·`DOCKER_TLS_VERIFY`·`DOCKER_CERT_PATH`·`DOCKER_CONFIG`, RUNTIME R9.1(허용 목록 최소 환경).
- 이 리포의 정본 시험은 Docker 가 있는 곳에서 돈다고 전제한다(README). 엔진이 없는데 통과하면 점검이 아니다(조용한 건너뜀 통과 금지).

## 검토한 대안과 버리는 이유
- skipif 유지 + 건너뛴 수 출력: 사람이 읽어야만 안다. rc 로 판정하는 규칙에 맞지 않아 버린다.
- 환경 변수로 건너뛰기 허용 스위치: 시험용 문을 두는 것이다. 버린다.

## 결과 / 되돌리는 조건
얻는 것: 엔진에 못 닿으면 rc≠0. 감수하는 것: Docker 없는 곳에서는 정적 시험(Docker 불필요)만 따로 돌려야 하며 전체 명령은 실패한다. Docker 없는 CI 를 정본으로 삼게 되면 새 ADR.
