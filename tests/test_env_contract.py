"""platform 이미지의 환경 입력은 계약 Env 스키마(3.4.10)대로 받는다: 기동 때 envcheck 가 검증하고 위반이면 종료 64, 통과하면 기본값이 채워진다. 이미지는 지금 이 리포에서 빌드한다(check=True 의미: 빌드 실패는 오류).
변이: 같은 이미지에 올바른 환경을 주면 통과한다(위반이 환경 때문임을 보인다)."""
import pytest
from ops_common import build, have_docker, sh, Stack

pytestmark = pytest.mark.skipif(not have_docker(), reason="Docker 가 필요하다")
TMP = ["--read-only", "--tmpfs", "/tmp"]


@pytest.fixture(scope="module")
def imgs():
    st = Stack("pe")
    tags = {}
    try:
        for v in ("monitoring", "backup-store", "step-ca", "identity", "identity-proxy", "identity-db", "public-ingress"):
            tags[v] = f"platform-env-{v}:t-{st.tag}"; build(v, tags[v])
        yield tags
    finally:
        for t in tags.values(): sh("docker", "rmi", t, check=False)
        st.close()


def rc(image, *args, env=(), entry=None, extra=()):
    cmd = ["docker", "run", "--rm", *TMP, *extra]
    for e in env: cmd += ["-e", e]
    if entry: cmd += ["--entrypoint", entry]
    return sh(*cmd, image, *args, check=False, timeout=60)


def test_monitoring_rejects_a_relative_ca_path_and_accepts_defaults(imgs):
    assert rc(imgs["monitoring"], "check", env=["MONITORING_ROOT_CA=relative.pem"]).returncode == 64
    assert rc(imgs["monitoring"], "check").returncode == 0   # 변이: 기본값이면 설정 점검까지 통과한다


def test_monitoring_substitutes_the_contract_inputs_into_the_generated_config(imgs):
    r = rc(imgs["monitoring"], "-c", "/usr/local/bin/openit-monitoring.sh check >/dev/null; grep -c '/custom/targets' /tmp/openit-monitoring/prometheus.yml; grep -c '/custom/ca.pem' /tmp/openit-monitoring/blackbox.yml",
           env=["MONITORING_TARGETS_DIR=/custom/targets", "MONITORING_ROOT_CA=/custom/ca.pem"], entry="sh")
    assert r.returncode == 0 and [int(x) > 0 for x in r.stdout.split()] == [True, True], r.stdout + r.stderr


def test_monitoring_rejects_a_name_outside_the_schema(imgs):
    assert rc(imgs["monitoring"], "check", env=["MONITORING_UNKNOWN=1"]).returncode == 64


def test_backup_store_rejects_a_bad_port(imgs):
    assert rc(imgs["backup-store"], env=["OPENIT_BACKUP_PORT=abc"]).returncode == 64
    assert rc(imgs["backup-store"], env=["OPENIT_BACKUP_PORT=8000"]).returncode == 2   # 변이: 환경은 통과하고 자격·TLS 가 없어 종료 2(다른 이유)


def test_step_ca_rejects_a_bad_port_and_a_relative_password_path(imgs):
    assert rc(imgs["step-ca"], "serve", env=["STEP_CA_PORT=0"]).returncode == 64
    assert rc(imgs["step-ca"], "serve", env=["STEP_CA_PASSWORD_FILE=pw"]).returncode == 64


def test_identity_images_reject_a_bad_public_url_and_report_missing_secret_files_by_name(imgs):
    r = rc(imgs["identity"], env=["IDENTITY_PUBLIC_URL=http://insecure.example"])
    assert r.returncode == 64 and "IDENTITY_PUBLIC_URL" in r.stderr and "형식" in r.stderr   # 환경 계약 위반
    r = rc(imgs["identity"], env=["IDENTITY_PUBLIC_URL=https://a.example"])
    assert r.returncode == 64 and "비밀 파일을 읽지 못했다" in r.stderr   # 변이: 환경이 맞으면 다음 단계(비밀 파일)에서 이름과 함께 거절한다
    assert rc(imgs["identity-proxy"]).returncode == 64   # IDENTITY_PUBLIC_URL 필수
    r = rc(imgs["identity-proxy"], env=["IDENTITY_PUBLIC_URL=https://a.example", "IDENTITY_SESSION_MAX=8"])
    assert r.returncode == 64 and "IDENTITY_SESSION_MAX" in r.stderr   # Duration 형식(단위 없음)


