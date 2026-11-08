"""영역 게이트웨이(RUNTIME R1.1·R1.8·R6.2·R3.5, CONVENTIONS 13절) 단독 시험: 실제 이미지(진입점이 마운트된 Exposure 선언에서 설정을 만든다). Docker 필요.
 (1) 들어오는 쪽: 서비스 이름 인증서로 TLS 를 끝내고 영역 안 컴포넌트로 넘긴다 (2) 나가는 쪽: Exposure.egress 에 선언한 상대만 CONNECT 터널(TLS 끝까지 유지),
 선언 밖은 403 + BoundaryError(PERMISSION_DENIED, details.reason=EGRESS_DENIED) (3) 변이: egress 에서 상대를 빼면 같은 호출이 403 이 된다."""
import json, pathlib, subprocess, sys, tempfile, time, uuid
import pytest
from ops_common import lock   # 이미지 digest 의 출처: locks/images.lock

from boundary_contracts import PIPELINE_SCHEMA_VERSION as PSV   # 계약 패키지의 현행 값과 같아야 한다(박지 않는다)
ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGE = "platform-area-gateway:test-" + uuid.uuid4().hex[:8]   # D22: 이미지 태그에 리포 이름 + 임의 접미사(다른 세션과 충돌 방지)
CURL = "curlimages/curl:8.10.1"


def sh(*a, check=True, timeout=60):
    return subprocess.run(a, capture_output=True, text=True, timeout=timeout, check=check)


def have_docker():
    return sh("docker", "version", check=False).returncode == 0


pytestmark = pytest.mark.skipif(not have_docker(), reason="Docker 가 필요하다")


def start_gw(stack, name, exposure, alias=None, upstream="127.0.0.1:8080"):
    """진입점 계약: /etc/openit/exposure.json + /certs + 환경 변수 AREA_GATEWAY_UPSTREAM. 설정은 이미지가 만든다."""
    d, tag = stack["d"], stack["tag"]
    (d / f"{name}.json").write_text(json.dumps(exposure))
    stack["run"](f"{name}-{tag}", "--network-alias", alias or name, "--read-only", "--tmpfs", "/tmp", "-e", f"AREA_GATEWAY_UPSTREAM={upstream}",
                 "-v", f"{d}/{name}.json:/etc/openit/exposure.json:ro", "-v", f"{d}/certs:/certs:ro", IMAGE)
    # 평문 상류는 같은 pod의 루프백뿐이다. 각 게이트웨이의 앱도 그 네트워크 공간에 둔다.
    if upstream == "127.0.0.1:8080":
        app = f"{name}-app-{tag}"
        stack["run"](app, lock("UTIL_IMAGE"), "python", "-c", stack["app_code"], network=f"container:{name}-{tag}")
        until = time.monotonic() + 30
        while time.monotonic() < until:
            if sh("docker", "exec", app, "python", "-c", "import socket;socket.create_connection(('127.0.0.1',8080),timeout=1).close()", check=False).returncode == 0:
                break
            time.sleep(0.1)
        else:
            pytest.fail("pod application did not become ready")
    # A running process may still be warming DNS/listeners. Wait for the image's
    # declared health probe rather than assuming a fixed sleep means readiness.
    deadline = time.monotonic() + 45  # Standalone fixture startup budget, not a runtime contract timeout.
    while time.monotonic() < deadline:
        state = sh("docker", "inspect", "--format", "{{.State.Running}}", f"{name}-{tag}").stdout.strip()
        if state != "true":
            break
        if sh("docker", "exec", f"{name}-{tag}", "/usr/local/bin/area-gateway-entrypoint.sh", "health", check=False, timeout=8).returncode == 0:
            return
        time.sleep(0.2)
    pytest.fail("gateway did not become ready:\n" + sh("docker", "logs", f"{name}-{tag}", check=False).stderr[-6000:])


