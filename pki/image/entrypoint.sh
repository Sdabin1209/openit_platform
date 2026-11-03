#!/bin/sh
# step-ca 시작(ADR 0003): 처음이면 `step ca init`(출력 없이: 공식 entrypoint 의 DOCKER_STEPCA_INIT_* 는 CA 비밀번호를 로그에 찍는다), 그 뒤 step-ca 를 /tmp 사본으로 실행한다
# (바이너리의 파일 권한이 cap_drop ALL 에서 exec 를 막는다, 측정함). 비밀번호는 파일(/run/secrets/step-ca-password)로만 받는다. 추가 이름은 STEP_CA_DNS_NAMES(공백 구분).
set -eu
PW=/run/secrets/step-ca-password; PORT=${STEP_CA_PORT:-9000}
if [ ! -f /home/step/config/ca.json ]; then
  DNS=""; for d in ${STEP_CA_DNS_NAMES:-}; do DNS="$DNS --dns $d"; done
  step ca init --name OpenIt --dns step-ca $DNS --address ":$PORT" --provisioner admin --acme --password-file "$PW" --provisioner-password-file "$PW" >/dev/null 2>&1
fi
cp /usr/local/bin/step-ca /tmp/step-ca
exec /tmp/step-ca /home/step/config/ca.json --password-file "$PW"
