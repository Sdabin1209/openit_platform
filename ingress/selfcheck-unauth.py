#!/usr/bin/env python3
"""공개 입구의 '인증 없는 요청' 자체 점검(platform 이 아는 사실의 정본, 손 표 없음). 마운트된 영역 Exposure 선언에서 기대 행을 만들고, 띄운 공개 입구에 쿠키·토큰 없는 요청을 보내 응답을 대조한다.
기대(RUNTIME R3.13·R3.23, CONVENTIONS 6절):
 - auth.kind=device-token: 토큰 없으면 401 + WWW-Authenticate: Bearer (realm 없음: 세션 경로와 구분된다)
 - auth.kind=account|authenticated: /v1/ 경로는 401 + WWW-Authenticate: Bearer realm="openit" + BoundaryError(PERMISSION_DENIED); 그 밖의 GET 화면은 Accept: text/html 이면 302 /oauth2/start, html 이 아니면 401
 - 선언에 없는 /v1/ 경로: 404 BoundaryError(NOT_FOUND)
 - auth.kind=none·denied·machine-token 은 기대 행을 만들지 않는다(없는 인증을 점검할 수 없고, 상류가 답하므로 공개 입구가 정하는 응답이 아니다)
사용: selfcheck-unauth <https://주소:포트> --cacert <공개 입구 인증서를 검증할 루트 PEM> [--exposures 폴더...]   기본 폴더: /etc/openit/exposures
출력: 줄마다 PASS 또는 FAIL 과 근거. 종료 코드 0 모두 일치, 1 어긋남, 2 입력 오류(선언 없음·계약 위반). 비밀 값 없음."""
import json, pathlib, ssl, sys, urllib.error, urllib.request

DEFAULT = ["/etc/openit/exposures"]
OPERATIONAL = {"/healthz", "/readyz", "/metrics"}


def concrete(path):
    return path.replace("*", "x")


def rows(exposures):
    """(메서드, 경로, 종류, 기대) 행. 같은 (메서드, 경로)는 한 번만."""
    seen, out = set(), []
    for e in exposures:
        for r in e["routes"]:
            kind = r["auth"]["kind"]
            if kind not in ("device-token", "account", "authenticated"):
                continue
            for p in r["paths"]:
                if p in OPERATIONAL:
                    continue
                for m in (r.get("methods") or ["GET"]):
                    key = (m, concrete(p))
                    if key not in seen:
                        seen.add(key); out.append((m, concrete(p), kind))
    return out


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def request(base, ctx, method, path, accept=None):
    h = {"Accept": accept} if accept else {}
    data = None if method in ("GET", "HEAD") else b"{}"
    if data: h["Content-Type"] = "application/json"
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect, urllib.request.HTTPSHandler(context=ctx))
    try:
        with op.open(urllib.request.Request(base + path, data=data, method=method, headers=h), timeout=10) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()
    except OSError as e:
        return 0, {}, str(e).encode()


def body_code(b):
    try: return json.loads(b).get("code")
    except Exception: return None


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__.split("사용:")[1].split("\n")[0], file=sys.stderr); return 2
    base, args, cafile, dirs = argv[0].rstrip("/"), argv[1:], None, []
    i = 0
    while i < len(args):
        if args[i] == "--cacert": cafile = args[i + 1]; i += 2
        elif args[i] == "--exposures":
            i += 1
            while i < len(args) and not args[i].startswith("--"): dirs.append(args[i]); i += 1
        else: print("알 수 없는 인자: " + args[i], file=sys.stderr); return 2
    from boundary_contracts import validator
    files = []
    for d in (dirs or DEFAULT):
        p = pathlib.Path(d)
        if p.is_dir(): files += sorted(p.glob("*.json"))
    if not files:
        print("Exposure 선언이 없다", file=sys.stderr); return 2
    exposures = []
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        errs = list(validator("Exposure").iter_errors(d))
        if errs:
            print(f"{f.name}: Exposure 선언이 계약을 어겼다", file=sys.stderr); return 2
        exposures.append(d)
    if not cafile:
        print("--cacert 가 필요하다(인증서 검증을 끄지 않는다)", file=sys.stderr); return 2
    ctx = ssl.create_default_context(cafile=cafile)
    bad = n = 0

    def report(ok, what, detail=""):
        nonlocal bad, n
        n += 1; bad += 0 if ok else 1
        print(("PASS " if ok else "FAIL ") + what + ("" if ok else " :: " + detail))

    for m, p, kind in rows(exposures):
        if kind == "device-token":
            st, h, b = request(base, ctx, m, p)
            wa = h.get("WWW-Authenticate", "") if h else ""
            report(st == 401 and wa == "Bearer", f"{m} {p} (device-token) 토큰 없음 -> 401 + WWW-Authenticate: Bearer", f"{st} '{wa}'")
        elif p.startswith("/v1/"):
            st, h, b = request(base, ctx, m, p)
            wa = h.get("WWW-Authenticate", "") if h else ""
            report(st == 401 and wa == 'Bearer realm="openit"' and body_code(b) == "PERMISSION_DENIED", f"{m} {p} ({kind}) 세션 없음 -> 401 + Bearer realm=\"openit\" + PERMISSION_DENIED", f"{st} '{wa}' {body_code(b)}")
        else:
            if m == "GET":
                st, h, b = request(base, ctx, m, p, "text/html")
                loc = (h.get("Location", "") if h else "")
                report(st == 302 and loc.startswith("/oauth2/start"), f"{m} {p} ({kind}) 화면(html) 세션 없음 -> 302 /oauth2/start", f"{st} '{loc}'")
            st, h, b = request(base, ctx, m, p)
            wa = h.get("WWW-Authenticate", "") if h else ""
            report(st == 401 and wa == 'Bearer realm="openit"', f"{m} {p} ({kind}) html 아닌 요청 세션 없음 -> 401 + Bearer realm=\"openit\"", f"{st} '{wa}'")
    st, h, b = request(base, ctx, "GET", "/v1/__undeclared__")
    report(st == 404 and body_code(b) == "NOT_FOUND", "GET /v1/__undeclared__ 선언 없는 경로 -> 404 NOT_FOUND", f"{st} {body_code(b)}")
    print(f"{'일치' if bad == 0 else '어긋남'}: {n}건 중 {bad}건 어긋남")
    return 0 if bad == 0 and n > 1 else 1


sys.exit(main(sys.argv[1:]))
