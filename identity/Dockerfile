# platform 사람 인증 이미지 identity(Keycloak 공식 이미지 위, 3.4.10). 입력은 계약 IdentityEnv 뿐이다: KC_*·realm 가져오기 파일·--config-file 은 진입점(identity-entry)이 만든다(구조 규칙 1·6).
# Keycloak "optimized image"(공식 권고 https://www.keycloak.org/server/containers): 빌드 때 `kc.sh build` 로 증강을 끝내 읽기 전용 루트를 쓴다. 빌드 옵션은 실행 때의 같은 이름 옵션과 같아야 한다.
# 쓰기 가능해야 하는 곳(tmpfs): /tmp, /opt/keycloak/data/tmp, /opt/keycloak/data/import(realm 가져오기 작업 폴더). 비밀은 파일로만 받는다(D84).
ARG KEYCLOAK_IMAGE=quay.io/keycloak/keycloak@sha256:9409c59bdfb65dbffa20b11e6f18b8abb9281d480c7ca402f51ed3d5977e6007
ARG GO_BUILDER=docker.io/library/caddy@sha256:c4cd20eaa0b69112fd5d4f721ffc9671687e1d5d0b155c8620cf7546dbef94c0
FROM ${GO_BUILDER} AS entry
COPY --from=common . /src/common
COPY entry/ /src/identity/entry/
RUN cd /src/identity/entry && CGO_ENABLED=0 go build -trimpath -buildvcs=false -o /identity-entry .
FROM ${KEYCLOAK_IMAGE}
ARG COMMIT=unknown
ARG BOUNDARY_TAG=unknown
ARG EXPOSURE_JSON
ARG JOBS_JSON
RUN /opt/keycloak/bin/kc.sh build --db=postgres --health-enabled=true --http-relative-path=/auth
COPY --from=entry /identity-entry /usr/local/bin/identity-entry
# 오프라인 검증은 전이 참조(_common·CommonEnv·잡 Env 포함)까지 필요하므로 계약 패키지의 스키마 묶음을 함께 넣는다.
COPY --from=boundary_contracts boundary_contracts/schemas/ /etc/openit/schemas/
# io.openit.exposure: 이 서비스의 노출 선언(계약 Exposure, 정본 identity/exposure-identity.json). build-image.sh 가 계약 스키마로 검증해 build arg 로 준다
LABEL io.openit.jobs="${JOBS_JSON}" io.openit.exposure="${EXPOSURE_JSON}" io.openit.service="identity" io.openit.revision="${COMMIT}" io.openit.contracts.boundary="${BOUNDARY_TAG}" io.openit.contracts.survey-schema="n/a" io.openit.model-runtime="n/a"
# 건강 확인(Docker 표준 HEALTHCHECK): 관리 포트의 준비 경로. 첫 기동은 realm 가져오기로 오래 걸린다(시작 유예 90초는 측정하지 않은 값)
HEALTHCHECK --interval=10s --timeout=5s --start-period=90s --retries=3 CMD ["/usr/local/bin/identity-entry", "health", "keycloak"]
USER 1000
# 진입점만 ENTRYPOINT 에, 기본 역할은 CMD 에 둔다(Docker 표준): deploy 는 잡을 compose command = 잡 선언 argv 로 띄운다(CONVENTIONS 13절).
# 역할을 ENTRYPOINT 에 박아 두면 잡 argv 가 그 뒤 인자로 붙어 Keycloak 서버 경로가 돌았다(E2E 사용자 등록 잡 실패, 2026-11-06).
ENTRYPOINT ["/usr/local/bin/identity-entry"]
CMD ["keycloak"]
