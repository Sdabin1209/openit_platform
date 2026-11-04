#!/usr/bin/env python3
"""platform 공개 입구의 경로 표 생성기(구조 점검 S9, ADR 0002). 각 영역의 Exposure 선언(라벨 io.openit.exposure 의 내용, 계약 스키마로 검증)에서 Caddy 경로 처리(routes.caddy)를 만든다.
손으로 쓴 영역 경로는 없다: 경로·메서드·인증 종류·역할·상류 토큰·사람 신원 헤더·스트리밍·시간 한도·본문 상한이 모두 선언에서 나온다.
계약: RUNTIME R2.1(앱 응답 그대로, 헤더는 앱이 정하지 않았을 때만 더함)·R3.5(본문 상한 413)·R3.13(기기 401)·R3.23(사람 401·302)·R3.24(역할 403, ACCOUNT_PENDING_APPROVAL)·R3.12(인증 확인 한도 503), CONVENTIONS 6절(신원 헤더).
 - machine-token 경로는 내보내지 않는다(3.4.7: 받는 서비스가 대조하고 compose 밖 기계 호출자는 hosts 표로 영역 게이트웨이에 바로 간다): 선언이 없는 것과 같다(404 바닥).
 - denied 는 404 BoundaryError(NOT_FOUND). Exposure 에 없는 /v1/* 도 404(Caddyfile 바닥 규칙).
사용: gen-ingress-routes.py <Exposure JSON 파일 또는 폴더>... > routes.caddy      (비밀 값 없음; 비밀은 {file./run/secrets/<이름>} 치환으로 설정을 읽을 때 Caddy 가 읽는다)"""
import json, pathlib, re, sys

ROLE_RE = r"(^|,)(%s)(,|$)"
CA = "/etc/openit/pki/root_ca.crt"
PERM = lambda msg, extra="": '{"pipeline_schema_version":"{$PIPELINE_SCHEMA_VERSION}","code":"PERMISSION_DENIED","message":"%s","retryable":false%s}' % (msg, extra)
PENDING = PERM("account pending approval", ',"details":{"reason":"ACCOUNT_PENDING_APPROVAL"}')
NOTFOUND = '{"pipeline_schema_version":"{$PIPELINE_SCHEMA_VERSION}","code":"NOT_FOUND","message":"not found","retryable":false}'
TOO_LARGE = '{"pipeline_schema_version":"{$PIPELINE_SCHEMA_VERSION}","code":"INVALID_RECORD","message":"request body too large","retryable":false,"details":{"max_body_bytes":%d}}'
OPERATIONAL = {"/healthz", "/readyz", "/metrics"}
DEFAULT_MAX_BODY = 8 * 1024 * 1024


