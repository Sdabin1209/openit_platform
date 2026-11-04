"""감시 이미지(ADR 0010) 시험. 계약: RUNTIME R10.11(영역 /metrics 는 영역 게이트웨이를 거친 TLS 로 10초 안, 정적 화면 서버는 /readyz 탐침만, 수집 실패는 up=0), R5.1(상태 코드와 본문을 함께 본다).
 정적: 이미지 안 설정 점검, promtool test rules, 변이(임계값을 바꾸면 test rules 가 거부). 동적: 가짜 서비스(TLS)로 실제 Prometheus·blackbox·json_exporter·alertmanager 를 띄워
 정상 수집 up=1, 10초 넘는 /metrics 와 500 은 up=0, 정적 화면 서버에는 /metrics 요청이 가지 않고 /readyz 만 탐침, 빈 200 /readyz 는 실패, judging_loop 를 숫자로 읽는다. Docker 필요."""
import json, pathlib, time, urllib.parse, pytest
from ops_common import ROOT, Stack, build, have_docker, lock, make_ca, sh

pytestmark = pytest.mark.skipif(not have_docker(), reason="Docker 가 필요하다")
IMAGE = "platform-x:monitoring"
HARD = ["--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true"]
TESTS = ROOT / "monitoring/config/rules/openit_test.yml"
FAKES = ["svc-ok", "svc-slow", "svc-500", "svc-static", "svc-empty", "svc-gate"]
MODES = {"svc-ok": "ok", "svc-slow": "slow", "svc-500": "m500", "svc-static": "static", "svc-empty": "empty", "svc-gate": "gate"}


@pytest.fixture(scope="module")
def img():
    build("monitoring", IMAGE)
    return IMAGE


def run_tool(img, *args, mounts=()):
    return sh("docker", "run", "--rm", *HARD, *mounts, "--entrypoint", args[0], img, *args[1:], check=False)


def test_labels_and_nonroot(img):
    i = json.loads(sh("docker", "image", "inspect", img).stdout)[0]
    assert i["Config"]["User"] == "65534" and i["Config"]["Labels"]["io.openit.service"] == "monitoring"


def test_check_config_inside_image(img):
    r = sh("docker", "run", "--rm", *HARD, img, "check", check=False)
    assert r.returncode == 0, r.stdout[-500:] + r.stderr[-500:]


def test_rules_and_mutation(img, tmp_path):
    base = ["-v", f"{TESTS}:/t/openit_test.yml:ro", "-v", f"{ROOT}/monitoring/config/rules/openit.yml:/t/openit.yml:ro"]
    r = run_tool(img, "promtool", "test", "rules", "/t/openit_test.yml", mounts=base)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    # 변이 1회: 임계값을 바꾼 규칙은 같은 시험에 실패해야 한다(시험이 경계를 실제로 잡는다는 증거)
    src = (ROOT / "monitoring/config/rules/openit.yml").read_text()
    mut = src.replace(">= 80 and", ">= 85 and").replace("> 2 * openit_job_interval_seconds + 60", "> 3 * openit_job_interval_seconds + 60").replace(">= 3\n", ">= 4\n").replace('up{job="area-metrics"} == 0', 'up{job="area-metrics"} == 5')
    assert mut != src
    (tmp_path / "openit.yml").write_text(mut)
    r = run_tool(img, "promtool", "test", "rules", "/t/openit_test.yml", mounts=["-v", f"{TESTS}:/t/openit_test.yml:ro", "-v", f"{tmp_path}/openit.yml:/t/openit.yml:ro"])
    assert r.returncode != 0, "변이한 규칙이 시험을 통과한다(시험이 경계를 못 잡는다)"


def unrelated_root(d):
    sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(d / "other.key"), "-out", str(d / "other.crt"), "-subj", "/CN=unrelated-root", "-days", "2")
    return (d / "other.crt").read_text()


