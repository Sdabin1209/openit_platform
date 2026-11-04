"""platform 이미지가 라벨 io.openit.jobs(JobsDeclaration)로 내는 잡(3.4.16, RUNTIME R10.1 데이터 주인 백업): 라벨은 계약 validator 로, 백업·복구 잡은 라벨의 argv 그대로 실제 백업 저장소(rest-server https)에 돌려 본다.
결과는 BackupJobResult(표준 출력 마지막 줄), 종료 코드 0 ok / 75 재시도 가능 / 1 그 밖의 실패. 변이: 자격이 틀리면 1(failed), 저장소가 멈추면 75, 라벨이 없거나 깨지면 검증 실패."""
import json
import pytest
from boundary_contracts import validator
from ops_common import Stack, build, have_docker, make_ca, sh

pytestmark = pytest.mark.skipif(not have_docker(), reason="Docker 가 필요하다")
HARD = ["--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp"]
REPO_PW, AREA_PW = "repo-pass", "platform-pass"
UID = {"public-ingress": 10001, "step-ca": 1000}   # 잡은 이미지의 비루트 사용자로 돈다(deploy 가 볼륨을 그 사용자 소유로 둔다)
IMAGES = {"public-ingress": ("gateway-backup", "gateway-restore", "/data", "INGRESS_ROOT_CA", "gateway-data"),
          "step-ca": ("pki-backup", "pki-restore", "/home/step", "STEP_CA_HOME", "pki-ca")}


def jobs_of(labels, service):
    raw = labels.get("io.openit.jobs")
    assert raw, "라벨 io.openit.jobs 가 없다"
    d = json.loads(raw)
    errs = list(validator("JobsDeclaration").iter_errors(d))
    assert not errs, errs[0].message
    return {j["name"]: j for j in d["jobs"]}


@pytest.fixture(scope="module")
def stack():
    st = Stack("pjob")
    tags = {}
    try:
        for v in list(IMAGES) + ["identity", "backup-store"]:
            tags[v] = f"platform-job-{v}:t-{st.tag}"; build(v, tags[v])
        labels = {v: json.loads(sh("docker", "image", "inspect", tags[v]).stdout)[0]["Config"]["Labels"] for v in tags}
        make_ca(st.d, "tls", "backup-store")
        for d in ("areas", "tlsdir", "sec"): (st.d / d).mkdir(); (st.d / d).chmod(0o755)
        (st.d / "areas/platform").write_text(f"platform:{AREA_PW}\n")
        (st.d / "tlsdir/tls.crt").write_text((st.d / "tls.crt").read_text()); (st.d / "tlsdir/tls.key").write_text((st.d / "tls.key").read_text())
        (st.d / "sec/creds").write_text(f"platform:{AREA_PW}\n"); (st.d / "sec/badcreds").write_text("platform:zz-sekret-9f3\n"); (st.d / "sec/repopw").write_text(REPO_PW)
        for f in list((st.d / "areas").glob("*")) + list((st.d / "tlsdir").glob("*")) + list((st.d / "sec").glob("*")): f.chmod(0o644)
        v = st.volume("bsdata")
        sh("docker", "run", "--rm", "-v", f"{v}:/data", "--user", "0", "--entrypoint", "chown", tags["backup-store"], "65534:65534", "/data")
        st.run("backup-store", "--network-alias", "backup-store", *HARD, "-v", f"{v}:/data", "-v", f"{st.d}/areas:/run/secrets/areas:ro", "-v", f"{st.d}/tlsdir:/run/tls:ro", tags["backup-store"])
        st.tags, st.labels = tags, labels
        yield st
    finally:
        for t in tags.values(): sh("docker", "rmi", t, check=False)
        st.close()


def run_job(st, service, job, volume, *, creds="creds", url="https://backup-store:8000/platform"):
    """라벨이 선언한 argv 그대로 잡을 돌린다. deploy 가 하는 일(볼륨 연결, 비밀 파일, 환경)을 같게 흉내 낸다."""
    name, _, mount, envname, _need = IMAGES[service]
    j = jobs_of(st.labels[service], service)[job]
    assert j["idempotent"] is True
    envval = mount if envname == "STEP_CA_HOME" else "/ca.pem"
    argv = j["argv"]
    r = sh("docker", "run", "--rm", "--network", st.net, *HARD, "-v", f"{volume}:{mount}", "-v", f"{st.d}/root_ca.crt:/ca.pem:ro", "-v", f"{st.d}/root_ca.crt:/etc/openit/pki/root_ca.crt:ro", "-v", f"{st.d}/sec:/sec:ro",
           "-e", f"OPENIT_BACKUP_URL={url}", "-e", f"OPENIT_BACKUP_CREDENTIALS_FILE=/sec/{creds}", "-e", "OPENIT_BACKUP_REPO_PASSWORD_FILE=/sec/repopw", "-e", f"{envname}={envval}",
           "--entrypoint", argv[0], st.tags[service], *argv[1:], check=False, timeout=300)
    last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    return r.returncode, json.loads(last) if last.startswith("{") else None, r


