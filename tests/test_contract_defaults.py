"""계약이 정한 값(게이트웨이 기본값 gateway_defaults, 기기 ID 패턴)의 사본이 platform 코드에 없고 계약에서 읽는지 정적으로 본다(D117)."""
import importlib.util, pathlib, re
from boundary_contracts import load_schema

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gateway_defaults_are_read_from_the_contract_not_copied():
    from boundary_contracts import gateway_defaults
    want = gateway_defaults()
    area = load("area-gateway/gen-area-gateway-config.py", "area_cfg")
    ingress = load("ingress/gen-ingress-routes.py", "ingress_routes")
    assert area.DEFAULT_MAX_BODY == ingress.DEFAULT_MAX_BODY == want["max_body_bytes"]
    assert area.HEADER_DEFAULT == want["timeouts_ms"]["response_header"]
    # 사본 부재: 생성기 소스에 계약 값 리터럴이 다시 박히지 않는다(값이 바뀌어도 시험이 따라온다)
    literals = [str(want["max_body_bytes"]), "8 * 1024 * 1024"] + [str(v) for v in want["timeouts_ms"]["response_header"]["by_service"].values()] \
        + [str(want["timeouts_ms"]["response_header"]["default"])]
    for f in ("area-gateway/gen-area-gateway-config.py", "ingress/gen-ingress-routes.py"):
        text = (ROOT / f).read_text(encoding="utf-8")
        assert not [x for x in literals if x in text], (f, [x for x in literals if x in text])


def test_device_id_pattern_is_read_from_the_contract_not_copied():
    import subprocess, sys
    out = subprocess.run([sys.executable, str(ROOT / "ingress/gen-device-id-re.py")], capture_output=True, text=True, check=True).stdout.strip()
    contract = load_schema("DeviceAllowlist")["properties"]["devices"]["items"]["properties"]["device_id"]["pattern"]
    assert contract == "^" + out + "$(?![\\s\\S])"
    # 사본이 없다: Caddyfile 과 기기 인증서 보조 스크립트에 패턴 문자열이 다시 박히지 않는다
    for f in ("ingress/config/Caddyfile", "ingress/scripts/device-pki.sh"):
        assert out not in (ROOT / f).read_text(encoding="utf-8"), f
