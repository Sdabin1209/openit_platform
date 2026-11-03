"""영역 게이트웨이(RUNTIME R1.1·R1.8·R6.2, CONVENTIONS 13절) 단독 시험: 생성기 + 실제 Envoy 이미지. Docker 필요.
 (1) 들어오는 쪽: 서비스 이름 인증서로 TLS 를 끝내고 영역 안 컴포넌트로 넘긴다 (2) 나가는 쪽: Exposure.egress 에 선언한 상대만 CONNECT 터널(TLS 끝까지 유지),
 선언 밖은 403 + BoundaryError(PERMISSION_DENIED, details.reason=EGRESS_DENIED) (3) 변이: egress 에서 상대를 빼면 같은 호출이 403 이 된다."""
import json, pathlib, subprocess, sys, tempfile, time, uuid
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
GEN = ROOT / "scripts/gen-area-gateway-config.py"
IMAGE = "platform-area-gateway:test"
CURL = "curlimages/curl:8.10.1"


def sh(*a, check=True, timeout=60):
    return subprocess.run(a, capture_output=True, text=True, timeout=timeout, check=check)


def have_docker():
    return sh("docker", "version", check=False).returncode == 0


pytestmark = pytest.mark.skipif(not have_docker(), reason="Docker 가 필요하다")


@pytest.fixture(scope="module")
def stack():
    tag = uuid.uuid4().hex[:8]; net = f"pgw-{tag}"; d = pathlib.Path(tempfile.mkdtemp(prefix="pgw-"))
    sh("docker", "network", "create", net)
    names = []
    def run(name, *args):
        names.append(name); sh("docker", "run", "-d", "--name", name, "--network", net, *args)
    try:
        subprocess.run(["bash", str(ROOT / "scripts/build-image.sh"), "/dev/stdin"], input=json.dumps(
            {"source_dir": str(ROOT), "revision": "test", "versions": {"boundary": "v" + sh(str(ROOT / ".venv/bin/python"), "-c", "import importlib.metadata as m;print(m.version('boundary-contracts'))").stdout.strip()}, "image_tag": IMAGE}),
            text=True, capture_output=True, check=False)
        # 인증서: 이 영역 게이트웨이(서비스 이름 survey-service)와 허용 상대(svc-x), 허용 밖 상대(svc-y)
        for cn in ("survey-service", "svc-x", "svc-y"):
            sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(d / f"{cn}.key"), "-out", str(d / f"{cn}.crt"), "-subj", f"/CN={cn}", "-addext", f"subjectAltName=DNS:{cn}", "-days", "2")
        (d / "certs").mkdir(); (d / "certs/tls.crt").write_text((d / "survey-service.crt").read_text()); (d / "certs/tls.key").write_text((d / "survey-service.key").read_text())
        for p in list(d.glob("*")) + list((d / "certs").glob("*")):
            if p.is_file(): p.chmod(0o644)
        exposure = json.loads((ROOT.parent / "boundary-contracts/examples/Exposure.json").read_text()); exposure["egress"] = ["svc-x"]
        (d / "exposure.json").write_text(json.dumps(exposure))
        def gen(path, exp):
            r = sh(str(ROOT / ".venv/bin/python"), str(GEN), "--exposure", str(exp), "--upstream", "app:8080", "--sds-out", str(d / "sds.yaml"))
            (d / path).write_text(r.stdout)
        gen("envoy.yaml", d / "exposure.json")
        util = "python:3.12-slim"
        for nm, tls in (("svc-x", True), ("svc-y", True)):
            code = ("import http.server,ssl\nclass H(http.server.BaseHTTPRequestHandler):\n def do_GET(s): s.send_response(200); s.end_headers(); s.wfile.write(b'from-" + nm + "')\n def log_message(s,*a): pass\n"
                    "h=http.server.ThreadingHTTPServer(('0.0.0.0',443),H); c=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); c.load_cert_chain('/c.crt','/c.key'); h.socket=c.wrap_socket(h.socket,server_side=True); h.serve_forever()")
            run(f"{nm}-{tag}", "--network-alias", nm, "-v", f"{d}/{nm}.crt:/c.crt:ro", "-v", f"{d}/{nm}.key:/c.key:ro", util, "python", "-c", code)
        run(f"app-{tag}", "--network-alias", "app", util, "python", "-c",
            "import http.server\nclass H(http.server.BaseHTTPRequestHandler):\n def do_GET(s): s.send_response(200); s.send_header('X-App','1'); s.end_headers(); s.wfile.write(b'from-app')\n def log_message(s,*a): pass\nhttp.server.ThreadingHTTPServer(('0.0.0.0',8080),H).serve_forever()")
        run(f"gw-{tag}", "--network-alias", "gw", "--read-only", "--tmpfs", "/tmp", "-v", f"{d}/envoy.yaml:/etc/envoy/envoy.yaml:ro", "-v", f"{d}/sds.yaml:/etc/envoy/sds.yaml:ro", "-v", f"{d}/certs:/certs:ro", IMAGE)
        time.sleep(4)
        yield {"net": net, "d": d, "tag": tag, "run": run, "gen": gen}
    finally:
        for n in names: sh("docker", "rm", "-f", n, check=False)
        sh("docker", "network", "rm", net, check=False)


