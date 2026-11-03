"""영역 게이트웨이(RUNTIME R1.1·R1.8·R6.2·R3.5, CONVENTIONS 13절) 단독 시험: 실제 이미지(진입점이 마운트된 Exposure 선언에서 설정을 만든다). Docker 필요.
 (1) 들어오는 쪽: 서비스 이름 인증서로 TLS 를 끝내고 영역 안 컴포넌트로 넘긴다 (2) 나가는 쪽: Exposure.egress 에 선언한 상대만 CONNECT 터널(TLS 끝까지 유지),
 선언 밖은 403 + BoundaryError(PERMISSION_DENIED, details.reason=EGRESS_DENIED) (3) 변이: egress 에서 상대를 빼면 같은 호출이 403 이 된다."""
import json, pathlib, subprocess, sys, tempfile, time, uuid
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGE = "platform-area-gateway:test"
CURL = "curlimages/curl:8.10.1"


def sh(*a, check=True, timeout=60):
    return subprocess.run(a, capture_output=True, text=True, timeout=timeout, check=check)


def have_docker():
    return sh("docker", "version", check=False).returncode == 0


pytestmark = pytest.mark.skipif(not have_docker(), reason="Docker 가 필요하다")


def start_gw(stack, name, exposure, alias=None, upstream="app:8080"):
    """진입점 계약: /etc/openit/exposure.json + /certs + 환경 변수 AREA_GATEWAY_UPSTREAM. 설정은 이미지가 만든다."""
    d, tag = stack["d"], stack["tag"]
    (d / f"{name}.json").write_text(json.dumps(exposure))
    stack["run"](f"{name}-{tag}", "--network-alias", alias or name, "--read-only", "--tmpfs", "/tmp", "-e", f"AREA_GATEWAY_UPSTREAM={upstream}",
                 "-v", f"{d}/{name}.json:/etc/openit/exposure.json:ro", "-v", f"{d}/certs:/certs:ro", IMAGE)
    time.sleep(4)


@pytest.fixture(scope="module")
def stack():
    tag = uuid.uuid4().hex[:8]; net = f"pgw-{tag}"; d = pathlib.Path(tempfile.mkdtemp(prefix="pgw-"))
    sh("docker", "network", "create", net)
    names = []
    def run(name, *args):
        names.append(name); sh("docker", "run", "-d", "--name", name, "--network", net, *args)
    try:
        req = d / "build-request.json"   # build-image.sh 는 요청 JSON 파일 경로를 받는다
        req.write_text(json.dumps(

            {"source_dir": str(ROOT), "revision": "abcdef1", "versions": {"boundary": "v" + sh(str(ROOT / ".venv/bin/python"), "-c", "import importlib.metadata as m;print(m.version('boundary-contracts'))").stdout.strip()}, "dependency_sources": {"boundary": str(ROOT.parent / "boundary-contracts")}, "image_tag": IMAGE}))
        subprocess.run(["bash", str(ROOT / "scripts/build-image.sh"), str(req)], text=True, capture_output=True, check=True)
        # 인증서: 이 영역 게이트웨이(서비스 이름 survey-service)와 허용 상대(svc-x), 허용 밖 상대(svc-y)
        for cn in ("survey-service", "svc-x", "svc-y"):
            sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(d / f"{cn}.key"), "-out", str(d / f"{cn}.crt"), "-subj", f"/CN={cn}", "-addext", f"subjectAltName=DNS:{cn}", "-days", "2")
        (d / "certs").mkdir(); (d / "certs/tls.crt").write_text((d / "survey-service.crt").read_text()); (d / "certs/tls.key").write_text((d / "survey-service.key").read_text())
        for p in list(d.glob("*")) + list((d / "certs").glob("*")):
            if p.is_file(): p.chmod(0o644)
        exposure = json.loads((ROOT.parent / "boundary-contracts/examples/Exposure.json").read_text()); exposure["egress"] = ["svc-x"]
        (d / "exposure.json").write_text(json.dumps(exposure))
        util = "python:3.12-slim"
        for nm, tls in (("svc-x", True), ("svc-y", True)):
            code = ("import http.server,ssl\nclass H(http.server.BaseHTTPRequestHandler):\n def do_GET(s): s.send_response(200); s.end_headers(); s.wfile.write(b'from-" + nm + "')\n def log_message(s,*a): pass\n"
                    "h=http.server.ThreadingHTTPServer(('0.0.0.0',443),H); c=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); c.load_cert_chain('/c.crt','/c.key'); h.socket=c.wrap_socket(h.socket,server_side=True); h.serve_forever()")
            run(f"{nm}-{tag}", "--network-alias", nm, "-v", f"{d}/{nm}.crt:/c.crt:ro", "-v", f"{d}/{nm}.key:/c.key:ro", util, "python", "-c", code)
        run(f"app-{tag}", "--network-alias", "app", util, "python", "-c",
            "import http.server\nclass H(http.server.BaseHTTPRequestHandler):\n def do_GET(s): s.send_response(200); s.send_header('X-App','1'); s.end_headers(); s.wfile.write(b'from-app')\n def log_message(s,*a): pass\nhttp.server.ThreadingHTTPServer(('0.0.0.0',8080),H).serve_forever()")
        st = {"net": net, "d": d, "tag": tag, "run": run}
        start_gw(st, "gw", exposure)
        yield st
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
    exposure = json.loads((stack["d"] / "exposure.json").read_text()); exposure["egress"] = []
    start_gw(stack, "gw2", exposure)
    out = sh("docker", "run", "--rm", "--network", inns(stack, "gw2"), CURL, "-sk", "--max-time", "8", "-x", "http://127.0.0.1:3128", "https://svc-x/", "-v", check=False).stderr
    assert "403" in out


