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
RUN /opt/keycloak/bin/kc.sh build --db=postgres --health-enabled=true --http-relative-path=/auth
COPY --from=entry /identity-entry /usr/local/bin/identity-entry
COPY --from=boundary_contracts schemas/IdentityEnv.schema.json /etc/openit/schemas/
# io.openit.exposure: 이 서비스의 노출 선언(계약 Exposure, 정본 identity/exposure-identity.json). build-image.sh 가 계약 스키마로 검증해 build arg 로 준다
LABEL io.openit.exposure="${EXPOSURE_JSON}" io.openit.service="identity" io.openit.revision="${COMMIT}" io.openit.contracts.boundary="${BOUNDARY_TAG}" io.openit.contracts.survey-schema="n/a" io.openit.model-runtime="n/a"
USER 1000
ENTRYPOINT ["/usr/local/bin/identity-entry", "keycloak"]