def curl(net, *args):
    return sh("docker", "run", "--rm", "--network", net, CURL, "-sk", "--max-time", "8", *args, check=False).stdout


def inns(stack, name="gw"):
    """영역 게이트웨이와 같은 네트워크 공간(영역 안 컴포넌트의 자리): 출구는 이 공간의 loopback 이다(R1.8)."""
    return f"container:{name}-{stack['tag']}"


def test_ingress_tls_terminates_and_forwards(stack):
    assert curl(stack["net"], "https://gw/") == "from-app"


def test_ingress_cert_is_the_service_name(stack):
    out = sh("docker", "run", "--rm", "--network", stack["net"], "alpine/openssl", "s_client", "-connect", "gw:443", "-servername", "survey-service", check=False, timeout=30).stdout
    assert "CN = survey-service" in out or "CN=survey-service" in out


def test_egress_allowed_peer_gets_a_tunnel_with_tls_end_to_end(stack):
    assert curl(inns(stack), "-x", "http://127.0.0.1:3128", "https://svc-x/") == "from-svc-x"


def test_egress_undeclared_peer_is_403_boundary_error(stack):
    # curl 은 CONNECT 거절을 오류로 낸다: 거절 응답(상태 줄·본문)을 소켓으로 직접 받는다
    raw = sh("docker", "run", "--rm", "--network", inns(stack), "python:3.12-slim", "python", "-c",
             "import socket;s=socket.create_connection(('127.0.0.1',3128));s.sendall(b'CONNECT svc-y:443 HTTP/1.1\\r\\nHost: svc-y:443\\r\\n\\r\\n');s.settimeout(3);d=b''.join(iter(lambda: s.recv(4096), b''));print(d.decode())").stdout
    head, _, b = raw.replace("\r\n", "\n").partition("\n\n")   # subprocess 텍스트 모드가 CRLF 를 LF 로 바꾼다
    assert head.startswith("HTTP/1.1 403")
    err = json.loads(b)
    assert err["code"] == "PERMISSION_DENIED" and err["details"] == {"reason": "EGRESS_DENIED"} and err["retryable"] is False and err["pipeline_schema_version"] == "2.0"


def test_mutation_removing_the_peer_from_egress_denies_it(stack):
    d = stack["d"]
    exposure = json.loads((d / "exposure.json").read_text()); exposure["egress"] = []
    (d / "exposure2.json").write_text(json.dumps(exposure))
    stack["gen"]("envoy2.yaml", d / "exposure2.json")
    tag = stack["tag"]
    stack["run"](f"gw2-{tag}", "--network-alias", "gw2", "--read-only", "--tmpfs", "/tmp", "-v", f"{d}/envoy2.yaml:/etc/envoy/envoy.yaml:ro", "-v", f"{d}/sds.yaml:/etc/envoy/sds.yaml:ro", "-v", f"{d}/certs:/certs:ro", IMAGE)
    time.sleep(3)
    out = sh("docker", "run", "--rm", "--network", inns(stack, "gw2"), CURL, "-sk", "--max-time", "8", "-x", "http://127.0.0.1:3128", "https://svc-x/", "-v", check=False).stderr
    assert "403" in out


def test_egress_listener_is_loopback_only_not_reachable_from_other_containers(stack):
    # 출구는 loopback 이다: 같은 네트워크 공간 밖의 다른 컨테이너는 3128 에 닿지 못한다(계약 R1.8, 클라이언트 require_egress_proxy)
    out = sh("docker", "run", "--rm", "--network", stack["net"], CURL, "-sk", "--max-time", "4", "-x", "http://gw:3128", "https://svc-x/", check=False)
    assert out.returncode != 0 and out.stdout == ""


def test_route_upstreams_split_by_longest_path_prefix(stack):
    # 영역 안 컴포넌트가 여럿일 때: 경로 접두사별 상류(가장 긴 접두사 우선), 나머지는 기본 상류. Exposure 스키마에는 경로별 상류 필드가 없어 배치가 준다
    d, tag = stack["d"], stack["tag"]
    util = "python:3.12-slim"
    stack["run"](f"app2-{tag}", "--network-alias", "app2", util, "python", "-c",
                 "import http.server\nclass H(http.server.BaseHTTPRequestHandler):\n def do_GET(s): s.send_response(200); s.end_headers(); s.wfile.write(('app2:' + s.path).encode())\n def log_message(s,*a): pass\nhttp.server.ThreadingHTTPServer(('0.0.0.0',8080),H).serve_forever()")
    r = sh(str(ROOT / ".venv/bin/python"), str(GEN), "--exposure", str(d / "exposure.json"), "--upstream", "app:8080", "--route-upstream", "/v1/other=app2:8080", "--sds-out", str(d / "sds.yaml"))
    (d / "envoy3.yaml").write_text(r.stdout)
    stack["run"](f"gw3-{tag}", "--network-alias", "gw3", "--read-only", "--tmpfs", "/tmp", "-v", f"{d}/envoy3.yaml:/etc/envoy/envoy.yaml:ro", "-v", f"{d}/sds.yaml:/etc/envoy/sds.yaml:ro", "-v", f"{d}/certs:/certs:ro", IMAGE)
    time.sleep(3)
    assert curl(stack["net"], "https://gw3/v1/other/x") == "app2:/v1/other/x"
    assert curl(stack["net"], "https://gw3/v1/sessions") == "from-app"
