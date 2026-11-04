# 공개 입구 시험 공통(source 해서 쓴다): 이미지는 지금 이 리포에서 빌드하고(build-image.sh), 시험 PKI·비밀은 이 리포의 생성기로 만들고, 상류는 제어되는 가짜 + TLS 앞단으로 둔다.
# 호출 쪽이 정하는 것: PREFIX(컨테이너·네트워크 이름 접두어, 리포 이름 + 접미사), 호출 전에 source scripts/lib.sh. 정리는 이 파일이 만든 이름만 지운다.
stack_init() { # stack_init <PREFIX> <PKI에 넣을 서비스 이름...>
  PREFIX=$1; shift; ID=$$; T=$(mktemp -d); chmod 755 "$T"; export SECRETS_DIR=$T
  ING=platform-ingress:$PREFIX-$ID; NET=$PREFIX-net-$ID; DATAVOL=$PREFIX-data-$ID; CN=$PREFIX-gw-$ID; CU=$PREFIX-up-$ID; PKI=$T/pki; mkdir -p "$PKI"
  gateway_test_pki "$PKI" "$@" || { echo "시험 PKI 를 만들지 못했다"; exit 1; }
  GWI=$(sed -n 's/^GATEWAY_IMAGE=//p' "$ROOT/locks/images.lock"); UTIL=$(sed -n 's/^UTIL_IMAGE=//p' "$ROOT/locks/images.lock")
  BSRC=$(bash "$ROOT/scripts/fetch-boundary-src.sh" "$T/boundary-src") || exit 1
  printf '{"source_dir":"%s","revision":"abcdef1","versions":{"boundary":"v%s"},"variant":"public-ingress","dependency_sources":{"boundary":"%s"},"image_tag":"%s"}' "$ROOT" "$("$ROOT/.venv/bin/python" -c 'import importlib.metadata as m;print(m.version("boundary-contracts"))')" "$BSRC" "$ING" > "$T/build-req.json"
  bash "$ROOT/scripts/build-image.sh" "$T/build-req.json" >/dev/null 2>"$T/build.err" || { tail -3 "$T/build.err"; echo "공개 입구 이미지를 만들지 못했다"; exit 1; }
  bash "$ROOT/ingress/scripts/gen-test-secrets.sh" "$T" >/dev/null 2>&1 || { echo "시험 비밀을 만들지 못했다"; exit 1; }
  DEVICE_PKI_DIR=$T/dpki bash "$ROOT/ingress/scripts/device-pki.sh" init >/dev/null 2>&1 || { echo "기기 CA 를 만들지 못했다"; exit 1; }
  DEVCA=$T/dpki/ca.crt   # 계약 PublicIngressEnv.INGRESS_DEVICE_CA_FILE 로 마운트한다(필수)
  docker network create $NET >/dev/null
}
stack_cleanup() { # 로그는 지우기 전에 $KEEP_DIR 로 남긴다(실패 진단)
  if [ "${1:-0}" != 0 ] || [ "${KEEP:-0}" = 1 ]; then d=${KEEP_DIR:-$ROOT/build/logs/$PREFIX-$ID}; mkdir -p "$d"; for c in $CN $CU; do docker logs $c > "$d/$c.log" 2>&1; done; echo "로그를 남겼다: $d"; fi
  docker rm -f $CN $CU $CU-tls ${EXTRA_CONTAINERS:-} >/dev/null 2>&1; docker network rm $NET >/dev/null 2>&1; docker volume rm -f $DATAVOL >/dev/null 2>&1; docker rmi "$ING" >/dev/null 2>&1; rm -rf "$T"
}
start_upstream() { # start_upstream <상류 파이썬 파일> <서비스 이름 별칭...>: 상류 + 같은 네트워크 공간의 TLS 앞단(서비스 이름 인증서)
  local py=$1; shift
  docker run -d --name $CU --network $NET $(for h in "$@"; do echo --network-alias $h; done) -v "$py:/e.py:ro" "$UTIL" python /e.py >/dev/null
  printf '{\n\tadmin off\n\tskip_install_trust\n\tauto_https off\n}\nhttps://:443 {\n\ttls /pki/leaf.crt /pki/leaf.key\n\treverse_proxy 127.0.0.1:8080\n}\n' > "$PKI/front.caddy"
  docker run -d --name $CU-tls --network container:$CU -v "$PKI/front.caddy:/etc/caddy/Caddyfile:ro" -v "$PKI:/pki:ro" "$GWI" caddy run --config /etc/caddy/Caddyfile >/dev/null
}
start_gateway() { # start_gateway <이름> [docker 인자...]: 공개 입구(internal 모드) 한 개. 호스트 포트는 Docker 가 배정한다
  local name=$1; shift
  docker run -d --name "$name" --network $NET $(gateway_test_mounts "$PKI") --user 10001:10001 --group-add "$SECRETS_GID" --read-only --tmpfs /tmp:uid=10001,gid=10001 -v "$DATAVOL:/data" --tmpfs /config:uid=10001,gid=10001 --tmpfs /etc/openit/root-out:uid=10001,gid=10001,mode=755 \
    -e "GATEWAY_HOSTS=localhost:8443" -v "${DEVCA_MOUNT:-$DEVCA}:/etc/openit/device-ca.pem:ro" -v "$ROOT/ingress/tests/exposures:/etc/openit/exposures:ro" -v "$T/tokens:/run/secrets:ro" -p 127.0.0.1::8443 "$@" "$ING" >/dev/null
}
wait_port() { # wait_port <컨테이너>: 호스트 포트를 stdout 으로(준비 확인: /healthz 가 응답할 때까지)
  local p="" i; for i in $(seq 1 60); do p=$(docker port "$1" 8443/tcp 2>/dev/null | head -1 | sed 's/.*://'); [ -n "$p" ] && curl -sk -o /dev/null -m 2 --resolve "localhost:$p:127.0.0.1" "https://localhost:$p/healthz" && { echo "$p"; return 0; }; sleep 0.5; done; return 1
}
use_name_resolution() { # use_name_resolution <호스트 포트>: 모든 curl 이 이름(localhost)으로 붙게 한다. 기본 기기 인증(mTLS)에서는 Host 와 TLS SNI 가 같아야 하고(RFC 9110 421) SNI 에는 IP 리터럴을 쓸 수 없다(RFC 6066 3절)
  mkdir -p "$T/curlhome"; printf 'resolve = "localhost:%s:127.0.0.1"\n' "$1" > "$T/curlhome/.curlrc"; export CURL_HOME=$T/curlhome; GW_URL=https://localhost:$1
}
