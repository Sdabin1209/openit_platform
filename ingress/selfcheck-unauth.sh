#!/bin/sh
# 공개 입구 인증 없는 요청 자체 점검(ingress/selfcheck-unauth.py). 사용: docker run --rm --network <스택 네트워크> -v <선언 폴더>:/etc/openit/exposures:ro --entrypoint selfcheck-unauth <public-ingress 이미지> <https://주소:포트> [--cacert 파일 | --insecure]
exec /opt/gw/bin/python /usr/local/bin/selfcheck-unauth.py "$@"
