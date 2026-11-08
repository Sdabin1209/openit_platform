#!/usr/bin/env python3
"""Caddy forward_auth over a private Unix socket; reload DeviceAllowlist per request.

TLS verifies the certificate. Caddy supplies its CN and decimal serial, replacing
client headers. No credential or patient value appears in diagnostics or logs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socketserver
from http.server import BaseHTTPRequestHandler

from jsonschema import Draft202012Validator
from boundary_contracts import BoundaryError, format_checker, strict_json, validator
from boundary_contracts.schemas_api import ContractValidator

_INPUT = json.loads((Path(__file__).parent / "schemas" / "DeviceAuthRequest.json").read_text())
# 왜 감싸나: 영역 내부 스키마(DeviceAuthRequest)용 계약 검증기가 5.0.0 에는 없다(5.0.1 schema_validator 로 바꾼다). 감싸야 NaN·무한대 검사와 형식 검사를 받는다.
_INPUT_VALIDATOR = ContractValidator(Draft202012Validator(_INPUT, format_checker=format_checker(_INPUT)))
_ALLOWLIST_VALIDATOR = validator("DeviceAllowlist")
_DEVICE_ID_VALIDATOR = validator(_INPUT["properties"]["device_id"]["x-contract"])


def load_allowlist(path: Path) -> dict[str, set[str]]:
    document = strict_json.loads(path.read_text(encoding="utf-8"))   # 계약 JSON 공통 규칙(깊이 64·1 MiB·I-JSON): 허용 목록은 deploy 가 쓴 파일이다
    _ALLOWLIST_VALIDATOR.validate(document)
    result: dict[str, set[str]] = {}
    for entry in document["devices"]:
        device = entry["device_id"]
        if device in result:
            raise ValueError("duplicate device_id")
        result[device] = set(entry["serials"])
    return result


def authorize(path: Path, device: str, decimal_serial: str) -> tuple[int, dict, bytes]:
    try:
        allowed = load_allowlist(path)
    except Exception:
        # Schema exceptions are deliberately indistinguishable from unreadable
        # configuration. Never retain a previously allowed certificate on error.
        return failure(503, "UNAVAILABLE", "device authorization unavailable")
    try:
        # Certificate serials are positive DER integers of at most 20 octets.
        # 48 decimal digits suffice for that public contract; bound conversion.
        _INPUT_VALIDATOR.validate({"device_id": device, "serial_decimal": decimal_serial})
        _DEVICE_ID_VALIDATOR.validate(device)
        serial = format(int(decimal_serial), "x")
        _ALLOWLIST_VALIDATOR.validate({
            "schema_version": 1,
            "devices": [{"device_id": device, "serials": [serial]}],
        })
    except Exception:
        return failure(403, "PERMISSION_DENIED", "device authentication failed")
    if serial not in allowed.get(device, set()):
        return failure(403, "PERMISSION_DENIED", "device authentication failed")
    return 204, {"X-Openit-Device": device, "Cache-Control": "no-store"}, b""


def failure(status: int, code: str, message: str) -> tuple[int, dict, bytes]:
    record = BoundaryError(code, message).to_record()
    body = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json", "Cache-Control": "no-store"}
    if status == 503:
        headers["Retry-After"] = "5"
    return status, headers, body


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
            try:
                load_allowlist(self.server.allowlist)
                record = {"status": "ready"}
                validator("HealthStatus").validate(record)
                result = 200, {"Content-Type": "application/json", "Cache-Control": "no-store"}, json.dumps(record).encode()
            except Exception:
                result = failure(503, "UNAVAILABLE", "device authorization unavailable")
        elif self.path == "/verify":
            cn = self.headers.get_all("X-Openit-Device-Cn", [])
            serial = self.headers.get_all("X-Openit-Device-Serial", [])
            result = authorize(self.server.allowlist, cn[0] if len(cn) == 1 else "", serial[0] if len(serial) == 1 else "")
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
