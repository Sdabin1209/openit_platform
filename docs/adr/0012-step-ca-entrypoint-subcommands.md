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
