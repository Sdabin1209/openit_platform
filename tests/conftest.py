"""pytest 시작 때 docker 환경을 한 곳(scripts/docker-env.sh)에서 받는다: 사용자 전역 ~/.docker 에 기대지 않는다(DOCKER_CONFIG 가 있으면 그대로).
Docker 가 필요한 시험은 Docker 가 없으면 건너뛰지 않고 실패한다(fixture docker_required)."""
import pathlib, sys
import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))   # 공용 최소 환경(scripts/minenv.py)
from minenv import apply_docker_env
apply_docker_env(_ROOT)


@pytest.fixture(scope="session")
def docker_required():
    """왜 건너뛰지 않고 실패: skipif 면 다른 context·TLS 엔진에서 gateway/mTLS/변이 시험이 통째로 빠진 채 rc=0 이 된다(조용한 건너뜀 통과 금지, ADR 0019)."""
    sys.path.insert(0, str(_ROOT / "tests"))
    from ops_common import have_docker
    if not have_docker():
        pytest.fail("Docker 엔진에 닿지 못했다: 이 시험은 Docker 가 필요하다(건너뛰지 않는다)", pytrace=False)
