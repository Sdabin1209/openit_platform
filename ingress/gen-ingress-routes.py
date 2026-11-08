#!/usr/bin/env python3
"""공개 입구 경로 표 생성기의 진입점(ADR 0002). 로직은 openit_platform/components/ingress_routes.py, 조립은 openit_platform/wiring/ingress_routes.py.
사용: gen-ingress-routes.py <Exposure JSON 파일 또는 폴더>... > routes.caddy (비밀 값 없음)."""
import pathlib, sys
# 왜 경로를 더하나: 이미지에서는 이 스크립트 옆(/usr/local/bin)에 openit_platform/ 이 있고, 리포에서는 리포 루트에 있다. 파일 이름·위치는 Dockerfile·entrypoint 가 부르므로 그대로 둔다.
for _root in (pathlib.Path(__file__).resolve().parent, pathlib.Path(__file__).resolve().parent.parent):
    if (_root / "openit_platform").is_dir():
        sys.path.insert(0, str(_root))
        break
from openit_platform.components.ingress_routes import *   # noqa: F401,F403 — 시험이 이 파일을 불러 gen 을 쓴다
from openit_platform.wiring.ingress_routes import load, main

if __name__ == "__main__":
    main(sys.argv[1:])
