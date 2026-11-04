"""인증서 발급(step-ca 이미지, ADR 0012) 시험. deploy 의 test-cert-renewal.sh(R4.4 시절)를 platform 이미지로 옮겼다: 같은 시나리오를 이미지의 부명령(serve·root·token·cert)으로 돈다.
 (1) 초기화·발급: 서비스 이름 SAN, 루트로 검증 (2) 갱신: 수명이 줄면 serial 이 바뀐다 (3) R3.11: 인증기관이 멈춰도 발급된 인증서는 유효하고 인증서 컨테이너는 살아 있다, 인증기관이 돌아오면 다시 갱신
 (4) R4.6: 인증서가 만료된 뒤 컨테이너를 다시 시작하면(새 토큰) 사람 손 없이 새 인증서를 받는다 (5) 변이: 갱신 데몬을 빼면 (2) 의 판정이 실패한다.
수명은 시험에서만 줄인다: 시험이 CA 상태 볼륨의 ca.json 에 minTLSCertDuration 을 낮춘다(제품 이미지에는 시험용 문이 없다; 발급 수명·갱신 시점은 제품 환경 변수 STEP_CERT_NOT_AFTER·STEP_RENEW_EXPIRES_IN). Docker 필요."""
import json, time, pytest
from ops_common import ROOT, Stack, build, have_docker, sh

pytestmark = pytest.mark.skipif(not have_docker(), reason="Docker 가 필요하다")
IMAGE = "platform-x:step-ca"
HARD = ["--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp:exec"]
NAME = "survey-service"


