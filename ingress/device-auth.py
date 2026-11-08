#!/usr/bin/env python3
"""Caddy forward_auth over a private Unix socket; reload DeviceAllowlist per request.

TLS verifies the certificate. Caddy supplies its CN and decimal serial, replacing
client headers. No credential or patient value appears in diagnostics or logs.
판정 로직은 openit_platform/components/device_authorization.py, 조립은 openit_platform/wiring/device_auth.py. 이 파일은 소켓 서버(진입점)다.
"""
from __future__ import annotations

import argparse
import os
import pathlib
from pathlib import Path
import socketserver
import sys
from http.server import BaseHTTPRequestHandler

# 왜 경로를 더하나: 이미지에서는 이 스크립트 옆(/usr/local/bin)에 openit_platform/ 이 있고, 리포에서는 리포 루트에 있다. 파일 이름·위치는 entrypoint 가 부르므로 그대로 둔다.
for _root in (pathlib.Path(__file__).resolve().parent, pathlib.Path(__file__).resolve().parent.parent):
    if (_root / "openit_platform").is_dir():
        sys.path.insert(0, str(_root))
        break

from openit_platform.wiring.device_auth import build, failure

_AUTH = build(Path(__file__).parent / "schemas" / "DeviceAuthRequest.json")
load_allowlist = _AUTH.load_allowlist
authorize = _AUTH.authorize


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, socket: str, allowlist: Path):
        self.allowlist = allowlist
        super().__init__(socket, Handler)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == "/readyz":
            result = _AUTH.ready(self.server.allowlist)
        elif self.path == "/verify":
            cn = self.headers.get_all("X-Openit-Device-Cn", [])
            serial = self.headers.get_all("X-Openit-Device-Serial", [])
            result = _AUTH.authorize(self.server.allowlist, cn[0] if len(cn) == 1 else "", serial[0] if len(serial) == 1 else "")
        else:
            result = failure(404, "NOT_FOUND", "not found")
        status, headers, body = result
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("allowlist", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--socket", default="/tmp/openit/device-auth.sock")
    args = parser.parse_args()
    try:
        load_allowlist(args.allowlist)
    except Exception:
        parser.exit(65, "ingress: DeviceAllowlist is unreadable or invalid\n")
    if args.check:
        return
    # Private parent and socket: only this image's Caddy process can submit the
    # trusted TLS attributes. No TCP listener is exposed to application networks.
    Path(args.socket).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(Path(args.socket).parent, 0o700)
    Path(args.socket).unlink(missing_ok=True)
    with Server(args.socket, args.allowlist) as server:
        os.chmod(args.socket, 0o600)
        server.serve_forever()


if __name__ == "__main__":
    main()
