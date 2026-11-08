# ADR 0014: 영역 게이트웨이의 Exposure 시간 제한

## 상태
수용. ADR 0001의 들어오는 요청 시간 제한을 구체화한다.

## 맥락
영역 게이트웨이가 모든 요청의 유휴 상한을 120초로 고정해, 정상적인 release-gate 서버 마감 170초보다 먼저 요청을 끊었다. 경로 선언의 timeouts_ms도 읽지 않았다. E2E에서 공개 입구의 180초 헤더 대기까지 도달하지 못했다.

## 결정과 근거
Exposure.timeouts_ms를 경로마다 반영한다. dial은 클러스터 connect_timeout으로 매핑하며 같은 상류라도 값이 다르면 클러스터를 나눈다. response_header는 재시도 횟수 0의 retry_policy.per_try_timeout으로 최초 응답 헤더만 기다린다. 전체 응답 timeout은 0으로 두어 SSE·파일 전송 전체 시간을 헤더 대기로 제한하지 않는다. read가 있으면 route idle_timeout으로 활동 없는 스트림을 제한하고, 없으면 숨은 유휴 제한을 추가하지 않는다.

헤더 대기의 생략 기본값은 계약 CONVENTIONS 시간 상한 사슬이다: release-gate 180초, question-authoring 120초, ops-feedback 60초, 그 밖 55초. 연결 기본값은 1초다. 이는 계약에서 정한 시작값이며 실측 성능 수치가 아니다. 선언 없는 최종 경로와 배치용 접두사 경로에도 같은 기본값을 적용한다. 배치용 상류 선택이 선언의 시간·본문 제한을 우회하지 않게 한다.

Envoy 공식 문서의 RouteAction.timeout은 응답 전체, per_try_timeout은 응답을 시작하기 전, idle_timeout은 스트림 활동 사이를 제한한다. 따라서 헤더 대기와 전체 응답을 구분한다. read의 유휴 판정은 헤더·데이터 활동에 의해 갱신되며 요청 전송 중에도 적용된다.

근거: 계약 RUNTIME R3.3과 CONVENTIONS 시간 상한 사슬, [Envoy timeout 문서](https://www.envoyproxy.io/docs/envoy/latest/faq/configuration/timeouts), [RouteAction API](https://www.envoyproxy.io/docs/envoy/latest/api-v3/config/route/v3/route_components.proto).

### 후속 검토: 유휴 상한과 요청 헤더
`read < response_header`(헤더 값을 생략하면 사슬 기본값과 비교)는 헤더 대기 중 계약 밖 408을 만들 수 있으므로 기동 시 종료 65로 거부한다. 값을 조용히 늘리지 않는다. 이 교차 필드 관계는 현 Exposure JSON Schema에 표현돼 있지 않으며 생성기의 의미 검증과 시험으로 강제한다.

클라이언트의 Envoy 시간·재시도·대체 응답 제어 헤더는 ingress HCM의 표준 header_mutation 필터가 router보다 먼저 제거한다. 공개 입구를 거치지 않는 호출에도 적용한다. route request_headers_to_remove만 쓰면 router가 시간 헤더를 이미 읽은 뒤이므로 충분하지 않다([Envoy router.cc](https://github.com/envoyproxy/envoy/blob/v1.32.3/source/common/router/router.cc), finalTimeout 호출과 finalizeRequestHeaders 순서). 응답을 204로 바꾸는 timeout-alt-response도 제거한다.

## 검토한 대안
- 120초를 180초로만 올리기: 다른 경로와 명시 선언을 계속 무시하므로 기각.
- response_header를 route timeout에 넣기: 정상 SSE와 큰 응답을 전체 시간으로 끊으므로 기각.
- 모든 제한을 없애기: 무응답 상류를 계약 시간에 거부하지 못하므로 기각.

## 결과
정상 지연 응답이 서버 마감까지 기다릴 수 있고, 명시한 헤더 상한 초과는 기존 GatewayErrorResponse로 응답한다. 자동 재시도는 추가하지 않는다. 짧은 헤더 상한, 본문 스트리밍·유휴, 실제 121초 응답과 기본값·접두사·연결 값 분리 시험으로 검증한다.

## 되돌리는 조건
계약의 시간 사슬 또는 Exposure 의미가 변경되거나, 고정 Envoy 버전에서 헤더·읽기 제한을 더 직접 표현하는 표준 기능으로 바꿀 때 이 결정을 대체한다. 다시 고정 120초로 돌아가지 않는다.
