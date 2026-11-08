"""하위 프로세스에 줄 최소 환경 한 곳(RUNTIME R9.1: 시험·잡은 상속받은 환경 변수를 통째로 쓰거나 넘기지 않는다).
허용 목록은 head check-container-inputs 와 같은 최소 집합이다. 호출에 더 필요한 이름은 이름으로 더한다(minimal_env("DOCKER")) 또는 값으로 준다(minimal_env(KEY="v"))."""
import os

# 왜: Docker CLI 공식 연결 환경 변수(DOCKER_HOST·DOCKER_CONTEXT·DOCKER_TLS_VERIFY·DOCKER_CERT_PATH·DOCKER_CONFIG)와 ssh:// 엔진용 SSH_AUTH_SOCK 을 버리면
# 다른 context·TLS·ssh 엔진에서 docker 가 안 닿아 시험이 건너뛰어진다(codex C2 검토 P2, 2026-11-09). 값은 상속받은 것을 그대로 전달만 한다.
DOCKER_NAMES = ("DOCKER_CONFIG", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "SSH_AUTH_SOCK")
ALLOWED = ("PATH", "HOME", "LANG", "TMPDIR") + DOCKER_NAMES


def minimal_env(*names, **values):
    env = {k: os.environ[k] for k in ALLOWED + names if k in os.environ}
    env.update(values)
    return env


def apply_docker_env(root):
    """scripts/docker-env.sh 가 낸 줄(export NAME='v' / unset NAME)을 os.environ 에 반영한다(conftest·smoke 가 같은 한 곳을 쓴다, D117)."""
    import pathlib, subprocess
    out = subprocess.run(["bash", str(pathlib.Path(root) / "scripts/docker-env.sh")], capture_output=True, text=True, env=minimal_env("DOCKER")).stdout
    for line in out.splitlines():
        if line.startswith("export "):
            k, _, v = line[len("export "):].partition("=")
            os.environ.setdefault(k, v.strip("'"))
        elif line.startswith("unset "):
            os.environ.pop(line[len("unset "):], None)
