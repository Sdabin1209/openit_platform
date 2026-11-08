"""백업 저장소(RUNTIME R10.1, ADR 0011) 시험: 실제 restic 클라이언트(잠금된 restic 이미지)로 백업·복구 왕복, 다른 영역 자격으로 남의 경로 접근 거부,
보존 정리(forget --prune)가 성공, 변이(--private-repos 를 빼면 남의 경로가 열린다 = 시험이 막는다는 증거). Docker 필요."""
import pathlib, time, pytest
from ops_common import ROOT, Stack, build, lock, sh, make_ca

pytestmark = pytest.mark.usefixtures("docker_required")   # Docker 없으면 실패(ADR 0019)
IMAGE = "platform-x:backup-store"
AREAS = {"survey-service": "pw-survey-test", "ops-feedback": "pw-ops-test"}   # 시험용 임의 값(비밀 아님)
REPO_PW = "repo-pass-test"
HARD = ["--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true"]


@pytest.fixture(scope="module")
def st():
    s = Stack("pbs")
    try:
        build("backup-store", IMAGE)
        make_ca(s.d, "tls", "backup-store")
        (s.d / "areas").mkdir()
        for a, pw in AREAS.items():
            (s.d / "areas" / a).write_text(f"{a}:{pw}\n")
        (s.d / "tlsdir").mkdir()
        (s.d / "tlsdir/tls.crt").write_text((s.d / "tls.crt").read_text()); (s.d / "tlsdir/tls.key").write_text((s.d / "tls.key").read_text())
        for p in (s.d / "areas").glob("*"): p.chmod(0o644)
        for p in (s.d / "tlsdir").glob("*"): p.chmod(0o644)
        (s.d / "areas").chmod(0o755); (s.d / "tlsdir").chmod(0o755)
        (s.d / "pw").write_text(REPO_PW)
        (s.d / "data").mkdir(); (s.d / "data/f.txt").write_text("hello-backup\n" * 50)
        (s.d / "pw").chmod(0o644); (s.d / "data/f.txt").chmod(0o644); (s.d / "data").chmod(0o755)
        v = s.volume("bsdata")
        sh("docker", "run", "--rm", "-v", f"{v}:/data", "--user", "0", "--entrypoint", "chown", IMAGE, "65534:65534", "/data")
        s.vol = v
        yield s
    finally:
        s.close()


def serve(st, name, entrypoint_override=None, areas=True, tls=True):
    args = [*HARD, "--network-alias", "backup-store", "-v", f"{st.vol}:/data"]
    if areas: args += ["-v", f"{st.d}/areas:/run/secrets/areas:ro"]
    if tls: args += ["-v", f"{st.d}/tlsdir:/run/tls:ro"]
    if entrypoint_override: args += ["-v", f"{entrypoint_override}:/e.sh:ro", "--entrypoint", "/e.sh"]
    return st.run(name, *args, IMAGE)


def restic(st, area, *cmd, repo_area=None, pw=None, repo_pw=REPO_PW, cwd_mounts=()):
    """영역 백업 잡이 하는 그대로: 자격 파일 한 줄을 읽어 RESTIC_REST_* 로 restic 에 준다(영역 게이트웨이 대신 같은 네트워크)."""
    area_pw = AREAS[area] if pw is None else pw
    script = 'export RESTIC_REST_USERNAME="$U" RESTIC_REST_PASSWORD="$P"; exec restic --cacert /ca.crt "$@"'
    r = sh("docker", "run", "--rm", "--network", st.net, "--entrypoint", "sh",
           "-e", f"U={area}", "-e", f"P={area_pw}", "-e", f"RESTIC_REPOSITORY=rest:https://backup-store:8000/{repo_area or area}", "-e", f"RESTIC_PASSWORD={repo_pw}",
           "-v", f"{st.d}/root_ca.crt:/ca.crt:ro", *cwd_mounts, lock("RESTIC_IMAGE"), "-c", script, "restic", *cmd, check=False, timeout=180)
    return r


def wait_up(st, name):
    import time
    for _ in range(30):
        r = restic(st, "survey-service", "cat", "config")   # 저장소가 없어도 서버가 답하면(오류 문구가 달라도) 닿은 것이다
        if "connection refused" not in (r.stdout + r.stderr) and "no such host" not in (r.stdout + r.stderr): return
        time.sleep(1)
    raise AssertionError("저장소가 뜨지 않았다:\n" + st.logs(name))


def test_image_hardening_and_labels(st):
    import json
    img = json.loads(sh("docker", "image", "inspect", IMAGE).stdout)[0]
    assert img["Config"]["User"] == "65534"
    assert img["Config"]["Labels"]["io.openit.service"] == "backup-store"


