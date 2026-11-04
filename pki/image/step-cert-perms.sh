#!/bin/sh
# 인증서 컨테이너가 받은(또는 갱신한) 인증서·키 파일의 모드와 그룹을 맞춘다: 인증서 0644, 키 0640 그룹 STEP_CERT_GID(계약 StepCaEnv). 갱신 데몬이 --exec 로도 부른다.
set -eu
D=${STEP_CERTS_DIR:-/certs}; G=${STEP_CERT_GID:-10100}
chmod 0644 "$D/tls.crt"; chgrp "$G" "$D/tls.key"; chmod 0640 "$D/tls.key"
