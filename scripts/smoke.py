"""D22 스모크: 변형마다 빌드 -> 실행 -> 상태 확인 -> 비루트·라벨(io.openit.*) 확인. 고정 포트 없음(같은 docker 네트워크의 curl 컨테이너로 확인), 컨테이너·네트워크 이름에 platform 과 임의 접미사,
시험이 만든 것만 지운다. 실패하면 컨테이너 로그를 $KEEP_DIR(기본 /tmp/platform-smoke-<접미사>)에 남긴 뒤 지운다. 종료 코드 0 = 전부 통과. 사용: bash scripts/smoke.sh
identity(Keycloak optimized)는 영역 이미지가 아니라 io.openit.* 라벨이 없다: identity/tests/test-idp-smoke.sh 가 실제로 띄워 확인한다(여기서 중복하지 않는다)."""
import json, os, pathlib, subprocess, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from ops_common import Stack, boundary_src, build, make_ca, sh

CURL = "curlimages/curl:8.10.1"
HARD = ["--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true"]
LABELS = ["io.openit.service", "io.openit.revision", "io.openit.contracts.boundary", "io.openit.contracts.survey-schema", "io.openit.model-runtime"]
results = []


def check(name, ok, detail=""):
    results.append(ok); print(("  PASS " if ok else "  FAIL ") + name + ("" if ok else f" :: {detail}"))


def image_checks(variant, service, tag):
    r = build(variant, tag) if variant is not None else None
    cfg = json.loads(sh("docker", "image", "inspect", tag).stdout)[0]["Config"]
    lab = cfg.get("Labels") or {}
    check(f"{service}: 라벨 {len(LABELS)}개가 있고 io.openit.service={service}", all(k in lab for k in LABELS) and lab.get("io.openit.service") == service, {k: lab.get(k) for k in LABELS})
    u = cfg.get("User") or ""
    check(f"{service}: 이미지 사용자가 root 가 아니다({u or '없음'})", u not in ("", "0", "root", "0:0"), u)


def http(st, url, *extra):
    """같은 네트워크의 curl 컨테이너로 요청한다. (상태 코드, 본문). 연결 실패는 ('000','')."""
    r = sh("docker", "run", "--rm", "--network", st.net, CURL, "-sk", "--max-time", "5", "-o", "/dev/stdout", "-w", "\n%{http_code}", *extra, url, check=False)
    body, _, code = r.stdout.rpartition("\n")
    return code or "000", body


def http_in(container, url, *extra):
    """확인 컨테이너를 대상의 네트워크 공간에 붙여 부른다(--network container:<이름>): 평문 HTTP 는 루프백에서만 연다(RUNTIME R1.1)."""
    r = sh("docker", "run", "--rm", "--network", f"container:{container}", CURL, "-sk", "--max-time", "5", "-o", "/dev/stdout", "-w", "\n%{http_code}", *extra, url, check=False)
    body, _, code = r.stdout.rpartition("\n")
    return code or "000", body


def wait(fn, what, seconds=60):
    """준비 확인: 조건이 참이 될 때까지 기다린다(상태 확인 자체가 준비 신호)."""
    end = time.time() + seconds
    while time.time() < end:
        v = fn()
        if v: return v
        time.sleep(1)
    return None