class W:
    def __init__(self):
        self.s = Stack("psc")
        s = self.s
        build("step-ca", IMAGE)
        (s.d / "pw").write_text("pw-step-ca-test-" + s.tag); (s.d / "pw").chmod(0o644)
        self.ca, self.root, self.tok, self.certs = (s.volume(v) for v in ("ca", "root", "tok", "certs"))
        for v in (self.ca, self.root, self.tok, self.certs):   # 새 볼륨은 root 소유: step 사용자(1000)가 쓰게 소유자만 바꾼다
            sh("docker", "run", "--rm", "-v", f"{v}:/v", "--user", "0", "--entrypoint", "chown", IMAGE, "1000:1000", "/v")
        self.c = s.run("ca", "--network-alias", "step-ca", *HARD, "-v", f"{self.ca}:/home/step", "-v", f"{s.d}/pw:/run/secrets/step-ca-password:ro", IMAGE)
        self.wait_healthy(self.c)
        # 시험 전용: 최소 수명을 낮춘다(상태 볼륨의 설정 편집, 이미지·제품 구성은 그대로)
        sh("docker", "stop", self.c)
        self.patch_claims()
        sh("docker", "start", self.c); self.wait_healthy(self.c)
        sh("docker", "run", "--rm", *HARD[:5], "-v", f"{self.ca}:/home/step:ro", "-v", f"{self.root}:/out", "-e", "STEP_ROLE=root", IMAGE)

    def patch_claims(self):
        out = sh("docker", "run", "--rm", "-v", f"{self.ca}:/home/step", "--entrypoint", "cat", IMAGE, "/home/step/config/ca.json").stdout
        j = json.loads(out)
        j["authority"]["claims"] = {"minTLSCertDuration": "20s", "maxTLSCertDuration": "24h", "defaultTLSCertDuration": "24h"}
        (self.s.d / "ca.json").write_text(json.dumps(j)); (self.s.d / "ca.json").chmod(0o644)
        sh("docker", "run", "--rm", "-v", f"{self.ca}:/home/step", "-v", f"{self.s.d}/ca.json:/in.json:ro", "--entrypoint", "sh", IMAGE, "-c", "cat /in.json > /home/step/config/ca.json")

    def wait_healthy(self, c, t=90):
        for _ in range(t):
            if sh("docker", "inspect", "-f", "{{.State.Health.Status}}", c, check=False).stdout.strip() == "healthy": return
            time.sleep(1)
        raise AssertionError("CA 가 healthy 가 되지 않았다:\n" + self.s.logs(c)[-1500:])

    def token(self):
        sh("docker", "run", "--rm", "--network", self.s.net, *HARD[:5], "--tmpfs", "/tmp", "-v", f"{self.tok}:/tokens", "-v", f"{self.root}:/etc/openit/pki:ro",
           "-v", f"{self.s.d}/pw:/run/secrets/step-ca-password:ro", "-e", "STEP_ROLE=token", "-e", f"STEP_TOKEN_NAMES={NAME} other-name", IMAGE)

    def cert(self, name, env=(), image=IMAGE):
        e = ["-e", "STEP_ROLE=cert", "-e", f"STEP_CERT_NAME={NAME}"]   # 역할은 계약 Env 로 고른다(부명령 없음)
        for k in env: e += ["-e", k]
        return self.s.run(name, *HARD[:5], "--tmpfs", "/tmp", *e, "-v", f"{self.certs}:/certs", "-v", f"{self.root}:/etc/openit/pki:ro", "-v", f"{self.tok}:/tokens:ro", image)

    def inspect(self, field):
        r = sh("docker", "run", "--rm", "-v", f"{self.certs}:/certs:ro", "--entrypoint", "step", IMAGE, "certificate", "inspect", "/certs/tls.crt", "--format", "json", check=False)
        if r.returncode: return None
        j = json.loads(r.stdout)
        return {"serial": j["serial_number"], "sans": j.get("names"), "na": j["validity"]["end"]}[field]

    def keystat(self):
        k = sh("docker", "run", "--rm", "-v", f"{self.certs}:/certs:ro", "--entrypoint", "stat", IMAGE, "-c", "%a %g", "/certs/tls.key", check=False).stdout.split()
        c = sh("docker", "run", "--rm", "-v", f"{self.certs}:/certs:ro", "--entrypoint", "stat", IMAGE, "-c", "%a", "/certs/tls.crt", check=False).stdout.split()
        return (k[0], k[1], c[0]) if len(k) == 2 and c else None

    def verifies(self):
        return sh("docker", "run", "--rm", "-v", f"{self.certs}:/certs:ro", "-v", f"{self.root}:/pki:ro", "--entrypoint", "step", IMAGE, "certificate", "verify", "/certs/tls.crt", "--roots", "/pki/root_ca.crt", check=False).returncode == 0

    def wait(self, cond, t, what):
        for _ in range(t):
            if cond(): return
            time.sleep(2)
        raise AssertionError("기다린 조건이 되지 않았다: " + what)


ENV = ["STEP_CERT_NOT_AFTER=40s", "STEP_RENEW_EXPIRES_IN=30s"]


@pytest.fixture(scope="module")
def w():
    x = W()
    try:
        yield x
    finally:
        x.s.close()


def test_hardening(w):
    img = json.loads(sh("docker", "image", "inspect", IMAGE).stdout)[0]
    assert img["Config"]["User"] == "step" and img["Config"]["Labels"]["io.openit.service"] == "step-ca"
    assert sh("docker", "exec", w.c, "id", "-u").stdout.strip() == "1000"
    assert sh("docker", "inspect", "-f", "{{.HostConfig.ReadonlyRootfs}}", w.c).stdout.strip() == "true"
    assert "pw-step-ca-test" not in w.s.logs(w.c)   # 비밀번호가 로그에 없다


