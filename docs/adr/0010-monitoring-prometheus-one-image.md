# 0010. 감시: Prometheus + exporter 를 한 이미지, 역할 진입점

## 상태
채택(계약 boundary-contracts v3.4.9 RUNTIME R10.11·R5.1). 측정하지 않은 값은 "측정 안 함"으로 적었다.

## 맥락
영역 서비스의 `/metrics` 를 수집하고(영역 게이트웨이를 지난 TLS, 10초 안, 실패는 `up=0`), 정적 화면 서버는 `/readyz` 탐침으로만 본다. `/healthz`·`/readyz` 는 상태 코드와 본문을 함께 본다(R5.1). 경보 규칙은 영역 내부 사실이다(R8.2 폐지).

## 결정
- 이미지 변형 `monitoring` 하나에 prometheus·alertmanager·blackbox_exporter·json_exporter·node_exporter 를 넣고(각 공식 이미지를 digest 로 고정해 정적 바이너리만 `COPY --from`), 컨테이너마다 역할 하나를 인자로 고른다(`prometheus|alertmanager|blackbox|json|node|check`). 설정·규칙은 이미지 안(`/etc/openit/monitoring`).
- 수집 대상은 배치가 파일(`targets/metrics.yml, readyz.yml, public.yml, gate.yml`, file_sd)로 준다. 서비스 목록을 이미지에 박지 않는다(구조 규칙 1).
- `area-metrics` 잡: https, 루트 인증서로 검증, `scrape_timeout: 10s`(R10.11 의 10초를 명시). 실패(초과·연결 실패·200 아님)는 Prometheus 표준대로 `up=0`.
- `probe-readyz`: blackbox 모듈 `readyz`(2xx + 본문 `"status"` 정규식). 빈 200 은 실패.
- 수집 주기 1m, 보존 15d, `for:` 값은 시작값이고 측정 안 함. 임계값(디스크 80/90%, 연결 실패 1/3회, 900초, 2배+60초, 환자 턴 p95 2초, 모델 호출 합 1.5초)은 옛 점검·계약 목표(METRICS.md)에서 왔다.

## 왜
- Prometheus pull 모델·`up` 지표·`scrape_timeout` 은 R10.11 이 그대로 기대하는 표준 동작이다.
- 한 이미지·역할 인자: 배치(deploy)가 이미지별 명령줄·설정 경로를 알 필요가 없고, 설정과 규칙의 버전이 이미지 하나의 리비전으로 묶인다. `promtool`/`amtool` 도 같은 이미지에 있어 설정 점검(`check`)이 이미지 안에서 된다.

## 검토한 대안과 버리는 이유
- 공식 이미지 5개를 그대로 쓰고 설정을 배치가 마운트: 설정 경로·플래그를 deploy 가 알게 되어 영역 경계(구조 규칙 1)가 흐려지고 설정 버전이 어긋난다.
- 이미지 5개를 각각 빌드: 같은 설정 묶음을 5번 복사하고 변형이 늘어 빌드·라벨 관리가 커진다.
- VictoriaMetrics/Grafana Agent: 규칙 시험 도구(`promtool test rules`)와 기존 규칙을 그대로 쓸 수 없어 이전 비용이 이득보다 크다.

## 결과
얻는 것: 설정 점검·규칙 시험이 이미지 안에서 돈다. 감수하는 것: 5개 프로젝트의 업스트림 보안 갱신을 한 이미지에서 같이 올려야 한다.

## 되돌리는 조건
바이너리 호환 문제(공식 이미지의 `/bin/<x>` 위치 변경)나 이미지 크기가 문제가 될 때 변형을 나눈다.
