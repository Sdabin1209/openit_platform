"""영역 구조(DESIGN.md 6절): 컴포넌트는 서로 import 하지 않고, 영역 내부 스키마에는 통과·거부 예시가 있으며 결과가 맞고, types/ 가 스키마에서 다시 생성한 것과 같다."""
from ops_common import minimal_env
import json, pathlib, re, subprocess, sys
import pytest
from boundary_contracts import schema_validator

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENTS = sorted((ROOT / "openit_platform/components").glob("[a-z]*.py"))


@pytest.mark.parametrize("path", COMPONENTS, ids=lambda p: p.stem)
def test_components_do_not_import_each_other(path):
    others = {p.stem for p in COMPONENTS if p != path}
    for m in re.finditer(r"^\s*(?:from|import)\s+openit_platform\.(\w+)(?:\.(\w+))?", path.read_text(encoding="utf-8"), re.M):
        assert not (m.group(1) == "components" and m.group(2) in others), (path.name, m.group(0))
        assert m.group(1) != "wiring", (path.name, "컴포넌트는 조립을 알지 못한다")


@pytest.mark.parametrize("schema", sorted((ROOT / "ingress/schemas").glob("*.json")), ids=lambda p: p.stem)
def test_schema_examples_pass_and_fail_as_named(schema):
    check = schema_validator(json.loads(schema.read_text(encoding="utf-8")))
    examples = sorted((schema.parent / "examples").glob(schema.stem + ".*.json"))
    valid = [e for e in examples if ".valid" in e.name]
    invalid = [e for e in examples if ".invalid" in e.name]
    assert valid and invalid
    for e in valid:
        assert check.is_valid(json.loads(e.read_text(encoding="utf-8"))), e.name
    for e in invalid:
        assert not check.is_valid(json.loads(e.read_text(encoding="utf-8"))), e.name


def test_types_are_regenerated_from_schemas():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/gen-types.py"), "--check"], capture_output=True, text=True, env=minimal_env())
    assert r.returncode == 0, r.stderr
