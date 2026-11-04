# 0012. 인증서 발급: step-ca 이미지에 부명령 진입점

## 상태
채택(계약 RUNTIME R3.11·R4.6). 인증서 수명 24h·갱신 12h 는 deploy 에서 옮긴 시작값이고 측정 안 함.

## 맥락
서비스 인증서는 step-ca 가 발급하고 갱신한다. 발급기관이 멈춰도 발급된 인증서의 유효 기간 안에서는 출력이 바뀌지 않고(R3.11), 서버 전체가 멈췄다 만료 뒤 켜져도 사람 손 없이 재발급된다(R4.6). deploy 는 이 셸 한 줄을 compose 에 서비스마다 들고 있었다.

## 결정
- 변형 `step-ca`: 공식 `smallstep/step-ca`(digest 고정) + 진입점 `serve|root|token|cert|health`. 같은 이미지가 CA, 루트 내보내기, 일회용 토큰(OTT) 발급, 서비스 인증서 받기·갱신을 한다. 환경 변수 `STEP_CERT_NOT_AFTER`·`STEP_RENEW_EXPIRES_IN` 은 수명 조절용(기본: 인증기관 기본 24h, 12h).
- `cert`: `step certificate verify`(만료 포함)에 실패하면 토큰으로 재발급, 이어서 `step ca renew --daemon`. 파일 존재만 보면 만료 뒤 renew 가 거부되어 복구 못 한다(deploy ADR 0060 의 측정).
- 비밀번호는 파일로만 받고 `step ca init` 출력은 버린다(공식 entrypoint 의 `DOCKER_STEPCA_INIT_*` 는 비밀번호를 로그에 찍는다).

## 왜
`step ca renew --daemon` 은 인증기관이 닿지 않아도 기존 인증서를 그대로 두고 재시도하므로 R3.11 을 만족한다. 이미지에 넣어 두면 deploy 가 스크립트를 소유하지 않는다(구조 규칙 1).

## 검토한 대안과 버리는 이유
- ACME 도전(사이드카가 직접): 서버를 나누면 사이드카→CA 경로만 필요한 토큰 방식이 단순하다(deploy 측 결정을 따른다).
- cert-manager/Vault PKI: 단일 서버 배포에 과하다.

## 결과 / 되돌리는 조건
얻는 것: 시험이 이미지로 돈다(`tests/test_step_ca.py`). 감수하는 것: CA 복귀 뒤 갱신 재개 시각은 step 데몬의 재시도 지터에 달려 시험이 단언하지 않는다. 사설 PKI 를 조직 PKI 로 바꾸면 새 ADR.

## 추가 결정 (3.4.17): 갱신은 임시 파일 + rename, 데몬을 쓰지 않는다
- 맥락: `step ca renew --daemon --exec <모드 복구>` 는 갱신이 파일을 바꾼 뒤 후처리로 모드를 맞춰, 그 사이 그룹으로 읽는 컨테이너(공개 입구·DB)가 키를 못 읽을 수 있었다.
- 결정: cert 역할이 5초 주기로 `step certificate needs-renewal`(남은 수명이 `STEP_RENEW_EXPIRES_IN` 보다 짧은가)을 보고, 같은 키로 새 인증서를 같은 폴더의 임시 파일에 받아 0644 로 맞춘 뒤 rename(2)으로 바꿔 넣는다. 첫 발급도 임시 파일에서 키 0640·그룹 `STEP_CERT_GID` 를 맞춘 뒤 키, 인증서 순서로 rename 한다. 키는 갱신에 쓰이지 않는다.
- 왜: POSIX rename 은 원자적이라 읽는 쪽이 완성된 파일만 본다(RUNTIME OUT-FILE 과 같은 방식). 인증기관이 멈춰 있으면 갱신이 실패해도 기존 인증서를 그대로 두고 다음 주기에 다시 한다(R3.11).
- 대안: `--daemon --exec` 후처리 — 위 틈이 남는다. 점검 주기 5초는 측정하지 않은 값이다(시험이 쓰는 40초 수명의 갱신을 잡으려면 짧아야 한다).
- 시험: `tests/test_step_ca.py` — 다른 uid·같은 그룹 컨테이너가 45초 동안(여러 번 갱신) 키를 계속 읽어 한 번도 실패하지 않는다. 변이: 갱신 뒤 키를 제자리에서 0600 으로 두었다 되돌리는 방식이면 읽기가 실패한다.
