"""시험용 가짜 영역 서비스(TLS, 서비스 이름 인증서). MODE: ok | slow(/metrics 13초 지연) | m500 | static(/metrics 없음) | empty(/readyz 빈 200) | gate(/readyz 503 + judging_loop). 요청 경로를 표준 출력에 낸다."""
import http.server, json, os, ssl, sys, time
MODE = os.environ["MODE"]

class H(http.server.BaseHTTPRequestHandler):
    def send(self, code, body=b"", ctype="text/plain"):
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        print("REQ", self.path, flush=True)
        if self.path == "/metrics" and MODE not in ("static", "empty", "gate"):
            if MODE == "slow": time.sleep(13)
            if MODE == "m500": return self.send(500, b"boom")
            return self.send(200, b"# TYPE fake_up gauge\nfake_up 1\n", "text/plain; version=0.0.4")
        if self.path == "/readyz":
            if MODE == "empty": return self.send(200, b"")
            if MODE == "gate": return self.send(503, json.dumps({"status": "degraded", "judging_loop": {"consecutive_failures": 3, "last_run_at": 1700000000, "upstream_auth_failed": False}}).encode(), "application/json")
            return self.send(200, b'{"status": "ok"}', "application/json")
        self.send(404, b"no")
    def log_message(self, *a): pass

h = http.server.ThreadingHTTPServer(("0.0.0.0", 443), H)
c = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); c.load_cert_chain("/c.crt", "/c.key")
h.socket = c.wrap_socket(h.socket, server_side=True)
h.serve_forever()
