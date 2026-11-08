# 0018. 계약 5.0.0 반영: 사본은 계약에서 읽거나 계약과 대조한다

## 상태
채택(2026-11-08). 계약 v5.0.0(ID 타입 통일·계약 JSON 공통 규칙·입력 상한)에 맞춘다. [ADR 0013](0013-계약-4-기기-허용목록과-사용자-ID.md)의 구현 세부 중 기기 ID 정규식 위치만 대체한다(Supersedes 0013 의 Caddyfile 정규식 부분).

## 맥락
계약 5.0.0 은 같은 뜻의 타입을 한 번만 정의하고(D117) 영역 코드의 사본을 지우라고 한다. platform 에는 계약 값의 사본이 있었다: Caddyfile·`device-pki.sh` 의 기기 ID 정규식, 본문 상한 8MiB 두 곳, 응답 헤더 사슬 기본값, 설정 검증에서 오류 메시지에 선언 값을 싣는 곳, 직접 만든 `Draft202012Validator`(형식 검사 없음, 점검 `check-format-enforcement.py` 가 `ingress/device-auth.py` 를 잡았다).

## 결정
1. 계약 태그는 `requirements.txt` 한 곳에서 `v5.0.1` 로 올린다(5.0.0 으로 시작해 올렸다).
2. 기기 ID 정규식은 `ingress/gen-device-id-re.py` 가 계약 `DeviceAllowlist` 의 `device_id` 패턴에서 앵커를 떼어 낸다. entrypoint 가 `DEVICE_ID_RE` 로 내보내 Caddyfile 이 `{$DEVICE_ID_RE}` 로 쓰고, `device-pki.sh` 는 같은 스크립트를 부른다. 사본이 없다는 것을 `tests/test_contract_defaults.py` 가 본다.
3. 본문 상한 8MiB·연결 기본·응답 헤더 사슬 기본값은 계약 v5.0.1 `gateway_defaults()` 에서 읽는다. 5.0.0 에서는 산문뿐이라 사본과 대조 시험을 두었고, 변경 요청(`docs/change-requests/2026-11-08-exposure-machine-readable-defaults.md`)이 5.0.1 에 반영돼 사본을 지웠다. 시험은 사본 부재를 본다.
4. Exposure·허용 목록 파일은 `strict_json.loads` 와 `validate` 를 지나고, 오류에는 스키마 위치와 키워드만 싣는다(INTERFACES I7).
5. 영역 내부 스키마(`DeviceAuthRequest`)의 검증기는 계약 `schema_validator` 로 만든다(직접 만든 Draft202012Validator 와 감싸개는 없앴다).
6. 계약이 정한 조건(GATEWAY_HOSTS 형식)을 코드에서 지우고, 계약이 정하지 않은 조건은 `ingress/schemas/README.md` 표에 이유와 함께 둔다.

## 왜
- D117: 같은 값은 한 번만. 읽을 수 있는 것은 읽고, 읽을 수 없는 것은 어긋나면 시험이 실패하게 한다(규칙엔 점검을).
- R7: 컴포넌트가 낸 값은 받는 쪽이 다시 검증하지 않는다. 그래서 envcheck 가 이미 검증한 GATEWAY_HOSTS 를 다시 검사하지 않는다.
- INTERFACES I7: 오류에 값을 싣지 않는다. 선언 파일은 이웃 영역이 쓰므로 값이 로그에 남지 않게 한다.

## 검토한 대안과 버리는 이유
- Caddyfile 정규식을 느슨하게(`CN=([^,]+)`) 바꾸고 확인기에 맡기기: CN 에 `,` 이스케이프가 있는 주체에서 다른 값을 잘못 뽑을 수 있고, 현행 시험의 형식 게이트 동작이 바뀐다. 버린다.
- 사슬·본문 기본값을 `../boundary-contracts` 파일에서 직접 읽기: 이웃 리포 파일에 기대는 것이고 패키지에 없다. 버린다.

## 결과 / 되돌리는 조건
얻는 것: 계약 패턴과 기본값이 바뀌면 생성기가 자동으로 따라온다. 감수하는 것: 계약 패키지의 데이터 형태(gateway_defaults)에 생성기가 기댄다. 그 형태가 바뀌면 새 ADR.