@pytest.fixture(scope="module")
def stack():
    tag = uuid.uuid4().hex[:8]; net = f"pgw-{tag}"; d = pathlib.Path(tempfile.mkdtemp(prefix="pgw-"))
    sh("docker", "network", "create", net)
    names = []
    def run(name, *args, network=None):
        names.append(name); sh("docker", "run", "-d", "--name", name, "--network", network or net, *args)
    try:
        req = d / "build-request.json"   # build-image.sh 는 요청 JSON 파일 경로를 받는다
        req.write_text(json.dumps(

            {"source_dir": str(ROOT), "revision": "abcdef1", "versions": {"boundary": "v" + sh(str(ROOT / ".venv/bin/python"), "-c", "import importlib.metadata as m;print(m.version('boundary-contracts'))").stdout.strip()}, "dependency_sources": {"boundary": sh("bash", str(ROOT / "scripts/fetch-boundary-src.sh"), str(d / "boundary-src")).stdout.strip()}, "image_tag": IMAGE}))
        b = subprocess.run(["bash", str(ROOT / "scripts/build-image.sh"), str(req)], text=True, capture_output=True, check=False)
        assert b.returncode == 0, "이미지를 만들지 못했다:\n" + b.stderr[-1500:]
        # 인증서: 이 영역 게이트웨이(서비스 이름 survey-service)와 허용 상대(svc-x), 허용 밖 상대(svc-y)
        for cn in ("survey-service", "svc-x", "svc-y"):
            sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(d / f"{cn}.key"), "-out", str(d / f"{cn}.crt"), "-subj", f"/CN={cn}", "-addext", f"subjectAltName=DNS:{cn}", "-days", "2")
        (d / "certs").mkdir(); (d / "certs/tls.crt").write_text((d / "survey-service.crt").read_text()); (d / "certs/tls.key").write_text((d / "survey-service.key").read_text())
        for p in list(d.glob("*")) + list((d / "certs").glob("*")):
            if p.is_file(): p.chmod(0o644)
        exposure = json.loads((d / "boundary-src/examples/Exposure.json").read_text()); exposure["egress"] = ["svc-x"]
        (d / "exposure.json").write_text(json.dumps(exposure))
        util = lock("UTIL_IMAGE")
        for nm, tls in (("svc-x", True), ("svc-y", True)):
            code = ("import http.server,ssl\nclass H(http.server.BaseHTTPRequestHandler):\n def do_GET(s): s.send_response(200); s.end_headers(); s.wfile.write(b'from-" + nm + "')\n def log_message(s,*a): pass\n"
                    "h=http.server.ThreadingHTTPServer(('0.0.0.0',443),H); c=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); c.load_cert_chain('/c.crt','/c.key'); h.socket=c.wrap_socket(h.socket,server_side=True); h.serve_forever()")
            run(f"{nm}-{tag}", "--network-alias", nm, "-v", f"{d}/{nm}.crt:/c.crt:ro", "-v", f"{d}/{nm}.key:/c.key:ro", util, "python", "-c", code)
        app_code = "import http.server,time\nclass H(http.server.BaseHTTPRequestHandler):\n def do_GET(s):\n  if s.path.startswith('/delay-header/'):\n   time.sleep(float(s.path.rsplit('/',1)[1])); s.send_response(200); s.end_headers(); s.wfile.write(b'delayed'); return\n  if s.path.startswith('/stream/'):\n   s.send_response(200); s.send_header('Content-Length','4'); s.end_headers(); s.wfile.write(b'x'); s.wfile.flush()\n   for _ in range(3): time.sleep(float(s.path.rsplit('/',1)[1])); s.wfile.write(b'x'); s.wfile.flush()\n   return\n  if s.path=='/app-error':\n   s.send_response(503); s.send_header('Retry-After','17'); s.send_header('X-App','original'); s.end_headers(); s.wfile.write(b'app-original-body'); return\n  s.send_response(200); s.send_header('X-App','1'); s.end_headers(); s.wfile.write(b'from-app')\n def log_message(s,*a): pass\nhttp.server.ThreadingHTTPServer(('0.0.0.0',8080),H).serve_forever()"
        st = {"net": net, "d": d, "tag": tag, "run": run, "app_code": app_code}
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
    raw = sh("docker", "run", "--rm", "--network", inns(stack), lock("UTIL_IMAGE"), "python", "-c",
             "import socket;s=socket.create_connection(('127.0.0.1',3128));s.sendall(b'CONNECT svc-y:443 HTTP/1.1\\r\\nHost: svc-y:443\\r\\n\\r\\n');s.settimeout(3);d=b''.join(iter(lambda: s.recv(4096), b''));print(d.decode())").stdout
    head, _, b = raw.replace("\r\n", "\n").partition("\n\n")   # subprocess 텍스트 모드가 CRLF 를 LF 로 바꾼다
    assert head.startswith("HTTP/1.1 403")
    err = json.loads(b)
    assert err["code"] == "PERMISSION_DENIED" and err["details"] == {"reason": "EGRESS_DENIED"} and err["retryable"] is False and err["pipeline_schema_version"] == PSV


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
    sh("docker", "run", "-d", "--name", f"comp2-{tag}", "--network", f"container:gwport-{tag}", lock("UTIL_IMAGE"), "python", "-c",
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
    stack["run"](f"eo-{stack['tag']}", "--network-alias", "eo", "--read-only", "--tmpfs", "/tmp", "-e", "AREA_GATEWAY_UPSTREAM=127.0.0.1:8080",
                 "-v", f"{stack['d']}/eo.json:/etc/openit/exposure.json:ro", IMAGE)
    time.sleep(4)
    # 들어오는 쪽 없음: 443 연결이 거절된다(listener 가 없다)
    r = sh("docker", "run", "--rm", "--network", stack["net"], CURL, "-sk", "--max-time", "4", "https://eo/", check=False)
    assert r.returncode != 0 and r.stdout == ""
    # 나가는 쪽은 그대로 동작한다
    assert curl(inns(stack, "eo"), "-x", "http://127.0.0.1:3128", "https://svc-x/") == "from-svc-x"
    # 변이: 같은 선언에 /certs 를 마운트하면 같은 호출이 응답한다(위 단언이 마운트 유무 때문임을 보인다)
    assert curl(stack["net"], "https://gw/") == "from-app"


def test_healthcheck_is_healthy_and_turns_unhealthy_when_the_gateway_stops_answering(stack):
    # 이미지 HEALTHCHECK(출구·입구 listener 가 TCP 를 받는다): healthy. 변이: 프로세스를 멈추면(pause) unhealthy
    c = f"gw-{stack['tag']}"
    def status(): return sh("docker", "inspect", "-f", "{{.State.Health.Status}}", c, check=False).stdout.strip()
    end = time.time() + 90
    while time.time() < end and status() != "healthy": time.sleep(2)   # 준비 확인: 건강 확인 자체가 신호다
    assert status() == "healthy"
    sh("docker", "pause", c)
    end = time.time() + 90
    while time.time() < end and status() != "unhealthy": time.sleep(3)
    assert status() == "unhealthy"
    sh("docker", "unpause", c)


def test_public_denied_path_reaches_service_inside_area(stack):
    exposure = {"service": "dataset-store", "routes": [{"paths": ["/v1/datasets", "/v1/datasets/*"], "auth": {"kind": "denied"}}]}
    start_gw(stack, "internal-route", exposure)
    assert curl(stack["net"], "https://internal-route/v1/datasets") == "from-app"


@pytest.mark.parametrize("upstream", ["127.0.0.2:8080", "127.0.0.1:8081"])
def test_ingress_upstream_failure_has_declared_gateway_error(stack, upstream):
    exposure = {"service": "survey-service", "routes": [{"paths": ["/"], "auth": {"kind": "none"}}]}
    start_gw(stack, "unavailable-" + upstream.split(":")[0], exposure, upstream=upstream)
    gateway = "unavailable-" + upstream.split(":")[0]
    response = sh("docker", "run", "--rm", "--network", stack["net"], CURL, "-skv", "--max-time", "8", "-i", f"https://{gateway}/", check=False)
    assert response.returncode == 0, response.stderr
    raw = response.stdout
    headers, _, body = raw.replace("\r\n", "\n").partition("\n\n")
    assert " 503 " in headers, {"response": raw, "gateway_logs": sh("docker", "logs", f"{gateway}-{stack['tag']}", check=False).stderr[-8000:]}
    assert "retry-after: 5" in headers.lower()
    from boundary_contracts import validator
    normalized = dict(line.split(": ", 1) for line in headers.lower().splitlines()[1:] if ": " in line)
    validator("GatewayErrorResponse").validate({"status": 503, "headers": normalized, "body": json.loads(body)})


def test_application_503_body_and_retry_header_are_preserved(stack):
    raw = curl(stack["net"], "-i", "https://gw/app-error")
    headers, _, body = raw.replace("\r\n", "\n").partition("\n\n")
    assert " 503 " in headers
    assert body == "app-original-body"
    assert "retry-after: 17" in headers.lower()
    assert "x-app: original" in headers.lower()
    assert "x-envoy-upstream-service-time" not in headers.lower()
    assert "server:" not in headers.lower()


def curl_seconds(result):
    # 왜 curl 이 잰 시간인가: docker run 의 컨테이너 시작 시간(부하에 따라 수 초)이 게이트웨이 시간 한도 단언에 섞이면 안 된다. curl 의 write-out %{stderr} 로 요청 시간만 stderr 에 받는다
    return float(result.stderr.strip().splitlines()[-1])


def timed_request(stack, gateway, path, budget):
    result = sh("docker", "run", "--rm", "--network", stack["net"], CURL,
                "-sk", "--max-time", str(budget), "-i", "-w", "%{stderr}%{time_total}", f"https://{gateway}{path}",
                check=False, timeout=budget + 15)
    return result, curl_seconds(result)


def test_declared_header_timeout_is_enforced_without_retry(stack):
    exposure = {"service": "release-gate", "routes": [{"paths": ["/*"], "auth": {"kind": "none"},
                "timeouts_ms": {"dial": 10, "response_header": 200}}]}
    start_gw(stack, "short-header", exposure)
    result, elapsed = timed_request(stack, "short-header", "/delay-header/1", 8)
    assert result.returncode == 0, result.stderr
    headers, _, body = result.stdout.replace("\r\n", "\n").partition("\n\n")
    assert " 504 " in headers, result.stdout
    from boundary_contracts import validator
    normalized = dict(line.split(": ", 1) for line in headers.lower().splitlines()[1:] if ": " in line)
    validator("GatewayErrorResponse").validate({"status": 504, "headers": normalized, "body": json.loads(body)})
    assert 0.15 < elapsed < 3, elapsed


def test_stream_continues_past_header_budget_but_read_idle_is_enforced(stack):
    exposure = {"service": "survey-service", "routes": [{"paths": ["/*"], "auth": {"kind": "none"},
                "streaming": True, "timeouts_ms": {"dial": 10, "response_header": 100, "read": 400}}]}
    start_gw(stack, "stream-budget", exposure)
    result, _ = timed_request(stack, "stream-budget", "/stream/0.15", 8)
    assert result.returncode == 0 and result.stdout.endswith("xxxx"), result.stdout + result.stderr
    result, _ = timed_request(stack, "stream-budget", "/stream/0.8", 8)
    assert result.returncode != 0, result.stdout
    assert " 200 " in result.stdout and not result.stdout.endswith("xxxx"), result.stdout


def test_release_gate_default_wait_exceeds_old_120_second_cutoff(stack):
    # Exact production-scale regression: a healthy slow response survives the
    # old 120s cutoff and still completes before the contract's 170s server cap.
    exposure = {"service": "release-gate", "routes": [{"paths": ["/*"], "auth": {"kind": "none"}}]}
    start_gw(stack, "release-budget", exposure)
    result, elapsed = timed_request(stack, "release-budget", "/delay-header/121", 190)
    assert result.returncode == 0 and " 200 " in result.stdout and result.stdout.endswith("delayed"), result.stdout + result.stderr
    assert 120 < elapsed < 170, elapsed


def test_client_envoy_headers_cannot_override_the_declared_timeout(stack):
    exposure = {"service": "release-gate", "routes": [{"paths": ["/*"], "auth": {"kind": "none"},
                "timeouts_ms": {"dial": 10, "response_header": 200}}]}
    start_gw(stack, "header-override", exposure)
    result = sh("docker", "run", "--rm", "--network", stack["net"], CURL, "-sk", "-i", "--max-time", "8", "-w", "%{stderr}%{time_total}",
                "-H", "x-envoy-upstream-rq-timeout-ms: 999999",
                "-H", "x-envoy-upstream-rq-per-try-timeout-ms: 999999",
                "-H", "x-envoy-expected-rq-timeout-ms: 999999",
                "-H", "x-envoy-max-retries: 9", "-H", "x-envoy-retry-on: 5xx",
                "-H", "x-envoy-upstream-rq-timeout-alt-response: true",
                "https://header-override/delay-header/1", check=False)
    assert result.returncode == 0, result.stderr
    assert " 504 " in result.stdout, result.stdout
    assert curl_seconds(result) < 3
    headers, _, body = result.stdout.replace("\r\n", "\n").partition("\n\n")
    from boundary_contracts import validator
    normalized = dict(line.split(": ", 1) for line in headers.lower().splitlines()[1:] if ": " in line)
    validator("GatewayErrorResponse").validate({"status": 504, "headers": normalized, "body": json.loads(body)})


def test_read_shorter_than_header_is_rejected_on_start_with_65(stack):
    declaration = {"service": "release-gate", "routes": [{"paths": ["/*"], "auth": {"kind": "none"},
                   "timeouts_ms": {"response_header": 200, "read": 100}}]}
    path = stack["d"] / "invalid-time-chain.json"
    path.write_text(json.dumps(declaration))
    result = sh("docker", "run", "--rm", "--read-only", "--tmpfs", "/tmp",
                "-v", f"{path}:/etc/openit/exposure.json:ro", "-v", f"{stack['d']}/certs:/certs:ro", IMAGE, check=False)
    assert result.returncode == 65, result.stderr
    assert "read must be >= response_header" in result.stderr
