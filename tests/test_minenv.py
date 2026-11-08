"""최소 환경(scripts/minenv.py)이 Docker 연결 이름을 전달하는지 본다(R9.1 허용 목록 + Docker CLI 공식 변수). 값은 가짜이고 출력하지 않는다."""
import subprocess, sys
from ops_common import ROOT, minimal_env
from minenv import DOCKER_NAMES

PRINT = "import os,sys;sys.stdout.write(','.join(sorted(k for k in os.environ if k in sys.argv[1].split(','))))"


def test_docker_connection_names_reach_child(monkeypatch):
    for k in DOCKER_NAMES:
        monkeypatch.setenv(k, "fake-" + k.lower())
    monkeypatch.setenv("UNLISTED_SECRET_NAME", "x")
    r = subprocess.run([sys.executable, "-I", "-c", PRINT, ",".join(DOCKER_NAMES) + ",UNLISTED_SECRET_NAME"], capture_output=True, text=True, env=minimal_env("DOCKER"))
    assert set(r.stdout.split(",")) == set(DOCKER_NAMES)   # 허용 목록에 없는 이름은 넘어가지 않는다


def test_docker_names_cover_official_connection_variables():
    assert {"DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "DOCKER_CONFIG"} <= set(DOCKER_NAMES)
