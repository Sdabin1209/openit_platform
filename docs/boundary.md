# platform 경계 문서

## 소유
공개 입구(사람·기기), 사람 인증(identity = Keycloak, identity-proxy = oauth2-proxy, identity-db), 영역 게이트웨이 이미지, 인증서 발급(step-ca), 감시, 백업 저장소. 이미지마다 `scripts/build-image.sh` 의 variant 하나: 없음 = area-gateway, `public-ingress`, `monitoring`, `backup-store`, `step-ca`, `identity`, `identity-proxy`, `identity-db`(PublishRequest.service 이름과 같다).

## 소비하는 계약
boundary-contracts(태그는 `requirements.txt` 한 곳에서 고정): Exposure, BuildImageRequest/Result, ImageLabels, BoundaryError, HealthStatus, DatabaseDeclaration, HumanAuthEndpoints와 이미지별 Env 스키마. 시험은 고정 태그 소스를 `scripts/fetch-boundary-src.sh` 로 받는다(이웃 작업 트리에 기대지 않는다).

## 이미지 입력: 계약 Env 스키마 (구조 규칙 6)
이 영역 이미지가 받는 환경 변수의 이름·형식·기본값은 계약 스키마가 정본이다(여기에 복사하지 않는다): `AreaGatewayEnv`, `PublicIngressEnv`, `MonitoringEnv`, `BackupStoreEnv`, `StepCaEnv`, `IdentityEnv`, `IdentityProxyEnv`, `AreaDatabaseEnv`(+ 라벨 `io.openit.database` = `DatabaseDeclaration`). 스키마 파일은 빌드 때 이미지 안(`/etc/openit/schemas/`)에 들어가고, 기동 때 `envcheck`(`common/envcheck`, Go 정적 바이너리)가 환경을 그 스키마로 검증하고 기본값을 채운다. **위반(필수 누락, 형식 위반, 스키마에 없는 이 영역 접두어 이름)이면 종료 64**. 선언(Exposure) 위반·같은 공개 경로 중복·기기 토큰 형식 위반은 종료 65.
이미지가 스스로 만드는 파생 값(deploy 가 주지 않는다): 공개 입구의 사설 CA 루트 내보내기(`INGRESS_ROOT_EXPORT_DIR`, 3.4.16), 공개 입구의 기기 mTLS 검증 조각(`INGRESS_DEVICE_CA_FILE`, 필수 — 파일이 없거나 PEM 이 아니면 종료 64, 3.4.13), 공개 입구의 CSRF 허용 호스트 목록(GATEWAY_HOSTS 에서), 오류 본문의 `pipeline_schema_version`(계약 패키지), 기기 허용 목록의 요청별 대조(`INGRESS_DEVICE_ALLOWLIST_FILE`, 부모 디렉터리 마운트·잘못된 갱신은 503 fail-closed), identity 의 `KC_*`·realm 가져오기 파일·`--config-file`, identity-proxy 의 `OAUTH2_PROXY_*`, 감시의 설정 경로 치환, identity-db 의 계정·`pg_hba`·TLS.
마운트 규칙(스키마 변수가 가리키는 경로 말고): 영역 게이트웨이 `/tmp` tmpfs; 공개 입구 `/tmp`,`/data`,`/config` tmpfs; identity `/tmp`,`/opt/keycloak/data/tmp`,`/opt/keycloak/data/import` tmpfs; identity-proxy 없음; identity-db `/var/lib/postgresql/data`(rw), `/tmp`·`/var/run/postgresql` tmpfs; monitoring prometheus `/prometheus`·alertmanager `/alertmanager`(rw). 읽기 전용 루트와 비루트로 돈다. 변형별 추가 설명: `docs/COMPONENTS.md`.
서비스 이름(네트워크 별칭): 사람 인증 경로는 공개 입구가 `identity`(Keycloak), `identity-proxy`(인증 확인)로 부른다(노출 선언: identity·identity-proxy 이미지 라벨 `io.openit.exposure`).

## 설치처는 호스트 이름으로 접속한다 (계약 3.4.14)
기본 기기 인증(mTLS)을 켜면 Caddy 는 Host 와 TLS SNI 가 같기를 요구하고(RFC 9110 15.5.20 421), SNI 에는 IP 리터럴을 쓸 수 없다(RFC 6066 3절). 그래서 `GATEWAY_HOSTS` 는 DNS 이름만 받고(IP 리터럴이면 envcheck 가 종료 64), 키오스크·직원 PC·점검 도구는 모두 그 이름으로 접속한다(IP 로 직접 붙으면 421). Host 를 SNI 와 다르게 위조한 요청은 CSRF 규칙에 닿기 전에 TLS 단에서 421 로 막힌다(시험: `test-gateway-auth.sh`). SNI 검사를 끄지 않는다(보안 약화).

## 공개 입구 자체 점검 명령 (`selfcheck-unauth`)
공개 입구 이미지 안의 명령. 인증 없는(쿠키·토큰 없음) 요청에 대한 기대 응답의 정본이다(손 표 없음): 마운트된 영역 Exposure 선언(+ 내장 선언)에서 기대 행을 만든다.
- 실행(배포는 띄운 스택에 실행만 한다): `docker run --rm --network <스택 네트워크> -v <선언 폴더>:/etc/openit/exposures:ro --entrypoint selfcheck-unauth <public-ingress 이미지> <https://주소:포트> --cacert 파일 [--exposures 폴더...]`
- 기본 선언 폴더: `/etc/openit/exposures`. 주소의 호스트는 공개 입구가 받는 이름이어야 한다(`GATEWAY_HOSTS` 또는 `GATEWAY_PROBE_SITE`).
- 기대 행: device -> 인증서 없음/폐기 시 403 + PERMISSION_DENIED, HTTP challenge 없음; account·authenticated 의 `/v1/` -> 401 + `Bearer realm="openit"` + PERMISSION_DENIED; 그 밖의 화면 GET 은 `Accept: text/html` 이면 302 `/oauth2/start`, 아니면 401; 선언 없는 `/v1/` 경로 -> 404 NOT_FOUND. `none`·`denied` 과 `/healthz`·`/readyz`·`/metrics` 는 행이 없다.
- 출력: 줄마다 `PASS`/`FAIL`, 마지막 줄 요약. 종료 코드 0 모두 일치, 1 어긋남(또는 점검할 행이 없음), 2 입력 오류(선언 없음·계약 위반·알 수 없는 인자).

## 장애 영향
- 공개 입구 정지: 사람·기기 모두 접근 불가(영역 사이 호출은 영향 없음).
- identity-proxy·identity 정지: 사람 경로 503 UU(R3.12), 기기 경로는 영향 없음.
- 영역 게이트웨이 정지: 그 영역의 들어오는 호출과 나가는 호출이 모두 끊긴다.
