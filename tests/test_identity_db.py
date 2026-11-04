"""identity-db(D126, 3.4.10): 계약 AreaDatabaseEnv 로 뜨고, 서버 TLS 인증서가 바뀌면(step-ca renew) 재시작 없이 새 인증서를 내보낸다. 이미지는 지금 이 리포에서 빌드한다."""
import json, pathlib, subprocess, time
import pytest
from ops_common import Stack, build, have_docker, make_ca, sh

pytestmark = pytest.mark.skipif(not have_docker(), reason="Docker 가 필요하다")
OSSL = "alpine/openssl"


def served_fp(st, host="identity-db"):
    r = sh("docker", "run", "--rm", "--network", st.net, OSSL, "s_client", "-starttls", "postgres", "-connect", f"{host}:5432", check=False, timeout=30)
    pem = r.stdout[r.stdout.find("-----BEGIN CERTIFICATE-----"):r.stdout.find("-----END CERTIFICATE-----") + 25]
    if "BEGIN" not in pem: return None
    fp = subprocess.run(["openssl", "x509", "-noout", "-fingerprint", "-sha256"], input=pem, capture_output=True, text=True).stdout.strip()
    return fp or None


def start_time(st):
    return sh("docker", "exec", st.containers[-1], "psql", "-X", "-q", "-U", "postgres", "-d", "postgres", "-tAc", "select pg_postmaster_start_time()", check=False).stdout.strip()


def file_fp(p):
    return sh("openssl", "x509", "-in", str(p), "-noout", "-fingerprint", "-sha256").stdout.strip()


def test_identity_db_serves_tls_and_picks_up_a_renewed_certificate_without_restart():
    st = Stack("pdb")
    tag = f"platform-identity-db:t-{st.tag}"
    try:
        build("identity-db", tag)
        make_ca(st.d, "a", "identity-db"); make_ca(st.d, "b", "identity-db")   # 같은 루트가 서명한 인증서 둘(A: 처음, B: 갱신 뒤)
        certs = st.d / "certs"; certs.mkdir(); certs.chmod(0o755)
        for n in ("crt", "key"): (certs / f"tls.{n}").write_text((st.d / f"a.{n}").read_text())
        for f in certs.glob("*"): f.chmod(0o644)
        (st.d / "pw").write_text("superuser-pw"); (st.d / "pw").chmod(0o644)
        (st.d / "db").mkdir(); (st.d / "db/identity").write_text("identity-pw"); (st.d / "db").chmod(0o755); (st.d / "db/identity").chmod(0o644)
        vol = st.volume("dbdata")
        st.run("identity-db", "--network-alias", "identity-db", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp", "--tmpfs", "/var/run/postgresql:uid=999,gid=999",
               "-e", "POSTGRES_PASSWORD_FILE=/run/secrets/pw", "-v", f"{st.d}/pw:/run/secrets/pw:ro", "-v", f"{st.d}/db:/run/secrets/db:ro", "-v", f"{certs}:/certs:ro", "-v", f"{vol}:/var/lib/postgresql/data", tag)
        want_a = file_fp(st.d / "a.crt"); want_b = file_fp(st.d / "b.crt")
        end = time.time() + 90; got = None
        while time.time() < end and got != want_a:   # 준비 확인: 서버가 올라와 TLS 로 A 를 낼 때까지
            got = served_fp(st); time.sleep(2)
        assert got == want_a, st.logs(st.containers[-1])[-800:]
        t0 = start_time(st)
        for n in ("crt", "key"): (certs / f"tls.{n}").write_text((st.d / f"b.{n}").read_text())   # step-ca renew 가 같은 경로의 파일을 바꾼다
        end = time.time() + 75
        while time.time() < end and got != want_b:   # 감시 루프 주기(30초) 안에 새 인증서를 낸다
            got = served_fp(st); time.sleep(3)
        assert got == want_b, "재시작 없이 새 인증서로 바뀌지 않았다"
        assert start_time(st) == t0, "서버가 재시작됐다"   # 재시작하지 않고 설정만 다시 읽었다
        # 변이: 계정은 첫 초기화 때 DatabaseDeclaration 대로 만들어졌다(암호는 파일에서)
        r = sh("docker", "exec", st.containers[-1], "psql", "-X", "-q", "-U", "postgres", "-d", "postgres", "-tAc", "select rolname||':'||rolsuper from pg_roles where rolname='identity'", check=False)
        assert r.stdout.strip() == "identity:false", r.stdout + r.stderr
    finally:
        sh("docker", "rmi", tag, check=False)
        st.close()


def test_identity_db_healthcheck_is_healthy_and_turns_unhealthy_without_tls_files():
    # Dockerfile HEALTHCHECK: 선언 계정으로 TLS 접속이 되면 healthy. 변이: TLS 인증서 파일을 빼면 unhealthy
    st = Stack("pdh")
    tag = f"platform-identity-db:h-{st.tag}"
    try:
        build("identity-db", tag)
        assert json.loads(sh("docker", "image", "inspect", tag).stdout)[0]["Config"].get("Healthcheck"), "HEALTHCHECK 가 없다"
        make_ca(st.d, "a", "identity-db")
        certs = st.d / "certs"; certs.mkdir(); certs.chmod(0o755)
        for n in ("crt", "key"): (certs / f"tls.{n}").write_text((st.d / f"a.{n}").read_text())
        for f in certs.glob("*"): f.chmod(0o644)
        (st.d / "pw").write_text("superuser-pw"); (st.d / "pw").chmod(0o644)
        (st.d / "db").mkdir(); (st.d / "db/identity").write_text("identity-pw"); (st.d / "db").chmod(0o755); (st.d / "db/identity").chmod(0o644)
        vol = st.volume("dbdata")
        c = st.run("identity-db", "--network-alias", "identity-db", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp", "--tmpfs", "/var/run/postgresql:uid=999,gid=999",
                   "-e", "POSTGRES_PASSWORD_FILE=/run/secrets/pw", "-v", f"{st.d}/pw:/run/secrets/pw:ro", "-v", f"{st.d}/db:/run/secrets/db:ro", "-v", f"{certs}:/certs:ro", "-v", f"{vol}:/var/lib/postgresql/data", tag)
        def status():
            return sh("docker", "inspect", "--format", "{{.State.Health.Status}}", c, check=False).stdout.strip()
        end = time.time() + 120; s = ""
        while time.time() < end and s != "healthy":   # 준비 확인: 건강 확인 자체가 준비 신호다
            s = status(); time.sleep(3)
        assert s == "healthy", st.logs(c)[-600:]
        (certs / "tls.crt").unlink()   # 변이: TLS 인증서 파일을 뺀다
        end = time.time() + 90
        while time.time() < end and s != "unhealthy":
            s = status(); time.sleep(3)
        assert s == "unhealthy"
    finally:
        sh("docker", "rmi", tag, check=False)
        st.close()