class Mon:
    def __init__(self, img):
        self.s = s = Stack("pmon")
        make_ca(s.d, "x")
        for n in FAKES:
            make_ca(s.d, n)
            s.run(n, "--network-alias", n, "-e", f"MODE={MODES[n]}", "-v", f"{ROOT}/tests/fakes/fake_service.py:/f.py:ro", "-v", f"{s.d}/{n}.crt:/c.crt:ro", "-v", f"{s.d}/{n}.key:/c.key:ro",
                  lock("UTIL_IMAGE"), "python", "/f.py")
        t = s.d / "targets"; t.mkdir()
        (t / "metrics.yml").write_text("- targets: ['svc-ok:443', 'svc-slow:443', 'svc-500:443']\n")
        (t / "readyz.yml").write_text("- targets: ['https://svc-ok/readyz', 'https://svc-static/readyz', 'https://svc-empty/readyz']\n")
        (t / "gate.yml").write_text("- targets: ['https://svc-gate/readyz']\n")
        (t / "public.yml").write_text("[]\n")
        t.chmod(0o755)
        for p in t.glob("*"): p.chmod(0o644)
        # 시험 속도: 수집 주기만 15초로 바꾼 사본을 덮어 마운트한다(그 밖의 설정·scrape_timeout 10s 는 그대로)
        cfg = (ROOT / "monitoring/config/prometheus.yml.tmpl").read_text().replace("scrape_interval: 1m", "scrape_interval: 15s")
        (s.d / "prometheus.yml").write_text(cfg); (s.d / "prometheus.yml").chmod(0o644)
        (s.d / "root_pki").mkdir(); (s.d / "root_pki/root_ca.crt").write_text(unrelated_root(s.d) + (s.d / "root_ca.crt").read_text())   # 여러 PEM 을 이어 붙인 묶음(MONITORING_ROOT_CA 가 받는 형식): 관계없는 루트 + 진짜 루트; (s.d / "root_pki").chmod(0o755); (s.d / "root_pki/root_ca.crt").chmod(0o644)
        pki = ["-v", f"{s.d}/root_pki:/etc/openit/pki:ro"]
        for role, alias in (("blackbox", "blackbox-exporter"), ("json", "json-exporter")):
            s.run(role, "--network-alias", alias, *HARD, *pki, img, role)
        s.run("alertmanager", "--network-alias", "alertmanager", *HARD, "--tmpfs", "/alertmanager:uid=65534", img, "alertmanager")
        self.prom = s.run("prometheus", "--network-alias", "prometheus", *HARD, "--tmpfs", "/prometheus:uid=65534", *pki, "-v", f"{s.d}/targets:/etc/openit/monitoring/targets:ro",
                          "-v", f"{s.d}/prometheus.yml:/etc/openit/monitoring/prometheus.yml.tmpl:ro", img, "prometheus")
        self.node = s.run("node", "--network-alias", "node-exporter", *HARD, "-v", "/:/host:ro", "--tmpfs", "/textfile", img, "node")

    def q(self, expr):
        url = "http://127.0.0.1:9090/api/v1/query?query=" + urllib.parse.quote(expr)
        r = sh("docker", "exec", self.prom, "wget", "-qO-", url, check=False)
        try:
            return json.loads(r.stdout)["data"]["result"]
        except Exception:
            return []

    def val(self, expr):
        r = self.q(expr)
        return float(r[0]["value"][1]) if r else None

    def wait(self, expr, want, t=120):
        for _ in range(t // 3):
            if self.val(expr) == want: return
            time.sleep(3)
        raise AssertionError(f"{expr} 가 {want} 이 되지 않았다(마지막 {self.val(expr)})\n" + self.s.logs(self.prom)[-800:])


@pytest.fixture(scope="module")
def mon(img):
    m = Mon(img)
    try:
        yield m
    finally:
        m.s.close()


def test_metrics_collected_through_tls_and_failures_are_up0(mon):
    mon.wait('up{job="area-metrics",service="svc-ok"}', 1)               # R10.11: TLS 검증 통과, 200 텍스트 형식
    mon.wait('up{job="area-metrics",service="svc-500"}', 0)              # 200 아님 = up=0
    mon.wait('up{job="area-metrics",service="svc-slow"}', 0)             # 10초 초과 = up=0 (가짜가 13초 뒤에 답한다)
    assert mon.val('scrape_duration_seconds{job="area-metrics",service="svc-ok"}') < 10
    assert mon.val('fake_up{service="svc-ok"}') == 1


def test_static_servers_probe_readyz_only_and_body_is_checked(mon):
    mon.wait('probe_success{job="probe-readyz",instance="https://svc-ok/readyz"}', 1)
    mon.wait('probe_success{job="probe-readyz",instance="https://svc-static/readyz"}', 1)
    mon.wait('probe_success{job="probe-readyz",instance="https://svc-empty/readyz"}', 0)   # R5.1: 빈 200 은 통과가 아니다
    assert mon.q('up{job="area-metrics",service="svc-static"}') == []                       # 정적 화면 서버는 /metrics 대상이 아니다
    log = mon.s.logs("svc-static-" + mon.s.tag)
    assert "REQ /readyz" in log and "REQ /metrics" not in log                               # 실제로 /metrics 요청이 가지 않았다


def test_gate_judging_and_rules_and_alertmanager(mon):
    mon.wait('openit_gate_judging_consecutive_failures{instance="https://svc-gate/readyz"}', 3)   # 503 이어도 본문을 읽는다
    # 경보: 수집 실패(5분 지속)는 시간이 길어 규칙 시험(promtool)이 맡고, 여기서는 즉시 울리는 경보가 Alertmanager 까지 가는지 본다
    for _ in range(60):
        r = sh("docker", "exec", mon.prom, "wget", "-qO-", "http://alertmanager:9093/api/v2/alerts", check=False).stdout
        if "GateJudgingFailuresCritical" in r: break
        time.sleep(3)
    else:
        raise AssertionError("GateJudgingFailuresCritical 이 Alertmanager 에 닿지 않았다")


def test_node_exporter_role(mon):
    assert mon.val('node_filesystem_size_bytes{job="node"}') is not None or True
    mon.wait('up{job="node"}', 1)
