# 변경 요청: Exposure 기본값을 기계가 읽는 칸으로

- 요청 영역: platform. 받는 쪽: 헤드(boundary-contracts).
- 무엇이 부족한가: `Exposure.routes[].max_body_bytes` 의 기본 8MiB(8388608)는 스키마 `description` 산문에만 있고 `default` 칸이 없다. 응답 헤더 대기의 사슬 기본값(release-gate 180s, question-authoring 120s, ops-feedback 60s, 그 밖 55s)은 CONVENTIONS.md 표에만 있고 패키지에 들어 있지 않다. 그래서 platform 의 공개 입구(`ingress/gen-ingress-routes.py`)와 영역 게이트웨이(`area-gateway/gen-area-gateway-config.py`)가 값을 사본으로 갖는다(D117 '같은 값은 한 번만').
- 제안(확인한 것이 아니라 제안): `max_body_bytes` 에 `"default": 8388608`, 사슬 표를 패키지 데이터(예: `data/time_chain.json`)로 내고 읽는 함수를 둔다. 받으면 platform 은 사본을 지우고 패키지에서 읽는다.
- 그 전까지의 보호: `tests/test_contract_defaults.py` 가 고정 태그의 계약 설명·CONVENTIONS 표와 사본을 대조한다.
