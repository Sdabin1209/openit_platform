# 0001. 영역 게이트웨이 이미지: Envoy (들어오는 쪽 TLS 종단 + 나가는 쪽 CONNECT 터널)

## 상태
채택(계약 boundary-contracts v3.4.6 CONVENTIONS 13절, RUNTIME R1.1·R1.8·R6.2). 측정하지 않은 값은 "측정 안 함"으로 적었다.

## 맥락
서비스를 가진 영역마다 게이트웨이가 하나 있다. 들어오는 쪽은 서비스 이름 인증서로 TLS 를 끝내고 영역 안 컴포넌트로 넘긴다. 나가는 쪽은 영역 안 컴포넌트의 영역 밖 호출을 HTTP CONNECT 터널(RFC 9110 9.3.6)로 받아, 그 영역 `Exposure.egress` 에 선언한 상대에게만 열고 그 밖은 403 `PERMISSION_DENIED`(`details.reason=EGRESS_DENIED`)로 거절한다. TLS 는 호출 컴포넌트와 받는 영역 게이트웨이 사이에서 끝까지 유지되므로 터널은 TLS 를 풀지 않는다.

## 결정
- 제품은 **Envoy 공식 이미지(`envoyproxy/envoy`, digest 고정)** 다. 영역마다 설정만 다르다. **설정 생성기(`area-gateway/gen-area-gateway-config.py`)를 이미지 안에 넣고**(파이썬 + 계약 패키지는 요청의 dependency_sources 소스 트리에서 설치) 진입점이 시작할 때 마운트된 Exposure 선언에서 설정을 만들어 envoy 를 exec 한다. 영역마다 이미지가 같고 입력만 다르다(deploy 변경 요청 CR-area-gateway-config-generator 의 결정).
- **이미지 입력(배포 입력, 영역 사이 계약이 아니다)**: `/etc/openit/exposure.json`(그 영역 Exposure, 계약 스키마로 검증; 어기거나 없으면 종료 코드 65/64 로 시작하지 않는다), `/certs/tls.crt`·`/certs/tls.key`, 환경 변수 `AREA_GATEWAY_UPSTREAM`(기본 127.0.0.1:8080)·`AREA_GATEWAY_INGRESS_PORT`(443)·`AREA_GATEWAY_EGRESS_PORT`(3128), `/tmp` tmpfs(읽기 전용 루트에서 만든 설정을 쓴다).
- Exposure.routes 의 `max_body_bytes`(없으면 8MiB)로 Content-Length 가 넘으면 413 BoundaryError(INVALID_RECORD), `upstream_port` 로 경로별 상류(같은 네트워크 공간 loopback 포트). Content-Length 가 없는 본문(청크 전송)의 상한은 **받는 앱이 지켜 413 을 낸다**(결정, 헤드 2026-11-04): 게이트웨이가 큰 업로드(패키지 tar 4GiB 등)를 버퍼링하지 않기 위함이고, RUNTIME R3.5 가 "앱에 닿기 전 거절해도 같다"고 하여 어느 쪽이 거절해도 출력이 같다. 따라서 게이트웨이는 Content-Length 로 앞에서 거절하는 것까지만 한다(앱 쪽 시험은 각 영역 몫).
- 인증서는 파일 SDS(`watched_directory`)로 읽어 인증서 갱신(ADR 0060, `step ca renew`) 때 재시작·reload 없이 새 파일을 쓴다.
- 허용 목록은 `:authority` 정확 일치(`<서비스>:443`), `external:backup` 은 `backup-store:443`, `external:web-push` 는 점 있는 공인 이름의 `:443` 정규식이다.
- 이미지는 비루트(101), 읽기 전용 루트에서 돈다. 라벨은 `io.openit.service=area-gateway`.

## 왜
- CONNECT 터널을 표준 기능(`connect_matcher`, `dynamic_forward_proxy`)으로 하고 허용 목록·거절 본문을 설정으로 선언할 수 있다. 시험(`tests/test_area_gateway.py`)이 실제 이미지로 허용·거절·변이를 확인했다.
- 파일 SDS 로 인증서 교체를 다시 읽는다(Caddy 는 설정이 그대로면 reload 를 건너뛰는 결함을 겪었다: deploy ADR 0060 실험 C6).

