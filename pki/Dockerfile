# platform 인증서 발급(사설 PKI, step-ca; ADR 0003). 공식 step-ca 이미지(digest 고정) + 비밀번호를 로그에 찍지 않는 시작 스크립트. 키는 볼륨 /home/step 에, 비밀번호는 파일로.
ARG STEP_CA_IMAGE=docker.io/smallstep/step-ca@sha256:a8308bddba866f5fccb2740c8bb2e5dea8cdde4b5856058539a7f5170894a9c0
FROM ${STEP_CA_IMAGE}
ARG COMMIT=unknown
ARG BOUNDARY_TAG=unknown
LABEL io.openit.service="step-ca" io.openit.revision="${COMMIT}" io.openit.contracts.boundary="${BOUNDARY_TAG}" io.openit.contracts.survey-schema="n/a" io.openit.model-runtime="n/a"
COPY image/entrypoint.sh /usr/local/bin/openit-step-ca-entrypoint.sh
USER step
ENTRYPOINT ["/usr/local/bin/openit-step-ca-entrypoint.sh"]
