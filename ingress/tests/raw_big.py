"""너무 큰 요청 줄·머리글을 소켓으로 직접 보내 상태 코드를 출력한다(curl 은 큰 값을 보내지 못한다). 사용: raw_big.py <포트> line|header   (시험 전용, 자체 서명 인증서라 검증하지 않는다)"""
import socket, ssl, sys
port, kind = int(sys.argv[1]), sys.argv[2]
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
ctx.set_alpn_protocols(["http/1.1"])
s = ctx.wrap_socket(socket.create_connection(("127.0.0.1", port), timeout=10), server_hostname="localhost")   # SNI = Host (IP 리터럴은 SNI 가 될 수 없다)
big = b"a" * 1200000
req = (b"GET /healthz?" + big + b" HTTP/1.1\r\nHost: localhost\r\n\r\n") if kind == "line" else (b"GET /healthz HTTP/1.1\r\nHost: localhost\r\nX-Big: " + big + b"\r\n\r\n")
try: s.sendall(req)
except OSError: pass
d = b""
try:
    while True:
        x = s.recv(65536)
        if not x: break
        d += x
except OSError: pass
print(d.split(b" ")[1].decode() if d.startswith(b"HTTP/") else "000")
