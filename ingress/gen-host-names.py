#!/usr/bin/env python3
"""GATEWAY_HOSTS 에서 호스트 이름 목록을 만드는 진입점. 로직은 openit_platform/components/host_names.py.
사용: gen-host-names.py [--sites] '<GATEWAY_HOSTS>'"""
import pathlib, sys
# 왜 경로를 더하나: 이미지에서는 이 스크립트 옆(/usr/local/bin)에 openit_platform/ 이 있고, 리포에서는 리포 루트에 있다. 파일 이름·위치는 Dockerfile·entrypoint 가 부르므로 그대로 둔다.
for _root in (pathlib.Path(__file__).resolve().parent, pathlib.Path(__file__).resolve().parent.parent):
    if (_root / "openit_platform").is_dir():
        sys.path.insert(0, str(_root))
        break
from openit_platform.components.host_names import parse

if __name__ == "__main__":
    print(parse(sys.argv[-1], len(sys.argv) > 2 and sys.argv[1] == "--sites"))
