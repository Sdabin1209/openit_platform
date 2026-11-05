"""pytest 시작 때 docker 환경을 한 곳(scripts/docker-env.sh)에서 받는다: 사용자 전역 ~/.docker 에 기대지 않는다(DOCKER_CONFIG 가 있으면 그대로)."""
import os, pathlib, shlex, subprocess

_ROOT = pathlib.Path(__file__).resolve().parent.parent
for _line in subprocess.run(["bash", str(_ROOT / "scripts/docker-env.sh")], capture_output=True, text=True).stdout.splitlines():
    if _line.startswith("export "):
        _k, _, _v = _line[len("export "):].partition("=")
        os.environ.setdefault(_k, shlex.split(_v)[0])