def secs(ms):
    return ("%gs" % (ms / 1000)) if ms % 1000 else "%ds" % (ms // 1000)


def respond(status, body, extra=()):
    lines = ["header Content-Type application/json", "header Cache-Control no-store"] + list(extra)
    return lines + ["respond `%s` %d" % (body, status)]


def proxy(host, r, mode):
    """mode: account | authenticated | none | device_cert | device_token"""
    t = r.get("timeouts_ms") or {}
    out = ["reverse_proxy https://%s {" % host,
           "\theader_up X-Forwarded-Host {http.request.hostport}",
           "\theader_up Host {upstream_hostport}",
           "\theader_up -X-Openit-Dn"]
    # 신원 헤더: 클라이언트가 보낸 값은 항상 지우고(CONVENTIONS 6절), 정해진 경로에서만 게이트웨이가 붙인다
    if mode == "device_cert":
        out.append('\theader_up X-Openit-Device "{re.devcn.1}"')
    else:
        out.append("\theader_up -X-Openit-Device")
    if r.get("user_header") == "set" and mode in ("account", "authenticated"):
        out += ['\theader_up X-Openit-User "{http.request.header.X-Auth-Request-Preferred-Username}"', '\theader_up X-Openit-Roles "{http.request.header.X-Auth-Request-Groups}"']
    else:
        out += ["\theader_up -X-Openit-User", "\theader_up -X-Openit-Roles"]
    if r.get("upstream_token"):
        out.append('\theader_up Authorization "Bearer {file./run/secrets/%s}"' % r["upstream_token"])
    elif mode != "device_token":
        out.append("\theader_up -Authorization")   # 클라이언트 자격은 서비스로 넘기지 않는다(기기 토큰 호환 경로 제외)
    if r.get("streaming"):
        out.append("\tflush_interval -1")
    out += ["\tlb_try_duration 0", "\ttransport http {", "\t\ttls_trusted_ca_certs " + CA, "\t\tdial_timeout %s" % secs(t.get("dial", 1000))]
    if t.get("response_header"):
        out.append("\t\tresponse_header_timeout %s" % secs(t["response_header"]))
    if t.get("read"):
        out.append("\t\tread_timeout %s" % secs(t["read"]))
    out += ["\t}", "}"]
    return out


def indent(lines, n=1):
    return ["\t" * n + l if l else l for l in lines]


def block(name, matcher_lines, body):
    return ["@%s {" % name] + indent(matcher_lines) + ["}", "handle @%s {" % name] + indent(body) + ["}"]


def role_expr(roles):
    return "expression `{http.request.header.X-Auth-Request-Groups}.matches(\"%s\")`" % (ROLE_RE % "|".join(sorted(roles)))


def gen(exposures):
    atoms = {}   # (path, 메서드 튜플) -> [(service, route)]
    for e in exposures:
        for r in e["routes"]:
            kind = r["auth"]["kind"]
            if kind == "machine-token":
                continue   # 내보내지 않는다: 이 경로는 아래 바닥 규칙(404)이거나 다른 선언이 정한다
            if kind == "denied":
                continue   # 거부 선언은 경로를 만들지 않는다: 선언이 없는 경로는 아래 바닥 규칙(404)이다. 같은 경로를 다른 영역이 열었으면 그 선언이 서비스한다(HTTP.md I1)
            for p in r["paths"]:
                if p in OPERATIONAL:
                    continue   # 영역의 상태·지표 경로는 영역 게이트웨이로만 닿고 공개 입구에 열지 않는다(CONVENTIONS 78행, R5.1·R10.11). 입구 자기 /healthz·/readyz 는 Caddyfile 이 따로 둔다
                atoms.setdefault((p, tuple(sorted(r.get("methods") or []))), []).append((e["service"], r))
    # 같은 공개 경로를 서로 다른 서비스가 겹치는 메서드로 열면 주인이 둘이다: 시작하지 않는다(종료 65). 메서드를 적지 않은 선언은 모든 메서드다
    by_path = {}
    for (path, methods), opts in atoms.items():
        for svc in {o[0] for o in opts}:
            by_path.setdefault(path, []).append((svc, set(methods)))
    for path, owners in by_path.items():
        for i, (a, ma) in enumerate(owners):
            for b, mb in owners[i + 1:]:
                if a != b and (not ma or not mb or ma & mb):
                    raise SystemExit("같은 공개 경로를 두 서비스가 연다: %s %s" % (path, sorted({a, b})))
    out = ["# 생성됨(platform ingress/gen-ingress-routes.py): 각 영역 Exposure 선언에서 만든다. 직접 고치지 않는다.", ""]
    n = 0
    # 2) 허용 경로: 정확한 경로(와일드카드 없음)가 먼저, 긴 패턴이 먼저
    floor_done = False
    for (path, methods), opts in sorted(atoms.items(), key=lambda kv: (kv[0][0] == "/*", "*" in kv[0][0], -len(kv[0][0]), kv[0][0], kv[0][1])):
        if path == "/*" and not floor_done:   # 선언에 없는 /v1/* 는 404(루트 정적 화면 /* 가 삼키지 않게)
            floor_done = True
            out += block("v1floor", ["path /v1/*"], respond(404, NOTFOUND)) + [""]
        n += 1
        m = ["path " + path] + (["method " + " ".join(methods)] if methods else [])
        kinds = {o[1]["auth"]["kind"] for o in opts}
        body = []
        limit = max(o[1].get("max_body_bytes", DEFAULT_MAX_BODY) for o in opts)
        if limit != DEFAULT_MAX_BODY:
            body += ["request_body {", "\tmax_size %d" % limit, "}"]
        if kinds == {"device-token"}:
            svc, r = opts[0]
            body += ["handle @device_cert {", "\theader ?Cache-Control no-store"] + indent(proxy(svc, r, "device_cert")) + ["}",
                     "handle @device_ok {", "\theader ?Cache-Control no-store"] + indent(proxy(svc, r, "device_token")) + ["}",
                     "handle {"] + indent(respond(401, PERM("device authentication failed"), ["header WWW-Authenticate Bearer"])) + ["}"]
        elif kinds <= {"account", "authenticated"}:
            body += ["import authenticate"]
            auth_only = [o for o in opts if o[1]["auth"]["kind"] == "authenticated"]
            acct = [o for o in opts if o[1]["auth"]["kind"] == "account"]
            if acct:   # 가입 승인 대기(역할 없음)는 403 ACCOUNT_PENDING_APPROVAL, authenticated 경로는 역할 없이도 연다(R3.24)
                if not auth_only:
                    body += block("pending%d" % n, ["expression `{http.request.header.X-Auth-Request-Groups} == \"\"`"], respond(403, PENDING))
            for i, (svc, r) in enumerate(auth_only):
                body += ["header ?Cache-Control no-store"] + proxy(svc, r, "authenticated")
            for i, (svc, r) in enumerate(acct):
                body += block("r%d_%d" % (n, i), [role_expr(r["auth"]["roles"])], ["header ?Cache-Control no-store"] + proxy(svc, r, "account"))
            if acct and not auth_only:
                body += ["handle {"] + indent(respond(403, PERM("role required"))) + ["}"]
        elif kinds == {"none"}:
            svc, r = opts[0]
            body += ["header ?Cache-Control no-store"] + proxy(svc, r, "none")
        else:
            raise SystemExit("한 경로·메서드에 섞인 인증 종류는 처리하지 못한다: %s %s %s" % (path, methods, sorted(kinds)))
        out += block("a%d" % n, m, body) + [""]
    out += ["# 바닥: 선언에 없는 경로는 404 BoundaryError(R3.5)"] + block("floor", ["path /*"], respond(404, NOTFOUND))
    # route 안에 써서 Caddy 가 handle 을 다시 정렬하지 않게 한다(순서가 곧 우선순위). Caddyfile 의 `order route last` 와 짝
    return "route {\n" + "\n".join(("\t" + l) if l else l for l in out) + "\n}\n"


def load(args):
    from boundary_contracts import validator
    files = []
    for a in args:
        p = pathlib.Path(a)
        files += sorted(p.glob("*.json")) if p.is_dir() else [p]
    if not files:
        sys.exit("Exposure 선언이 없다")
    ex = []
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        errs = list(validator("Exposure").iter_errors(d))
        if errs:
            sys.exit("%s: Exposure 선언이 계약을 어겼다: %s" % (f.name, errs[0].message[:200]))
        ex.append(d)
    return ex


if __name__ == "__main__":
    sys.stdout.write(gen(load(sys.argv[1:])))
