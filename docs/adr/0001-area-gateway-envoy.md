# 0001. 영역 게이트웨이 이미지: Envoy (들어오는 쪽 TLS 종단 + 나가는 쪽 CONNECT 터널)

## 상태
채택(계약 boundary-contracts v3.4.6 CONVENTIONS 13절, RUNTIME R1.1·R1.8·R6.2). 측정하지 않은 값은 "측정 안 함"으로 적었다.

## 맥락
서비스를 가진 영역마다 게이트웨이가 하나 있다. 들어오는 쪽은 서비스 이름 인증서로 TLS 를 끝내고 영역 안 컴포넌트로 넘긴다. 나가는 쪽은 영역 안 컴포넌트의 영역 밖 호출을 HTTP CONNECT 터널(RFC 9110 9.3.6)로 받아, 그 영역 `Exposure.egress` 에 선언한 상대에게만 열고 그 밖은 403 `PERMISSION_DENIED`(`details.reason=EGRESS_DENIED`)로 거절한다. TLS 는 호출 컴포넌트와 받는 영역 게이트웨이 사이에서 끝까지 유지되므로 터널은 TLS 를 풀지 않는다.

## 결정
- 제품은 **Envoy 공식 이미지(`envoyproxy/envoy`, digest 고정)** 다. 영역마다 설정만 다르다: `scripts/gen-area-gateway-config.py` 가 그 영역의 Exposure 선언(계약 스키마로 검증)과 upstream 주소에서 설정을 만든다. 이미지에는 설정을 넣지 않는다(배치가 `/etc/envoy/envoy.yaml`, `sds.yaml`, `/certs` 로 준다).
- 인증서는 파일 SDS(`watched_directory`)로 읽어 인증서 갱신(ADR 0060, `step ca renew`) 때 재시작·reload 없이 새 파일을 쓴다.
- 허용 목록은 `:authority` 정확 일치(`<서비스>:443`), `external:backup` 은 `backup-store:443`, `external:web-push` 는 점 있는 공인 이름의 `:443` 정규식이다.
- 이미지는 비루트(101), 읽기 전용 루트에서 돈다. 라벨은 `io.openit.service=area-gateway`.

## 왜
- CONNECT 터널을 표준 기능(`connect_matcher`, `dynamic_forward_proxy`)으로 하고 허용 목록·거절 본문을 설정으로 선언할 수 있다. 시험(`tests/test_area_gateway.py`)이 실제 이미지로 허용·거절·변이를 확인했다.
- 파일 SDS 로 인증서 교체를 다시 읽는다(Caddy 는 설정이 그대로면 reload 를 건너뛰는 결함을 겪었다: deploy ADR 0060 실험 C6).

## 검토한 대안과 버리는 이유
- **Caddy**: CONNECT 터널(forward proxy)이 표준 이미지에 없다(별도 플러그인 빌드 필요). 버린다.
- **Squid / tinyproxy**: CONNECT 허용 목록은 쉬우나 들어오는 쪽 TLS 종단과 사이드카 역할을 한 제품으로 못 한다. 영역마다 두 제품이 된다. 버린다.
- **HAProxy**: CONNECT 터널을 `http-request` 규칙으로 할 수 있으나 403 본문·SDS 파일 감시가 Envoy 만큼 선언적이지 않다. 버린다.

## 결과
- 얻는 것: 한 제품으로 두 방향, 설정은 계약 선언에서 생성. 감수: Envoy 설정이 길고(생성기가 감춘다) 이미지가 크다(측정 안 함).
- 미확인: `Exposure.routes` 에 따른 들어오는 쪽 경로별 동작은 이 이미지가 하지 않는다(영역 안 상류로 모두 넘긴다). 경로 표·인증은 platform 공개 입구의 몫이다. 영역 사이 호출은 공개 입구를 지나지 않는다(R3.15).

## 되돌리는 조건
Envoy 가 CONNECT 허용 목록 또는 SDS 갱신을 지원하지 않게 되면 위 대안 비교를 다시 한다.