def test_egress_listener_is_loopback_only_not_reachable_from_other_containers(stack):
    # 출구는 loopback 이다: 같은 네트워크 공간 밖의 다른 컨테이너는 3128 에 닿지 못한다(계약 R1.8, 클라이언트 require_egress_proxy)
    out = sh("docker", "run", "--rm", "--network", stack["net"], CURL, "-sk", "--max-time", "4", "-x", "http://gw:3128", "https://svc-x/", check=False)
    assert out.returncode != 0 and out.stdout == ""


def test_body_limit_413_boundary_error_per_route_and_default_8mib(stack):
    # R3.5(3.4.7): 경로의 max_body_bytes(없으면 8MiB)를 Content-Length 가 넘으면 앱에 닿기 전 413 + INVALID_RECORD
    exposure = json.loads((stack["d"] / "exposure.json").read_text())
    exposure["routes"] = [{"paths": ["/v1/small"], "methods": ["POST"], "auth": {"kind": "none"}, "max_body_bytes": 100},
                          {"paths": ["/v1/big/*"], "auth": {"kind": "none"}, "max_body_bytes": 1000000}]
    start_gw(stack, "gwlim", exposure)
    def post(path, n):
        # 본문은 표준 입력으로 보낸다(명령줄 길이 한도)
        return subprocess.run(["docker", "run", "--rm", "-i", "--network", stack["net"], CURL, "-sk", "--max-time", "20", "-X", "POST", "-H", "Content-Type: application/octet-stream", "--data-binary", "@-", "-w", "\n%{http_code}", f"https://gwlim{path}"],
                              input="x" * n, capture_output=True, text=True, check=False, timeout=60).stdout
    body, _, code = post("/v1/small", 101).rpartition("\n")
    assert code == "413"
    err = json.loads(body)
    assert err["code"] == "INVALID_RECORD" and err["details"] == {"max_body_bytes": 100} and err["retryable"] is False
    assert post("/v1/small", 100).rpartition("\n")[2] != "413"   # 한도 안: 앱으로 간다(시험 앱이 POST 를 몰라 501 일 수 있다)
    assert post("/v1/big/x", 500000).rpartition("\n")[2] != "413"                                                # 경로의 큰 상한 안
    assert post("/v1/other", 8 * 1024 * 1024 + 1).rpartition("\n")[2] == "413"                                 # 선언 없는 경로는 8MiB


