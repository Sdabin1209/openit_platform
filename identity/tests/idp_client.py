"""사람 인증 시험용 HTTP 클라이언트(platform 소유): 공개 입구(https)에 시험 PKI 루트만 신뢰하고 붙는다. 리다이렉트는 따라가지 않고 직접 따른다(응답을 그대로 단언하려고).
Keycloak 로그인 양식을 사람처럼 채워 쿠키 세션(_openit_session)을 얻는다. 암호는 호출자가 비밀 파일에서 읽어 넘긴다(출력하지 않는다)."""
import html, re, ssl, urllib.error, urllib.parse, urllib.request


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class Client:
    def __init__(self, base, ca):
        self.base = base
        ctx = ssl.create_default_context(cafile=ca)
        self.op = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect, urllib.request.HTTPSHandler(context=ctx))

    def raw(self, method, url, data=None, headers=None, jar=None):
        h = dict(headers or {})
        if jar:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in jar.items())
        req = urllib.request.Request(url if url.startswith("http") else self.base + url, data=data, method=method, headers=h)
        try:
            with self.op.open(req, timeout=30) as r:
                st, hd, body = r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            st, hd, body = e.code, e.headers, e.read()
        if jar is not None:
            for c in hd.get_all("Set-Cookie") or []:
                k, _, v = c.split(";", 1)[0].partition("=")
                if "max-age=0" in c.lower() or v == "":
                    jar.pop(k, None)
                else:
                    jar[k] = v
        return st, {k.lower(): v for k, v in hd.items()}, body

    def follow(self, method, url, jar, data=None, headers=None, limit=10):
        for _ in range(limit):
            st, hd, body = self.raw(method, url, data, headers, jar)
            loc = hd.get("location")
            if st in (301, 302, 303) and loc:
                url = urllib.parse.urljoin(url if url.startswith("http") else self.base + url, loc); method, data = "GET", None
                continue
            return st, hd, body, url
        raise RuntimeError("리다이렉트가 너무 많다")

    def login(self, user, password, rd="/"):
        """/oauth2/start 에서 Keycloak 로그인 양식을 거쳐 세션 쿠키를 얻는다. 쿠키 jar 를 돌려준다(실패하면 빈 dict)."""
        jar = {}
        st, hd, body, url = self.follow("GET", "/oauth2/start?rd=" + urllib.parse.quote(rd), jar, headers={"Accept": "text/html"})
        m = re.search(r'<form[^>]*id="kc-form-login"[^>]*action="([^"]+)"', body.decode("utf-8", "replace"))
        if not m:
            return {}
        action = urllib.parse.urljoin(url, html.unescape(m.group(1)))
        form = urllib.parse.urlencode({"username": user, "password": password, "credentialId": ""}).encode()
        self.follow("POST", action, jar, data=form, headers={"Content-Type": "application/x-www-form-urlencoded"})
        return jar if "_openit_session" in jar else {}

    def register(self, username, password):
        jar = {}
        st, hd, body, url = self.follow("GET", "/oauth2/start?rd=/", jar, headers={"Accept": "text/html"})
        m = re.search(r'href="([^"]*registration[^"]*)"', body.decode("utf-8", "replace"))
        if not m:
            return {}, "가입 링크가 없다"
        url = urllib.parse.urljoin(url, html.unescape(m.group(1)))
        st, hd, body, url = self.follow("GET", url, jar)
        m = re.search(r'<form[^>]*id="kc-register-form"[^>]*action="([^"]+)"', body.decode("utf-8", "replace"))
        if not m:
            return {}, "가입 양식이 없다"
        form = urllib.parse.urlencode({"username": username, "email": f"{username}@test.invalid", "firstName": "New", "lastName": "User", "password": password, "password-confirm": password}).encode()
        self.follow("POST", urllib.parse.urljoin(url, html.unescape(m.group(1))), jar, data=form, headers={"Content-Type": "application/x-www-form-urlencoded"})
        return (jar if "_openit_session" in jar else {}), "ok"
