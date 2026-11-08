"""하위 프로세스에 줄 최소 환경 한 곳(RUNTIME R9.1: 시험·잡은 상속받은 환경 변수를 통째로 쓰거나 넘기지 않는다).
허용 목록은 head check-container-inputs 와 같은 최소 집합이다. 호출에 더 필요한 이름은 이름으로 더한다(minimal_env("DOCKER")) 또는 값으로 준다(minimal_env(KEY="v"))."""
import os

ALLOWED = ("PATH", "HOME", "LANG", "TMPDIR", "DOCKER_CONFIG", "DOCKER_HOST")


def minimal_env(*names, **values):
    env = {k: os.environ[k] for k in ALLOWED + names if k in os.environ}
    env.update(values)
    return env