def test_upstream_port_routes_to_a_loopback_component(stack):
    # upstream_port(3.4.7): 영역 안 컴포넌트가 여럿일 때 경로별 상류 = 같은 네트워크 공간의 loopback 포트(여기서는 게이트웨이 컨테이너의 공간에 둔 두 번째 컴포넌트)
    tag = stack["tag"]
    exposure = json.loads((stack["d"] / "exposure.json").read_text())
    exposure["routes"] = [{"paths": ["/v1/second/*"], "auth": {"kind": "none"}, "upstream_port": 9090}]
    start_gw(stack, "gwport", exposure)
    sh("docker", "run", "-d", "--name", f"comp2-{tag}", "--network", f"container:gwport-{tag}", "python:3.12-slim", "python", "-c",
       "import http.server\nclass H(http.server.BaseHTTPRequestHandler):\n def do_GET(s): s.send_response(200); s.end_headers(); s.wfile.write(b'second')\n def log_message(s,*a): pass\nhttp.server.ThreadingHTTPServer(('127.0.0.1',9090),H).serve_forever()")
    time.sleep(3)
    try:
        assert curl(stack["net"], "https://gwport/v1/second/x") == "second"
        assert curl(stack["net"], "https://gwport/v1/first") == "from-app"
    finally:
        sh("docker", "rm", "-f", f"comp2-{tag}", check=False)


def test_invalid_exposure_declaration_does_not_start(stack):
    # 선언이 계약을 어기면 시작하지 않는다(종료 코드 != 0, 사유가 표준 오류에)
    d = stack["d"]; (d / "bad.json").write_text(json.dumps({"service": "x", "routes": [], "egress": ["BAD NAME"]}))
    r = sh("docker", "run", "--rm", "--read-only", "--tmpfs", "/tmp", "-v", f"{d}/bad.json:/etc/openit/exposure.json:ro", "-v", f"{d}/certs:/certs:ro", IMAGE, check=False, timeout=60)
    assert r.returncode != 0 and "계약" in r.stderr


def test_missing_exposure_declaration_does_not_start(stack):
    r = sh("docker", "run", "--rm", "--read-only", "--tmpfs", "/tmp", IMAGE, check=False, timeout=60)
    assert r.returncode != 0


def test_egress_only_when_certs_not_mounted_opens_no_ingress_listener(stack):
    # compose 밖(학습 서버)의 게이트웨이는 나가는 쪽만 쓴다: /certs 마운트가 없으면 들어오는 listener 를 열지 않는다(인증서 없는 입구 금지). 결정은 입력(마운트)에서 나온다
    exposure = json.loads((stack["d"] / "exposure.json").read_text())
    (stack["d"] / "eo.json").write_text(json.dumps(exposure))
    stack["run"](f"eo-{stack['tag']}", "--network-alias", "eo", "--read-only", "--tmpfs", "/tmp", "-e", "AREA_GATEWAY_UPSTREAM=app:8080",
                 "-v", f"{stack['d']}/eo.json:/etc/openit/exposure.json:ro", IMAGE)
    time.sleep(4)
    # 들어오는 쪽 없음: 443 연결이 거절된다(listener 가 없다)
    r = sh("docker", "run", "--rm", "--network", stack["net"], CURL, "-sk", "--max-time", "4", "https://eo/", check=False)
    assert r.returncode != 0 and r.stdout == ""
    # 나가는 쪽은 그대로 동작한다
    assert curl(inns(stack, "eo"), "-x", "http://127.0.0.1:3128", "https://svc-x/") == "from-svc-x"
    # 변이: 같은 선언에 /certs 를 마운트하면 같은 호출이 응답한다(위 단언이 마운트 유무 때문임을 보인다)
    assert curl(stack["net"], "https://gw/") == "from-app"
