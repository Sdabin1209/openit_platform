"""공개 입구의 셸 시험(장애·중계 R2.1·R3.1~R3.6·R4.1, 기기 인증서 mTLS)을 test 줄기에 올린다: 돌지 않는 시험은 점검이 아니다.
정상 실행은 종료 코드 0, 변이(일부러 망가뜨린 설정)는 종료 코드 1 이어야 한다(단언이 실제로 잡는지). 이미지는 각 시험이 지금 이 리포에서 빌드한다."""
import os, pathlib, subprocess
import pytest
from ops_common import have_docker

ROOT = pathlib.Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not have_docker(), reason="Docker 가 필요하다")


def run(script, **env):
    e = dict(os.environ, **env)
    return subprocess.run(["bash", str(ROOT / "ingress/tests" / script)], capture_output=True, text=True, env=e, timeout=1500)


def test_gateway_faults_pass():
    r = run("test-gateway-faults.sh")
    assert r.returncode == 0, r.stdout[-2500:] + r.stderr[-800:]


@pytest.mark.parametrize("mutation", ["503", "413"])
def test_gateway_faults_mutation_is_caught(mutation):
    r = run("test-gateway-faults.sh", FAULTS_MUTATE=mutation, FAULTS_QUICK="1")
    assert r.returncode == 1 and "FAIL" in r.stdout, r.stdout[-1500:] + r.stderr[-500:]


def test_device_mtls_pass():
    r = run("test-device-mtls.sh")
    assert r.returncode == 0, r.stdout[-2500:] + r.stderr[-800:]


def test_device_mtls_mutation_verification_off_is_caught():
    r = run("test-device-mtls.sh", MTLS_MUTATE="1")
    assert r.returncode == 1 and "FAIL" in r.stdout, r.stdout[-1500:] + r.stderr[-500:]