def main():
    st = Stack("platform-smoke")
    keep = pathlib.Path(os.environ.get("KEEP_DIR", str(ROOT / f"build/logs/smoke-{st.tag}")))
    tag = lambda v: f"platform-{v}:smoke-{st.tag}"
    imgs = []
    try:
        # ---- area-gateway (variant 없음): TLS 종단 응답이 오면 살아 있다(상류가 없어 503)
        t = tag("area-gateway"); imgs.append(t)
        # build() 는 variant 를 받는다: 영역 게이트웨이는 빈 값이 아니라 키가 없어야 한다
        req = pathlib.Path(st.d / "req.json")
        ver = "v" + sh(str(ROOT / ".venv/bin/python"), "-c", "import importlib.metadata as m;print(m.version('boundary-contracts'))").stdout.strip()
        req.write_text(json.dumps({"source_dir": str(ROOT), "revision": "abcdef1", "versions": {"boundary": ver}, "dependency_sources": {"boundary": boundary_src()}, "image_tag": t}))
        b = subprocess.run(["bash", str(ROOT / "scripts/build-image.sh"), str(req)], capture_output=True, text=True); assert b.returncode == 0, b.stderr[-1500:]
        image_checks(None, "area-gateway", t)
        make_ca(st.d, "svc", "svc", "localhost")
        (st.d / "certs").mkdir(); (st.d / "certs/tls.crt").write_text((st.d / "svc.crt").read_text()); (st.d / "certs/tls.key").write_text((st.d / "svc.key").read_text())
        ex = json.loads((pathlib.Path(boundary_src()) / "examples/Exposure.json").read_text()); ex["service"] = "svc"
        (st.d / "exposure.json").write_text(json.dumps(ex))
        for p in [st.d / "exposure.json"]: p.chmod(0o644)
        st.run("area-gateway", "--network-alias", "svc", *HARD, "--tmpfs", "/tmp", "-v", f"{st.d}/exposure.json:/etc/openit/exposure.json:ro", "-v", f"{st.d}/certs:/certs:ro", t)
        code = wait(lambda: (lambda c: c if c != "000" else None)(http(st, "https://svc/")[0]), "gw")
        check("area-gateway: TLS 응답이 온다(상류 없음이라 5xx 도 살아 있음의 증거)", code is not None, code)

        # ---- public-ingress: 평문 8080 /healthz
        t = tag("public-ingress"); imgs.append(t); image_checks("public-ingress", "public-ingress", t)
        sec = st.d / "sec"; pki = st.d / "ipki"; pki.mkdir()
        sh("bash", str(ROOT / "ingress/scripts/gen-test-secrets.sh"), str(sec))
        dca = st.d / "dpki" / "ca.crt"; subprocess.run(["bash", str(ROOT / "ingress/scripts/device-pki.sh"), "init"], env=dict(os.environ, DEVICE_PKI_DIR=str(st.d / "dpki")), capture_output=True, check=True)   # 기기 CA(필수 입력)
        mounts = sh("bash", "-c", f"source {ROOT}/scripts/lib.sh && gateway_test_pki {pki} survey-service identity identity-proxy && gateway_test_mounts {pki} && echo $SECRETS_GID").stdout.split()
        gid = mounts[-1]; mounts = mounts[:-1]
        ing = st.run("public-ingress", "--network-alias", "ingress", "--user", "10001:10001", "--group-add", gid, *HARD, "--tmpfs", "/tmp:uid=10001,gid=10001", "--tmpfs", "/data:uid=10001,gid=10001", "--tmpfs", "/config:uid=10001,gid=10001",
               *mounts, "-e", "GATEWAY_HOSTS=localhost:8443, 127.0.0.1:8443", "-v", f"{ROOT}/ingress/tests/exposures:/etc/openit/exposures:ro", "-v", f"{sec}/tokens:/run/secrets:ro", "-v", f"{dca}:/etc/openit/device-ca.pem:ro", t)
        # 준비 확인: 응답이 올 때까지(000 = 연결 실패는 아직 준비 전). 튜플은 늘 참이라 wait 가 첫 시도에서 끝나던 결함을 고쳤다
        got = wait(lambda: (lambda r: r if r[0] != "000" else None)(http_in(ing, "http://127.0.0.1:8080/healthz")), "ingress")
        check("public-ingress: /healthz 200 + {\"status\":\"ok\"}", got is not None and got[0] == "200" and '"ok"' in got[1], got)

        # ---- monitoring: prometheus 역할 /-/healthy
        t = tag("monitoring"); imgs.append(t); image_checks("monitoring", "monitoring", t)
        (st.d / "targets").mkdir()
        for f in ("metrics", "readyz", "public", "gate"): (st.d / "targets" / f"{f}.yml").write_text("[]\n")
        (st.d / "targets").chmod(0o755)
        for p in (st.d / "targets").glob("*"): p.chmod(0o644)
        prom = st.run("prometheus", "--network-alias", "prometheus", *HARD, "--tmpfs", "/tmp", "--tmpfs", "/prometheus:uid=65534", "-v", f"{st.d}/root_ca.crt:/etc/openit/pki/root_ca.crt:ro", "-v", f"{st.d}/targets:/etc/openit/monitoring/targets:ro", t, "prometheus")
        got = wait(lambda: (lambda r: r if r[0] == "200" else None)(http_in(prom, "http://127.0.0.1:9090/-/healthy")), "prom")
        check("monitoring: prometheus /-/healthy 200", got is not None, got)

        # ---- backup-store: 자격 없는 요청은 401(TLS 위에서 서버가 살아 있다)
        t = tag("backup-store"); imgs.append(t); image_checks("backup-store", "backup-store", t)
        make_ca(st.d, "backup-store", "backup-store")
        (st.d / "tlsdir").mkdir(); (st.d / "tlsdir/tls.crt").write_text((st.d / "backup-store.crt").read_text()); (st.d / "tlsdir/tls.key").write_text((st.d / "backup-store.key").read_text())
        (st.d / "areas").mkdir(); (st.d / "areas/survey-service").write_text("survey-service:smoke-pw\n")
        for p in (st.d / "tlsdir").glob("*"): p.chmod(0o644)
        (st.d / "areas/survey-service").chmod(0o644)
        v = st.volume("bsdata")
        sh("docker", "run", "--rm", "-v", f"{v}:/data", "--user", "0", "--entrypoint", "chown", t, "65534:65534", "/data")
        st.run("backup-store", "--network-alias", "backup-store", *HARD, "--tmpfs", "/tmp", "-v", f"{v}:/data", "-v", f"{st.d}/areas:/run/secrets/areas:ro", "-v", f"{st.d}/tlsdir:/run/tls:ro", t)
        got = wait(lambda: (lambda r: r if r[0] != "000" else None)(http(st, "https://backup-store:8000/survey-service/config")), "bs")
        check("backup-store: TLS 위에서 자격 없는 요청은 401", got is not None and got[0] == "401", got)

        # ---- step-ca: 이미지의 HEALTHCHECK(step ca health)가 healthy
        t = tag("step-ca"); imgs.append(t); image_checks("step-ca", "step-ca", t)
        ca = st.volume("ca")
        sh("docker", "run", "--rm", "-v", f"{ca}:/v", "--user", "0", "--entrypoint", "chown", t, "1000:1000", "/v")
        (st.d / "pw").write_text("smoke-ca-password"); (st.d / "pw").chmod(0o644)
        c = st.run("step-ca", "--network-alias", "step-ca", *HARD, "--tmpfs", "/tmp:exec", "-v", f"{ca}:/home/step", "-v", f"{st.d}/pw:/run/secrets/step-ca-password:ro", t)
        h = wait(lambda: sh("docker", "inspect", "--format", "{{.State.Health.Status}}", c, check=False).stdout.strip() == "healthy" or None, "ca", 120)
        check("step-ca: HEALTHCHECK 가 healthy", bool(h), sh("docker", "inspect", "--format", "{{.State.Health.Status}}", c, check=False).stdout.strip())
        # ---- 사람 인증 이미지 3종: 빌드·라벨·비루트(실제 기동·로그인은 identity/tests/test-idp-smoke.sh 가 확인한다)
        for v in ("identity", "identity-proxy", "identity-db"):
            t = tag(v); imgs.append(t); image_checks(v, v, t)
    except Exception as e:  # 실패해도 로그를 남기고 정리한다
        check("스모크 진행", False, repr(e)[:300])
    finally:
        if not all(results):
            keep.mkdir(parents=True, exist_ok=True)
            for c in st.containers:
                (keep / f"{c}.log").write_text(st.logs(c))
            print(f"실패: 컨테이너 로그를 남겼다: {keep}")
        st.close()
        for i in imgs: sh("docker", "rmi", i, check=False)
    print("통과: 스모크" if results and all(results) else "실패: 스모크")
    return 0 if results and all(results) else 1


sys.exit(main())