def test_roundtrip_forget_prune_and_cross_area_denied(st):
    c = serve(st, "bs")
    wait_up(st, c)
    # 하드닝: 실제 프로세스가 비루트이고 읽기 전용 루트에서 돈다
    assert sh("docker", "exec", c, "id", "-u").stdout.strip() == "65534"
    assert sh("docker", "inspect", "-f", "{{.HostConfig.ReadonlyRootfs}}", c).stdout.strip() == "true"
    mount = ["-v", f"{st.d}/data:/src:ro"]
    assert restic(st, "survey-service", "init").returncode == 0
    assert restic(st, "survey-service", "backup", "--host", "h", "/src", cwd_mounts=mount).returncode == 0
    # 복구 왕복: 다른 폴더로 복구해 원본과 같은지 본다
    out = st.d / "restored"; out.mkdir(); out.chmod(0o777)
    r = restic(st, "survey-service", "restore", "latest", "--target", "/out", cwd_mounts=["-v", f"{out}:/out"])
    assert r.returncode == 0, r.stderr[-300:]
    assert (out / "src/f.txt").read_text() == (st.d / "data/f.txt").read_text()
    # 영역마다 다른 저장 경로: 데이터가 /data/survey-service 아래에만 있다
    assert sh("docker", "exec", c, "ls", "/data").stdout.split() == ["survey-service"]
    # 보존 정리: append-only 가 아니므로 forget --prune 이 성공한다(헤드 결정, ADR 0011)
    assert restic(st, "survey-service", "backup", "--host", "h", "/src", "--tag", "again", cwd_mounts=mount).returncode == 0
    r = restic(st, "survey-service", "forget", "--keep-last", "1", "--prune")
    assert r.returncode == 0, r.stderr[-300:]
    snaps = restic(st, "survey-service", "snapshots", "--json")
    import json; assert len(json.loads(snaps.stdout)) == 1
    # 다른 영역 자격으로 남의 경로: 읽기·쓰기·init 모두 거부(rest-server 는 401 로 답한다: 측정함)
    for cmd in (("snapshots",), ("cat", "config"), ("init",)):
        r = restic(st, "ops-feedback", *cmd, repo_area="survey-service")
        assert r.returncode != 0 and any(x in (r.stdout + r.stderr) for x in ("401", "403")), (cmd, r.stderr[-300:])
    # 자기 경로는 되고(초기화), 남이 만든 저장소 폴더는 영향 없다
    assert restic(st, "ops-feedback", "init").returncode == 0
    # 틀린 암호는 401, 자격 없음은 닿지만 거부
    r = restic(st, "survey-service", "snapshots", pw="wrong")
    assert r.returncode != 0 and "401" in (r.stdout + r.stderr)
    # 틀린 저장소 암호(restic 암호화)로는 열 수 없다
    r = restic(st, "survey-service", "snapshots", repo_pw="wrong-repo-pass")
    assert r.returncode != 0
    # 저장소 파일에 평문이 없다(restic 암호화; 서버는 암호를 모른다)
    assert sh("docker", "exec", c, "sh", "-c", "grep -rqa hello-backup /data; echo $?").stdout.strip() == "1"
    # 로그에 암호가 없다
    lg = st.logs(c)
    assert not any(pw in lg for pw in AREAS.values())


def test_mutation_without_private_repos_cross_access_open(st):
    """변이 1회: --private-repos 를 뺀 서버에서는 같은 '남의 경로 접근' 이 열린다. 위 시험이 이 설정에 기대어 거부를 잡는다는 증거."""
    e = pathlib.Path(st.d) / "mut.sh"
    src = (ROOT / "backup-store/entrypoint.sh").read_text().replace("--private-repos ", "")
    assert "--private-repos" not in src
    e.write_text(src); e.chmod(0o755)
    c = serve(st, "bsmut", entrypoint_override=str(e))
    # 이름 충돌 방지: 먼저 띄운 서버를 멈춘다(내가 띄운 컨테이너)
    sh("docker", "stop", f"bs-{st.tag}", check=False)
    sh("docker", "start", c, check=False)
    wait_up(st, c)
    r = restic(st, "ops-feedback", "snapshots", repo_area="survey-service")
    assert r.returncode == 0, "변이한 서버에서도 거부된다면 시험이 private-repos 를 잡지 못한다: " + r.stderr[-200:]


@pytest.mark.parametrize("kw,why", [({"areas": False}, "영역 자격 없음"), ({"tls": False}, "TLS 없음")])
def test_refuses_to_start_insecure(st, kw, why):
    args = [*HARD, "-v", f"{st.vol}:/data"]
    if kw.get("areas", True): args += ["-v", f"{st.d}/areas:/run/secrets/areas:ro"]
    if kw.get("tls", True): args += ["-v", f"{st.d}/tlsdir:/run/tls:ro"]
    r = sh("docker", "run", "--rm", *args, IMAGE, check=False)
    assert r.returncode == 2, why + " " + r.stderr[-200:]


def test_healthcheck_is_healthy_and_turns_unhealthy_when_paused(st):
    # 이미지 HEALTHCHECK(저장소 포트가 TCP 를 받는다). 변이: 멈추면(pause) unhealthy
    c = serve(st, "hc")
    def status(): return sh("docker", "inspect", "-f", "{{.State.Health.Status}}", c, check=False).stdout.strip()
    end = time.time() + 90
    while time.time() < end and status() != "healthy": time.sleep(2)
    assert status() == "healthy"
    sh("docker", "pause", c)
    end = time.time() + 90
    while time.time() < end and status() != "unhealthy": time.sleep(3)
    assert status() == "unhealthy"
    sh("docker", "unpause", c)
