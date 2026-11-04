"""공개 입구를 통한 로그인 한 번이 되는지(OK) 안 되는지(FAIL)를 출력한다. 사용: login_check.py <포트> <루트 CA> <사용자> <암호 파일>. 암호는 출력하지 않는다.
준비 확인: 공개 입구가 /oauth2/start 에 응답할 때까지 기다린다(영역 게이트웨이를 다시 만든 직후를 위한 것이고, 로그인 자체는 한 번만 시도한다)."""
import sys, time
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from idp_client import Client
port, ca, user, pwfile = sys.argv[1:5]
c = Client(f"https://localhost:{port}", ca)
end = time.time() + 60
while time.time() < end:
    st, _, _ = c.raw("GET", "/oauth2/start", headers={"Accept": "text/html"})
    if st in (200, 302): break
    time.sleep(1)
print("OK" if c.login(user, open(pwfile).read().strip()) else "FAIL")