def test_issue_renew_ca_down_and_reissue_after_expiry(w):
    w.token()
    cert = w.cert("cert", ENV)
    w.wait(lambda: w.inspect("serial"), 30, "첫 발급")
    assert w.verifies()
    assert NAME in w.inspect("sans")
    w.wait(lambda: w.keystat() == ("640", "10100", "644"), 10, "키 0640 그룹 10100, 인증서 0644")   # 계약 StepCaEnv.STEP_CERT_GID 기본값
    s0 = w.inspect("serial")
    # (2) 갱신: 수명 40초, 남은 30초에 갱신 -> serial 이 바뀐다
    w.wait(lambda: w.inspect("serial") != s0, 45, "갱신으로 serial 변경")
    assert w.verifies()
    w.wait(lambda: w.keystat() == ("640", "10100", "644"), 10, "갱신 뒤에도 키 0640 그룹 10100")   # 갱신 데몬이 파일을 바꾼 뒤 --exec 로 모드를 다시 맞춘다
    w.wait_healthy(cert, 60)   # 인증서 역할의 HEALTHCHECK: 만료를 포함한 검증
    # (3) R3.11: 인증기관을 멈춘다. 발급된 인증서는 유효한 동안 그대로이고 인증서 컨테이너는 죽지 않는다
    sh("docker", "stop", w.c)
    s1 = w.inspect("serial")
    assert w.verifies()
    time.sleep(8)
    assert sh("docker", "inspect", "-f", "{{.State.Running}}", f"{cert}").stdout.strip() == "true"
    # 인증기관 복귀 뒤 갱신 재개는 데몬의 재시도 간격(지터)에 달려 시간이 불확정이라 이 시험은 단언하지 않는다(우리 코드가 아니라 step 의 동작)
    sh("docker", "start", w.c); w.wait_healthy(w.c)
    # (4) R4.6: 인증서 컨테이너를 멈추고 만료를 기다린다 -> 만료된 인증서는 검증 실패
    sh("docker", "stop", cert)
    w.wait(lambda: not w.verifies(), 40, "인증서 만료")
    expired = w.inspect("serial")
    w.token()   # 배치가 재시작과 함께 새 토큰을 준다
    sh("docker", "start", cert)
    w.wait(lambda: w.verifies() and w.inspect("serial") != expired, 40, "만료 뒤 사람 손 없이 재발급")


def test_mutation_without_renew_daemon_serial_stays(w):
    """변이 1회: 갱신하지 않는 진입점에서는 serial 이 안 바뀐다 = (2) 의 판정이 갱신 루프에 기댄다."""
    src = (ROOT / "pki/image/entrypoint.sh").read_text()
    assert "step certificate needs-renewal" in src
    (w.s.d / "mut.sh").write_text(src.replace("step certificate needs-renewal", "false step certificate needs-renewal"))   # 갱신 판정을 항상 아니오로
    (w.s.d / "mut.sh").chmod(0o755)
    sh("docker", "stop", f"cert-{w.s.tag}", check=False)   # 앞 시험의 인증서 컨테이너(같은 볼륨)가 갱신하지 않게
    sh("docker", "run", "--rm", "-v", f"{w.certs}:/certs", "--user", "0", "--entrypoint", "sh", IMAGE, "-c", "rm -f /certs/tls.*")
    w.token()
    c = w.s.run("mut", *HARD[:5], "--tmpfs", "/tmp", *sum((["-e", e] for e in ENV), []), "-v", f"{w.certs}:/certs", "-v", f"{w.root}:/etc/openit/pki:ro", "-v", f"{w.tok}:/tokens:ro",
                "-v", f"{w.s.d}/mut.sh:/m.sh:ro", "--entrypoint", "/m.sh", "-e", "STEP_ROLE=cert", "-e", f"STEP_CERT_NAME={NAME}", IMAGE)
    try:
        w.wait(lambda: w.inspect("serial"), 30, "첫 발급")
    except AssertionError:
        raise AssertionError("변이 컨테이너 첫 발급 실패:\n" + w.s.logs(c)[-800:])
    s0 = w.inspect("serial")
    time.sleep(50)
    assert w.inspect("serial") == s0, "갱신하지 않는데 serial 이 바뀌었다(시험이 갱신을 잡지 못한다)"
    assert not w.verifies(), "40초 수명이 만료돼야 한다"
    for _ in range(60):   # 변이의 HEALTHCHECK: 만료된 인증서면 unhealthy
        if sh("docker", "inspect", "-f", "{{.State.Health.Status}}", c, check=False).stdout.strip() == "unhealthy": break
        time.sleep(3)
    else:
        raise AssertionError("만료된 인증서 컨테이너가 unhealthy 가 되지 않았다")


