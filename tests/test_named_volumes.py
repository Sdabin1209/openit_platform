"""이름 있는 볼륨의 첫 마운트 복사(Docker 표준): 빈 볼륨을 이미지의 마운트 경로에 붙이면 그 경로 디렉터리의 소유자·모드가 복사된다. deploy 는 권한을 조정하지 않는다(0777 로 여는 우회 없음).
시험: 빈 이름 있는 볼륨을 붙여 이미지 사용자로 쓸 수 있고, 다른 uid·보조 그룹 10100 컨테이너가 읽는다. 변이: 이미지에 없는 경로에 붙이면(= 디렉터리를 이미지에서 뺀 것과 같다) 쓰기가 실패한다."""
import pytest
from ops_common import Stack, build, sh

pytestmark = pytest.mark.usefixtures("docker_required")   # Docker 없으면 실패(ADR 0019)


@pytest.fixture(scope="module")
def imgs():
    st = Stack("pnv")
    tags = {}
    try:
        for v in ("step-ca", "public-ingress"):
            tags[v] = f"platform-nv-{v}:t-{st.tag}"; build(v, tags[v])
        tags["st"] = st
        yield tags
    finally:
        for k, t in tags.items():
            if k != "st": sh("docker", "rmi", t, check=False)
        st.close()


def run(image, vol, mount, script, *, user=None, group=None):
    cmd = ["docker", "run", "--rm", "-v", f"{vol}:{mount}", "--entrypoint", "sh"]
    if user: cmd += ["--user", user]
    if group: cmd += ["--group-add", group]
    return sh(*cmd, image, "-c", script, check=False)


@pytest.mark.parametrize("mount,mode,group_readable", [("/certs", "0640", True), ("/tokens", "0644", False), ("/out", "0644", False)])
def test_step_ca_empty_named_volume_is_writable_by_the_image_user_and_readable_by_group_10100(imgs, mount, mode, group_readable):
    st = imgs["st"]; vol = st.volume(f"v{mount.strip('/')}")
    w = run(imgs["step-ca"], vol, mount, f"umask 0; echo data > {mount}/f && chmod {mode[1:]} {mount}/f" + (f" && chgrp 10100 {mount}/f" if group_readable else ""))   # 인증서 폴더의 키는 진입점이 하는 대로 그룹 10100 으로 맞춘다(step 은 이 그룹 구성원)   # 이미지 사용자(step)로, 권한 조정 없이
    assert w.returncode == 0, w.stderr
    # 다른 uid(10002) 가 보조 그룹 10100 으로 읽는다. 키 모드(0640)는 그룹으로만, 0644 는 누구나
    r = run(imgs["step-ca"], vol, mount, f"cat {mount}/f", user="10002:10002", group="10100")
    assert r.returncode == 0 and r.stdout.strip() == "data", r.stderr
    if mode == "0640":   # 그룹 없는 다른 uid 는 키를 못 읽는다(키 보호)
        assert run(imgs["step-ca"], vol, mount, f"cat {mount}/f", user="10002:10002").returncode != 0


def test_public_ingress_root_export_dir_is_writable_by_the_image_user_and_readable_by_others(imgs):
    st = imgs["st"]; vol = st.volume("rootout")
    assert run(imgs["public-ingress"], vol, "/etc/openit/root-out", "echo cert > /etc/openit/root-out/root_ca.crt").returncode == 0
    assert run(imgs["public-ingress"], vol, "/etc/openit/root-out", "cat /etc/openit/root-out/root_ca.crt", user="10002:10002").stdout.strip() == "cert"


def test_mutation_a_path_missing_from_the_image_gives_a_root_owned_volume_the_image_user_cannot_write(imgs):
    st = imgs["st"]; vol = st.volume("missing")
    assert run(imgs["step-ca"], vol, "/not-in-image", "echo x > /not-in-image/f").returncode != 0
