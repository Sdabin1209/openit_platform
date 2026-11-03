"""공개 입구 경로 표 생성기(ingress/gen-ingress-routes.py) 규칙: denied 는 경로를 만들지 않고, 같은 공개 경로를 두 영역이 열면 거부한다(HTTP.md I1, 헤드 결정)."""
import json, pathlib, subprocess, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parent.parent
GEN = ROOT / "ingress/gen-ingress-routes.py"


def run(*exposures):
    d = pathlib.Path(tempfile.mkdtemp())
    for i, e in enumerate(exposures):
        (d / f"{i}.json").write_text(json.dumps(e))
    return subprocess.run([sys.executable, "-I", str(GEN), str(d)], capture_output=True, text=True)


def ex(service, path, kind="none", **kw):
    r = {"paths": [path], "methods": ["GET"], "auth": {"kind": kind}, **kw}
    return {"service": service, "routes": [r]}


def test_denied_creates_no_route():
    r = run(ex("a", "/v1/x", "denied"), ex("b", "/v1/y"))
    assert r.returncode == 0 and "path /v1/x" not in r.stdout and "path /v1/y" in r.stdout


def test_denied_by_one_area_and_opened_by_another_is_served_by_the_opener():
    r = run(ex("a", "/v1/question-sets", "denied"), ex("b", "/v1/question-sets"))
    assert r.returncode == 0 and "path /v1/question-sets" in r.stdout


def test_same_public_path_opened_by_two_areas_refuses_to_start():
    r = run(ex("a", "/readyz"), ex("b", "/readyz"))
    assert r.returncode != 0 and "/readyz" in r.stderr


def test_mutation_different_paths_start_fine():
    assert run(ex("a", "/readyz"), ex("b", "/v1/z")).returncode == 0
