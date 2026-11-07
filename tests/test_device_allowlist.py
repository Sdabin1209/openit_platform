"""Revocation must affect the next request on an existing connection."""
import http.client
import importlib.util
import json
from pathlib import Path
import socket
import threading

import pytest
from boundary_contracts import validator

spec = importlib.util.spec_from_file_location("device_auth", Path(__file__).resolve().parents[1] / "ingress/device-auth.py")
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)


def write(path, serials):
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps({"schema_version": 1, "devices": [{"device_id": "kiosk-1", "serials": serials}]}))
    pending.replace(path)


def test_rotation_revocation_and_bad_reload_on_one_connection(tmp_path):
    path = tmp_path / "allowlist.json"
    write(path, ["a"])
    server = auth.Server(str(tmp_path / "auth.sock"), path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("localhost")
    connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.sock.connect(str(tmp_path / "auth.sock"))

    def request(serial):
        connection.request("GET", "/verify", headers={"X-Openit-Device-Cn": "kiosk-1", "X-Openit-Device-Serial": str(serial)})
        response = connection.getresponse()
        data = response.read()
        if response.status != 204:
            validator("BoundaryError").validate(json.loads(data))
        assert response.getheader("WWW-Authenticate") is None
        return response.status

    try:
        assert request(10) == 204
        write(path, ["a", "b"])
        assert request(11) == 204 and request(10) == 204
        write(path, ["b"])
        assert request(10) == 403 and request(11) == 204
        path.write_text("not json")
        assert request(11) == 503
        path.unlink()
        assert request(11) == 503
        write(path, ["b"])
        assert request(11) == 204
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("device,serial", [("", "10"), ("kiosk-2", "10"), ("kiosk-1", "11"), ("kiosk-1", "0"), ("kiosk-1", "1\n"), ("kiosk-1", str(2**159))])
def test_unlisted_or_invalid_certificate_is_denied(tmp_path, device, serial):
    path = tmp_path / "allowlist.json"
    write(path, ["a"])
    assert auth.authorize(path, device, serial)[0] == 403


def test_duplicate_device_id_is_not_silently_overwritten(tmp_path):
    path = tmp_path / "allowlist.json"
    entry = {"device_id": "kiosk-1", "serials": ["a"]}
    path.write_text(json.dumps({"schema_version": 1, "devices": [entry, entry]}))
    with pytest.raises(ValueError, match="duplicate"):
        auth.load_allowlist(path)
    assert auth.authorize(path, "kiosk-1", "10")[0] == 503


def test_generated_device_auth_uses_only_declared_environment_names():
    import importlib.util
    import re
    from boundary_contracts import load_schema
    source = Path(__file__).resolve().parents[1] / "ingress/gen-ingress-routes.py"
    spec = importlib.util.spec_from_file_location("generated_routes", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rendered = module.gen([{"service": "survey-service", "routes": [{"paths": ["/v1/sessions"], "auth": {"kind": "device"}, "upstream_token": "survey-api-token"}]}])
    names = set(re.findall(r"\{\$([A-Z][A-Z0-9_]*)", rendered))
    declared = set(load_schema("PublicIngressEnv")["properties"])
    assert names - declared <= {"PIPELINE_SCHEMA_VERSION"}
    assert "AUTH_CHECK_TIMEOUT" in names
