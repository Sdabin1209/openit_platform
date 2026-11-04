#!/bin/sh
# platform 인증서 발급 이미지의 진입점(ADR 0012). 부명령 하나로 인증기관·루트 내보내기·토큰 발급·인증서 받기/갱신을 모두 한다: 배치(deploy)가 셸 한 줄을 들고 있지 않게(구조 규칙 1).
#   serve(기본)      처음이면 `step ca init`(출력 없이: 공식 entrypoint 의 DOCKER_STEPCA_INIT_* 는 CA 비밀번호를 로그에 찍는다), 그 뒤 step-ca 를 /tmp 사본으로 실행(바이너리 파일 권한이 cap_drop ALL 에서 exec 를 막는다, 측정함)
#   root             /home/step/certs/root_ca.crt(공개) 를 $PKI_OUT(기본 /out)/root_ca.crt 로 복사
#   token <이름>...  서비스마다 일회용 토큰(OTT, 수명 5분 = step 기본)을 /tokens/<이름>.ott 로(프로비저너 비밀번호는 이 부명령만 읽는다)
#   cert <이름>      /certs/tls.{crt,key}: 검증(만료 포함)에 실패하면 /tokens/<이름>.ott 로 발급(R4.6: 만료 뒤에도 사람 손 없이), 그 뒤 갱신 데몬(R3.11: 인증기관이 멈춰도 발급된 인증서는 그대로, 데몬은 재시도)
# 비밀번호는 파일(/run/secrets/step-ca-password)로만 받고 출력하지 않는다. 환경 변수: STEP_CA_PORT(9000) STEP_CA_DNS_NAMES(공백 구분 추가 이름) STEP_CA_URL(기본 https://step-ca:$PORT)
#   STEP_CERT_NOT_AFTER(발급 수명, 비면 인증기관 기본 24h) STEP_RENEW_EXPIRES_IN(남은 수명이 이보다 짧아지면 갱신, 기본 12h = 수명 24h 의 절반)
set -eu
# 환경은 계약 StepCaEnv 로 검증하고 기본값을 채운다(위반 64)
eval "$(envcheck /etc/openit/schemas/StepCaEnv.schema.json)" || exit 64
export STEPPATH=$STEP_CA_HOME   # step CLI 의 상태 폴더 표준 변수
PW=$STEP_CA_PASSWORD_FILE; PORT=$STEP_CA_PORT; URL=$STEP_CA_URL; ROOT=/etc/openit/pki/root_ca.crt
cmd=${1:-serve}; [ $# -eq 0 ] || shift
case "$cmd" in
  serve)
    if [ ! -f $STEP_CA_HOME/config/ca.json ]; then
      DNS=""; for d in ${STEP_CA_DNS_NAMES:-}; do DNS="$DNS --dns $d"; done
      step ca init --name OpenIt --dns step-ca $DNS --address ":$PORT" --provisioner admin --acme --password-file "$PW" --provisioner-password-file "$PW" >/dev/null 2>&1
    fi
    cp /usr/local/bin/step-ca /tmp/step-ca
    exec /tmp/step-ca $STEP_CA_HOME/config/ca.json --password-file "$PW" ;;
  root)
    cp $STEP_CA_HOME/certs/root_ca.crt "${PKI_OUT:-/out}/root_ca.crt"; chmod 644 "${PKI_OUT:-/out}/root_ca.crt" ;;
  token)
    [ $# -gt 0 ] || { echo "token: 이름이 필요하다" >&2; exit 2; }
    export STEPPATH=/tmp
    for n in "$@"; do
      step ca token "$n" --provisioner admin --provisioner-password-file "$PW" --ca-url "$URL" --root "$ROOT" > "$STEP_TOKENS_DIR/$n.ott" || exit 1
    done
    chmod 644 "$STEP_TOKENS_DIR"/*.ott ;;
  cert)
    n=${1:?cert: 서비스 이름이 필요하다}; export STEPPATH=/tmp
    if ! step certificate verify $STEP_CERTS_DIR/tls.crt --roots "$ROOT" >/dev/null 2>&1; then
      NA=""; [ -z "${STEP_CERT_NOT_AFTER:-}" ] || NA="--not-after $STEP_CERT_NOT_AFTER"
      step ca certificate "$n" $STEP_CERTS_DIR/tls.crt $STEP_CERTS_DIR/tls.key --token "$(cat "$STEP_TOKENS_DIR/$n.ott")" --ca-url "$URL" --root "$ROOT" $NA --force >/dev/null
    fi
    exec step ca renew --daemon --force --expires-in "${STEP_RENEW_EXPIRES_IN:-12h}" $STEP_CERTS_DIR/tls.crt $STEP_CERTS_DIR/tls.key --ca-url "$URL" --root "$ROOT" ;;
  health)   # 이미지 HEALTHCHECK: 부명령마다 의미가 다르다(CA 는 step ca health, 인증서 컨테이너는 만료를 포함한 검증). 일회성(root·token)은 해당 없음
    if [ -f $STEP_CA_HOME/config/ca.json ]; then step ca health 2>/dev/null | grep -q '^ok'
    else step certificate verify $STEP_CERTS_DIR/tls.crt --roots "$ROOT" >/dev/null 2>&1; fi ;;
  *) echo "알 수 없는 부명령: $cmd (serve|root|token|cert|health)" >&2; exit 2 ;;
esac