## 검토한 대안과 버리는 이유
- **Caddy + forwardproxy 플러그인**: 들어오는 쪽 TLS 는 이미 쓰고 있어(공개 입구) 익숙하나 CONNECT 터널(forward proxy)이 공식 이미지에 없다(`caddyserver/forwardproxy` 를 xcaddy 로 직접 빌드해야 한다: 영역 게이트웨이 이미지가 공식 이미지가 아니라 우리가 빌드·보안 갱신하는 이미지가 된다). 허용 목록은 `acl` 로 되지만 거절 본문을 BoundaryError JSON 으로 낼 수 없다. 버린다.
- **Squid / tinyproxy**: CONNECT 허용 목록은 쉬우나 들어오는 쪽 TLS 종단과 사이드카 역할을 한 제품으로 못 한다. 영역마다 두 제품이 된다. 버린다.
- **HAProxy**: CONNECT 터널을 `http-request` 규칙으로 할 수 있으나 403 본문·SDS 파일 감시가 Envoy 만큼 선언적이지 않다. 버린다.

## 결과
- 얻는 것: 한 제품으로 두 방향, 설정은 계약 선언에서 생성. 감수: Envoy 설정이 길고(생성기가 감춘다) 이미지가 크다(측정 안 함).
- 들어오는 쪽 상류: 기본 상류(`AREA_GATEWAY_UPSTREAM`)와 Exposure 의 `upstream_port`(3.4.7)를 지원한다(단독 시험 있음). 경로 표·인증은 platform 공개 입구의 몫이다. 영역 사이 호출은 공개 입구를 지나지 않는다(R3.15).
- 나가는 쪽 리스너는 `127.0.0.1:3128`(영역 컴포넌트와 같은 네트워크 공간의 loopback, `OPENIT_EGRESS_PROXY=http://127.0.0.1:3128`, RUNTIME R1.8). 다른 컨테이너는 닿지 못한다(시험).

## 되돌리는 조건
Envoy 가 CONNECT 허용 목록 또는 SDS 갱신을 지원하지 않게 되면 위 대안 비교를 다시 한다.

## 추가 결정: 나가는 쪽 전용 동작 (배치 담당 발견)

- 맥락: compose 밖(학습 서버)의 model-lab 게이트웨이는 나가는 쪽만 필요한데, 생성기가 들어오는 쪽 listener 를 늘 열어 인증서 없는 입구가 생긴다.
- 결정: 진입점이 인증서 폴더(`AREA_GATEWAY_CERT_DIR`, 기본 `/certs`)가 마운트되어 있는지 본다. 없으면 생성기에 `--no-ingress` 를 주어 들어오는 listener 와 SDS 를 만들지 않고 나가는 쪽(loopback CONNECT)만 연다. 결정 기준은 입력(마운트)이고 새 필수 설정은 없다(`AREA_GATEWAY_CERT_DIR` 는 선택).
- 왜: 쓰지 않는 입구를 두지 않는다(공격면 최소화). 인증서가 없는 TLS 입구는 시작해도 쓸 수 없고 Envoy 는 SDS 감시 폴더가 없으면 시작 자체를 거부한다.
- 대안: Exposure.routes 가 빈 경우로 판단 - 버린다: 계약 스키마가 `routes` 최소 1개를 요구해 빈 선언은 계약 위반이다. 별도 환경 변수 스위치 - 버린다: 입력 하나(마운트)로 정해지는데 값이 어긋날 수 있는 두 번째 입력을 만든다.
- 결과: 마운트를 잊으면 들어오는 쪽이 조용히 닫힌다(안전한 방향). 시험 `test_egress_only_when_certs_not_mounted_opens_no_ingress_listener`가 listener 없음 단언 + 마운트 변이를 본다.
- 되돌리는 조건: 인증서 없이 여는 입구가 필요해지면(현재 없음).