@pytest.mark.parametrize("service", list(IMAGES))
def test_job_labels_are_valid_declarations_with_the_needed_volume(stack, service):
    jobs = jobs_of(stack.labels[service], service)
    b, r, mount, envname, need = IMAGES[service]
    assert set(jobs) == {b, r}
    for j in jobs.values():
        assert j["needs"] == [need] and "OPENIT_BACKUP_URL" in j["env"] and envname in j["env"]
        assert set(j["secret_files"]) == {"OPENIT_BACKUP_CREDENTIALS_FILE", "OPENIT_BACKUP_REPO_PASSWORD_FILE"}


def test_identity_users_job_label_declares_the_config_schema(stack):
    j = jobs_of(stack.labels["identity"], "identity")["register-users"]
    assert j["config"] == {"container_path": "/etc/openit/identity-users.json", "schema": "IdentityUsersConfig"}
    assert j["secret_files"] == ["IDENTITY_ADMIN_PASSWORD_FILE"] and j["idempotent"] is True
    assert j["argv"][-1] == j["config"]["container_path"]   # 잡이 읽는 설정 경로와 선언이 같다


def test_mutation_missing_or_broken_jobs_label_fails_validation(stack):
    stripped = {k: v for k, v in stack.labels["identity"].items() if k != "io.openit.jobs"}
    with pytest.raises(AssertionError):
        jobs_of(stripped, "identity")
    with pytest.raises(AssertionError):
        jobs_of({"io.openit.jobs": '{"jobs":[{"name":"x","argv":["a"]}]}'}, "identity")   # idempotent 없음


@pytest.mark.parametrize("service", list(IMAGES))
def test_backup_then_restore_round_trip_with_backup_job_result(stack, service):
    b, r, mount, envname, need = IMAGES[service]
    src, dst = stack.volume(f"src-{service}"), stack.volume(f"dst-{service}")
    own = f"{UID[service]}:{UID[service]}"; st_d = stack.d
    sh("docker", "run", "--rm", "-v", f"{st_d}/root_ca.crt:/ca.pem:ro", "-v", f"{src}:{mount}", "--user", "0", "--entrypoint", "sh", stack.tags[service], "-c", f"mkdir -p {mount}/certs && cp /ca.pem {mount}/certs/root_ca.crt && echo state > {mount}/state.txt && chown -R {own} {mount}")
    sh("docker", "run", "--rm", "-v", f"{dst}:{mount}", "--user", "0", "--entrypoint", "sh", stack.tags[service], "-c", f"chown -R {own} {mount}")
    rc, res, run = run_job(stack, service, b, src)
    assert rc == 0 and res and res["status"] == "ok" and res["snapshot_id"] and res["bytes"] > 0, run.stdout[-400:] + run.stderr[-400:]
    assert not list(validator("BackupJobResult").iter_errors(res))
    rc2, res2, _ = run_job(stack, service, b, src)   # 멱등: 다시 돌려도 ok(새 스냅숏)
    assert rc2 == 0 and res2["status"] == "ok"
    rc3, res3, run3 = run_job(stack, service, r, dst)   # 빈 볼륨으로 복구
    assert rc3 == 0 and res3 and res3["status"] == "ok" and not list(validator("BackupJobResult").iter_errors(res3)), run3.stdout[-400:] + run3.stderr[-400:]
    got = sh("docker", "run", "--rm", "-v", f"{dst}:{mount}", "--entrypoint", "cat", stack.tags[service], f"{mount}/state.txt").stdout
    assert got.strip() == "state"   # 복구 결과가 원본과 같다


def test_mutation_wrong_credentials_fail_and_unreachable_store_is_retryable(stack):
    vol = stack.volume("mut")
    sh("docker", "run", "--rm", "-v", f"{vol}:/data", "-v", f"{vol}:/home/step", "--user", "0", "--entrypoint", "chown", stack.tags["public-ingress"], "-R", "10001:10001", "/data")
    rc, res, run = run_job(stack, "public-ingress", "gateway-backup", vol, creds="badcreds")
    assert rc == 1 and res["status"] == "failed" and res["error"]["retryable"] is False and "zz-sekret-9f3" not in run.stdout + run.stderr   # 비밀 값이 출력에 없다
    assert not list(validator("BackupJobResult").iter_errors(res))
    rc, res, _ = run_job(stack, "public-ingress", "gateway-backup", vol, url="https://no-such-store:8000/platform")
    assert rc == 75 and res["status"] == "failed" and res["error"]["retryable"] is True
    rc, res, _ = run_job(stack, "step-ca", "pki-restore", vol, url="https://backup-store:8000/platform-empty")   # 스냅숏이 없는 저장소에서 복구
    assert rc == 1 and res["status"] == "failed"
