#!/bin/sh
# platform 인증서 발급 이미지의 진입점(ADR 0012). 역할(STEP_ROLE) 하나로 인증기관·루트 내보내기·토큰 발급·인증서 받기/갱신을 모두 한다: 배치(deploy)가 셸 한 줄을 들고 있지 않게(구조 규칙 1).
#   serve(기본)      처음이면 `step ca init`(출력 없이: 공식 entrypoint 의 DOCKER_STEPCA_INIT_* 는 CA 비밀번호를 로그에 찍는다), 그 뒤 step-ca 를 /tmp 사본으로 실행(바이너리 파일 권한이 cap_drop ALL 에서 exec 를 막는다, 측정함)
#   root             /home/step/certs/root_ca.crt(공개) 를 $PKI_OUT(기본 /out)/root_ca.crt 로 복사
#   token <이름>...  서비스마다 일회용 토큰(OTT, 수명 5분 = step 기본)을 /tokens/<이름>.ott 로(프로비저너 비밀번호는 이 부명령만 읽는다)
#   cert <이름>      /certs/tls.{crt,key}: 검증(만료 포함)에 실패하면 /tokens/<이름>.ott 로 발급(R4.6: 만료 뒤에도 사람 손 없이), 그 뒤 갱신 데몬(R3.11: 인증기관이 멈춰도 발급된 인증서는 그대로, 데몬은 재시도)
# 비밀번호는 파일(/run/secrets/step-ca-password)로만 받고 출력하지 않는다. 환경 변수: STEP_CA_PORT(9000) STEP_CA_DNS_NAMES(공백 구분 추가 이름) STEP_CA_URL(기본 https://step-ca:$PORT)
#   STEP_CERT_NOT_AFTER(발급 수명, 비면 인증기관 기본 24h) STEP_RENEW_EXPIRES_IN(남은 수명이 이보다 짧아지면 갱신, 기본 12h = 수명 24h 의 절반)
set -eu
# 첫 인자가 절대 경로면 잡 선언 argv 다(계약 JobsDeclaration.argv: 이미지 안에서 실행할 명령). 역할 분기·환경 검사 없이 그대로 실행한다(Docker 표준 진입점 관례, 2026-11-06)
case "${1:-}" in /*) exec "$@";; esac
# 환경은 계약 StepCaEnv 로 검증하고 기본값을 채운다(위반 64)
ENVOUT=$(envcheck /etc/openit/schemas/StepCaEnv.schema.json) || exit 64   # 명령 치환 안의 실패는 eval 에 가려지므로 먼저 받아 종료 코드를 본다
eval "$ENVOUT"
export STEPPATH=$STEP_CA_HOME   # step CLI 의 상태 폴더 표준 변수
PW=$STEP_CA_PASSWORD_FILE; PORT=$STEP_CA_PORT; URL=$STEP_CA_URL; ROOT=/etc/openit/pki/root_ca.crt
# 역할은 계약 StepCaEnv.STEP_ROLE(serve|root|token|cert)로 고른다(3.4.17: deploy 는 이미지 부명령을 모른다). 첫 인자 health 는 이미지의 HEALTHCHECK 가 부른다.
cmd=${STEP_ROLE}; [ "${1:-}" != health ] || cmd=health
case "$cmd" in
  serve)
    if [ ! -f $STEP_CA_HOME/config/ca.json ]; then
      DNS=""; for d in ${STEP_CA_DNS_NAMES:-}; do DNS="$DNS --dns $d"; done
      step ca init --name OpenIt --dns step-ca $DNS --address ":$PORT" --provisioner admin --acme --password-file "$PW" --provisioner-password-file "$PW" >/dev/null 2>&1
    fi
    cp /usr/local/bin/step-ca /tmp/step-ca
    exec /tmp/step-ca $STEP_CA_HOME/config/ca.json --password-file "$PW" ;;
  root)
    cp $STEP_CA_HOME/certs/root_ca.crt "$PKI_OUT/root_ca.crt"; chmod 644 "$PKI_OUT/root_ca.crt" ;;
  token)
    [ -n "${STEP_TOKEN_NAMES:-}" ] || { echo "step-ca: STEP_ROLE=token 에는 STEP_TOKEN_NAMES 가 필요하다" >&2; exit 64; }
    export STEPPATH=/tmp
    for n in $STEP_TOKEN_NAMES; do
      step ca token "$n" --provisioner admin --provisioner-password-file "$PW" --ca-url "$URL" --root "$ROOT" > "$STEP_TOKENS_DIR/$n.ott" || exit 1
    done
    chmod 644 "$STEP_TOKENS_DIR"/*.ott ;;
  cert)
    n=${STEP_CERT_NAME:-}; [ -n "$n" ] || { echo "step-ca: STEP_ROLE=cert 에는 STEP_CERT_NAME 이 필요하다" >&2; exit 64; }
    export STEPPATH=/tmp
    D=$STEP_CERTS_DIR
    # 읽는 쪽(공개 입구·DB 등, 보조 그룹 STEP_CERT_GID)이 언제나 완성된 0640 키와 인증서만 보게 한다: 받은 결과를 같은 폴더의 임시 파일에 두고 모드·그룹을 맞춘 뒤 rename(2)으로 바꿔 넣는다(POSIX 원자적 교체, RUNTIME OUT-FILE 과 같은 방식).
    # 키는 발급 때만 쓰이고 갱신(같은 키로 새 인증서)은 인증서 파일만 바꾼다. 인증서가 갱신 뒤에도 0644 로 같은 이름으로 보인다.
    publish() { # publish <새 인증서> <새 키|""> : 모드 0644/0640 + 그룹 맞춘 뒤 키 먼저, 인증서 나중에 rename
      chmod 0644 "$1"; if [ -n "$2" ]; then chgrp "$STEP_CERT_GID" "$2" && chmod 0640 "$2" && mv -f "$2" "$D/tls.key"; fi; mv -f "$1" "$D/tls.crt"
    }
    if ! step certificate verify $D/tls.crt --roots "$ROOT" >/dev/null 2>&1; then
      NA=""; [ -z "${STEP_CERT_NOT_AFTER:-}" ] || NA="--not-after $STEP_CERT_NOT_AFTER"
      rm -f "$D/.tls.crt.new" "$D/.tls.key.new"
      step ca certificate "$n" "$D/.tls.crt.new" "$D/.tls.key.new" --token "$(cat "$STEP_TOKENS_DIR/$n.ott")" --ca-url "$URL" --root "$ROOT" $NA --force >/dev/null || exit 1
      publish "$D/.tls.crt.new" "$D/.tls.key.new"
    fi
    trap 'exit 0' TERM INT
    while :; do   # 갱신: 남은 수명이 STEP_RENEW_EXPIRES_IN 보다 짧으면 같은 키로 새 인증서를 받는다. 인증기관이 멈춰 있으면 실패해도 발급된 인증서는 그대로 두고(R3.11) 다음 주기에 다시 한다. 점검 주기 5초는 측정하지 않은 값이다
      if step certificate needs-renewal "$D/tls.crt" --expires-in "$STEP_RENEW_EXPIRES_IN" >/dev/null 2>&1; then
        rm -f "$D/.tls.crt.new"
        if step ca renew --force --out "$D/.tls.crt.new" "$D/tls.crt" "$D/tls.key" --ca-url "$URL" --root "$ROOT" >/dev/null 2>&1 && [ -s "$D/.tls.crt.new" ]; then publish "$D/.tls.crt.new" ""; fi
      fi
      sleep 5 & wait $!
    done ;;
  health)   # 이미지 HEALTHCHECK: 역할마다 의미가 다르다. serve=CA 응답, cert=만료를 포함한 검증, root=루트 파일이 있음, token=이름마다 토큰이 있음
    case "$STEP_ROLE" in
      serve) step ca health 2>/dev/null | grep -q '^ok' ;;
      cert) step certificate verify $STEP_CERTS_DIR/tls.crt --roots "$ROOT" >/dev/null 2>&1 ;;
      root) [ -s "$PKI_OUT/root_ca.crt" ] ;;
      token) for n in $STEP_TOKEN_NAMES; do [ -s "$STEP_TOKENS_DIR/$n.ott" ] || exit 1; done ;;
    esac ;;
  *) echo "step-ca: 알 수 없는 역할: $cmd" >&2; exit 64 ;;
esac
