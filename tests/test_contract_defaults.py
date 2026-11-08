"""계약에 산문으로만 있는 기본값(본문 상한 8MiB, 응답 헤더 사슬)의 platform 사본이 고정 태그의 계약과 같은지 정적으로 본다(D117).
왜 시험인가: 스키마에 기계가 읽는 칸이 없어 사본을 지울 수 없다(변경 요청 docs/change-requests/2026-11-08-exposure-machine-readable-defaults.md)."""
import importlib.util, pathlib, re
from boundary_contracts import load_schema
from ops_common import boundary_src

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_body_limit_copies_match_the_contract_description():
    text = load_schema("Exposure")["$defs"]["route"]["properties"]["max_body_bytes"]["description"]
    contract = int(re.search(r"8MiB\((\d+)", text).group(1))
    assert contract == 8388608
    assert load("area-gateway/gen-area-gateway-config.py", "area_cfg").DEFAULT_MAX_BODY == contract
    assert load("ingress/gen-ingress-routes.py", "ingress_routes").DEFAULT_MAX_BODY == contract


def test_header_chain_defaults_match_the_contract_conventions_table():
    conventions = (pathlib.Path(boundary_src()) / "CONVENTIONS.md").read_text(encoding="utf-8")
    rows = dict(re.findall(r"^\| (release-gate|question-authoring|ops-feedback) [^|]*\| \d+초\((\d+)\) \|", conventions, re.M))
    assert set(rows) == {"release-gate", "question-authoring", "ops-feedback"}, rows
    module = load("area-gateway/gen-area-gateway-config.py", "area_cfg2")
    assert module.HEADER_CHAIN_MS == {k: int(v) * 1000 for k, v in rows.items()}
    # 표에 행이 없는 환자·직원 경로: 연결 1초 + 응답 헤더 55초 = 56초
    assert re.search(r"gateway 환자·직원 경로\(연결 1초 \+ 응답 헤더 55초\)", conventions)
    assert module.DEFAULT_HEADER_MS == 55000


def test_device_id_pattern_is_read_from_the_contract_not_copied():
    import subprocess, sys
    out = subprocess.run([sys.executable, str(ROOT / "ingress/gen-device-id-re.py")], capture_output=True, text=True, check=True).stdout.strip()
    contract = load_schema("DeviceAllowlist")["properties"]["devices"]["items"]["properties"]["device_id"]["pattern"]
    assert contract == "^" + out + "$(?![\\s\\S])"
    # 사본이 없다: Caddyfile 과 기기 인증서 보조 스크립트에 패턴 문자열이 다시 박히지 않는다
    for f in ("ingress/config/Caddyfile", "ingress/scripts/device-pki.sh"):
        assert out not in (ROOT / f).read_text(encoding="utf-8"), f
