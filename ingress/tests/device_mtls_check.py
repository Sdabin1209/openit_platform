"""Standalone Caddy assertions; every HTTPS connection verifies its CA and hostname."""
import http.client
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import time

from boundary_contracts import validator

port, directory = int(sys.argv[1]), Path(sys.argv[2])
policy = directory / "devices/allowlist.json"


def serial(cert):
    result = subprocess.run(["openssl", "x509", "-in", str(cert), "-noout", "-serial"], check=True, capture_output=True, text=True, env={"PATH": os.environ["PATH"]})
    return format(int(result.stdout.strip().split("=", 1)[1], 16), "x")


old = serial(directory / "dpki/old.crt")
new = serial(directory / "dpki/new.crt")


def replace(serials):
    record = {"schema_version": 1, "devices": [{"device_id": "kiosk-1", "serials": serials}]} if serials else {"schema_version": 1, "devices": []}
    validator("DeviceAllowlist").validate(record)
    pending = policy.with_suffix(".tmp")
    pending.write_text(json.dumps(record))
    pending.chmod(0o644)
    pending.replace(policy)


def connect(label=None):
    context = ssl.create_default_context(cafile=str(directory / "pki/root_ca.crt"))
    if label == "rogue":
        context.load_cert_chain(directory / "rogue/kiosk-1.crt", directory / "rogue/kiosk-1.key")
    elif label:
        context.load_cert_chain(directory / f"dpki/{label}.crt", directory / f"dpki/{label}.key")
    return http.client.HTTPSConnection("localhost", port, context=context, timeout=8)


def request(connection, headers=None, path="/v1/sessions"):
    connection.request("POST" if path == "/v1/sessions" else "GET", path, body='{"kind":"SESSION_START"}' if path == "/v1/sessions" else None, headers={"Content-Type": "application/json", **(headers or {})})
    response = connection.getresponse()
    data = response.read()
    body = json.loads(data)
    if response.status in (401, 403, 503):
        validator("BoundaryError").validate(body)
    if not path.startswith("/v1/staff/"):
        assert not response.getheader("WWW-Authenticate"), "device credentials have no HTTP challenge"
    return response.status, body


until = time.monotonic() + 45  # Fixture startup budget; TLS trust checks remain enabled while waiting.
while True:
    c = connect()
    try:
        assert request(c, path="/healthz")[0] == 200
        break
    except (OSError, http.client.HTTPException):
        if time.monotonic() >= until:
            raise
        time.sleep(0.1)
    finally:
        c.close()

replace([old])
plain, active, rotated = connect(), connect("old"), connect("new")
try:
    assert request(plain, {"Authorization": "Bearer retired-device-token", "X-Openit-Device": "kiosk-1"})[0] == 403
    status, body = request(active, {"X-Openit-Device": "forged", "X-Openit-Dn": "CN=forged"})
    assert status == 200
    credentials = body["headers"].get("Authorization", [])
    assert len(credentials) == 1 and credentials[0].startswith("Bearer ") and len(credentials[0]) > 7, "upstream Bearer credential missing"
    assert request(active, path="/v1/question-sets?question_set_id=test")[0] == 200
    assert body["headers"]["X-Openit-Device"] == ["kiosk-1"]
    assert "X-Openit-Dn" not in body["headers"]
    assert request(plain, {"X-Openit-Device": "forged"}, path="/v1/staff/alerts")[0] == 401
    status, staff = request(plain, {"Cookie": "fakeauth=staff-e2e", "X-Openit-Device": "forged", "X-Openit-Dn": "CN=forged"}, path="/v1/staff/alerts")
    assert status == 200 and staff["headers"]["X-Openit-User"] == ["staff-e2e"]
    assert "X-Openit-Device" not in staff["headers"] and "X-Openit-Dn" not in staff["headers"]
    assert request(rotated)[0] == 403
    replace([old, new])
    assert request(rotated)[0] == 200 and request(active)[0] == 200
    replace([new])
    assert request(active)[0] == 403, "revoked certificate remained authorized on an existing TLS connection"
    assert request(rotated)[0] == 200
    policy.write_text("invalid JSON")
    assert request(rotated)[0] == 503
    replace([new])
    assert request(rotated)[0] == 200
    rogue = connect("rogue")
    try:
        try:
            request(rogue)
        except (ssl.SSLError, ConnectionError, http.client.RemoteDisconnected):
            pass
        else:
            raise AssertionError("untrusted client certificate reached HTTP")
    finally:
        rogue.close()
finally:
    plain.close()
    active.close()
    rotated.close()