def test_identity_db_requires_the_superuser_password_file_and_declares_its_database(imgs):
    assert rc(imgs["identity-db"]).returncode == 64   # POSTGRES_PASSWORD_FILE 필수
    import json
    from boundary_contracts import validator
    lab = json.loads(sh("docker", "image", "inspect", imgs["identity-db"]).stdout)[0]["Config"]["Labels"]["io.openit.database"]
    assert not list(validator("DatabaseDeclaration").iter_errors(json.loads(lab)))
    inside = sh("docker", "run", "--rm", "--entrypoint", "cat", imgs["identity-db"], "/etc/openit/database.json").stdout
    assert json.loads(inside) == json.loads(lab)   # 라벨과 이미지가 쓰는 선언이 같다


def test_state_folders_are_declared_as_docker_volumes(imgs):
    # 배치는 이미지 선언(Config.Volumes)을 읽어 마운트하고 경로를 따로 알지 않는다. 변이: 상태가 없는 이미지(identity-proxy)는 볼륨이 없다
    import json
    def vols(tag):
        return set((json.loads(sh("docker", "image", "inspect", tag).stdout)[0]["Config"].get("Volumes") or {}))
    assert "/home/step" in vols(imgs["step-ca"])
    assert {"/prometheus", "/alertmanager"} <= vols(imgs["monitoring"])
    assert "/data" in vols(imgs["backup-store"])
    assert "/var/lib/postgresql/data" in vols(imgs["identity-db"])
    assert "/data" in vols(imgs["public-ingress"])
    assert vols(imgs["identity-proxy"]) == set()


def test_monitoring_accepts_a_concatenated_root_bundle(imgs):
    # MONITORING_ROOT_CA 는 여러 PEM 을 이어 붙인 파일을 받는다(step-ca 루트 + 공개 입구 사설 CA 루트)
    import pathlib, tempfile
    d = pathlib.Path(tempfile.mkdtemp()); d.chmod(0o755)
    for n in ("a", "b"):
        sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(d / f"{n}.key"), "-out", str(d / f"{n}.crt"), "-subj", f"/CN=root-{n}", "-days", "2")
    (d / "bundle.pem").write_text((d / "a.crt").read_text() + (d / "b.crt").read_text()); (d / "bad.pem").write_text("not a pem\n")
    for f in d.glob("*"): f.chmod(0o644)
    ok = rc(imgs["monitoring"], "check", env=["MONITORING_ROOT_CA=/ca/bundle.pem"], extra=["-v", f"{d}:/ca:ro"])
    assert ok.returncode == 0, ok.stdout + ok.stderr


def test_public_ingress_refuses_internal_mode_when_the_root_export_dir_is_unwritable(imgs):
    # 계약 PublicIngressEnv.INGRESS_ROOT_EXPORT_DIR: internal 모드는 루트를 거기에 써야 한다. 읽기 전용 루트 파일시스템의 기본 폴더(쓸 수 없음)에서는 시작하지 않는다
    import pathlib, tempfile
    d = pathlib.Path(tempfile.mkdtemp()); (d / "ca.pem").write_text("-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----\n"); (d / "ca.pem").chmod(0o644); d.chmod(0o755)
    base = ["--read-only", "--tmpfs", "/tmp", "-e", "GATEWAY_HOSTS=localhost", "-v", f"{d}/ca.pem:/etc/openit/device-ca.pem:ro"]
    r = sh("docker", "run", "--rm", *base, imgs["public-ingress"], "validate", check=False)
    assert r.returncode == 64 and "루트 내보내기 폴더" in r.stderr
    # 변이: files 모드는 사설 CA 를 쓰지 않으므로 이 폴더를 요구하지 않는다(다음 단계에서 다른 이유로 거절)
    r = sh("docker", "run", "--rm", *base, "-e", "GATEWAY_TLS_MODE=files", imgs["public-ingress"], "validate", check=False)
    assert "루트 내보내기 폴더" not in r.stderr