def reader(w, seconds):
    """다른 사용자(uid 10002)가 보조 그룹 10100 으로 키를 계속 읽는다(읽는 쪽 컨테이너: 공개 입구·DB 의 자리). (읽은 횟수, 실패 횟수)를 낸다."""
    script = f'f=0; n=0; end=$(( $(date +%s) + {seconds} )); while [ $(date +%s) -lt $end ]; do n=$((n+1)); head -c1 /certs/tls.key >/dev/null 2>&1 || f=$((f+1)); sleep 0.05; done; echo "$n $f"'
    r = sh("docker", "run", "--rm", "--user", "10002:10002", "--group-add", "10100", "-v", f"{w.certs}:/certs:ro", "--entrypoint", "sh", IMAGE, "-c", script, timeout=seconds + 60)
    n, f = r.stdout.split()[-2:]
    return int(n), int(f)


def fresh_cert_container(w, name, entry=None):
    sh("docker", "rm", "-f", *[f"{n}-{w.s.tag}" for n in ("cert", "mut", "certr", "mutr")], check=False)   # 같은 볼륨을 쓰는 앞 시험의 인증서 컨테이너를 치운다
    sh("docker", "run", "--rm", "-v", f"{w.certs}:/certs", "--user", "0", "--entrypoint", "sh", IMAGE, "-c", "rm -rf /certs/tls.* /certs/.tls*")
    w.token()
    if entry is None:
        return w.cert(name, ENV)
    return w.s.run(name, *HARD[:5], "--tmpfs", "/tmp", *sum((["-e", e] for e in ENV), []), "-v", f"{w.certs}:/certs", "-v", f"{w.root}:/etc/openit/pki:ro", "-v", f"{w.tok}:/tokens:ro",
                   "-v", f"{entry}:/m.sh:ro", "--entrypoint", "/m.sh", "-e", "STEP_ROLE=cert", "-e", f"STEP_CERT_NAME={NAME}", IMAGE)


def test_renewal_never_exposes_an_unreadable_key_to_readers_in_the_group(w):
    # 갱신을 여러 번 일으키는 45초 동안 다른 uid·같은 그룹 컨테이너가 키를 계속 읽어도 한 번도 실패하지 않는다(받은 결과를 임시 파일에서 맞춰 rename 으로 교체)
    fresh_cert_container(w, "certr")
    w.wait(lambda: w.inspect("serial"), 30, "첫 발급")
    s0 = w.inspect("serial")
    n, f = reader(w, 45)
    assert w.inspect("serial") != s0, "관찰 동안 갱신이 일어나지 않았다(시험이 의미가 없다)"
    assert n > 100 and f == 0, f"읽기 {n}번 중 {f}번 실패"
    assert w.keystat() == ("640", "10100", "644")


def test_mutation_in_place_update_with_a_later_mode_fix_makes_readers_fail(w):
    # 변이: 갱신 뒤 키를 제자리에서 0600 으로 두었다가 나중에 0640 으로 되돌리는 방식(옛 --exec 후처리)이면 읽는 쪽이 실패한다 = 위 시험이 그 결함을 잡는다
    src = (ROOT / "pki/image/entrypoint.sh").read_text()
    old = 'publish "$D/.tls.crt.new" ""; fi'
    assert old in src
    (w.s.d / "mut2.sh").write_text(src.replace(old, 'publish "$D/.tls.crt.new" ""; chmod 0600 "$D/tls.key"; sleep 2; chmod 0640 "$D/tls.key"; fi'))
    (w.s.d / "mut2.sh").chmod(0o755)
    fresh_cert_container(w, "mutr", entry=str(w.s.d / "mut2.sh"))
    w.wait(lambda: w.inspect("serial"), 30, "첫 발급")
    n, f = reader(w, 45)
    assert f > 0, f"변이인데 읽기 {n}번이 모두 성공했다(시험이 결함을 잡지 못한다)"
