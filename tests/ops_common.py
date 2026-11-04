"""운영 이미지(monitoring·backup-store·step-ca) 시험 공용. 빌드 입력은 이웃 작업 트리가 아니라 requirements.txt 의 고정 태그를 받은 것이다(fetch-boundary-src.sh).
외부 이미지는 locks/images.lock 의 digest 로 쓴다(시험이 쓰는 이미지가 배포가 쓰는 것과 같다)."""
import json, pathlib, shutil, subprocess, tempfile, uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv/bin/python")


def sh(*a, check=True, timeout=120, **kw):
    return subprocess.run(a, capture_output=True, text=True, timeout=timeout, check=check, **kw)


def have_docker():
    return sh("docker", "version", check=False).returncode == 0


def lock(name):
    for line in (ROOT / "locks/images.lock").read_text().splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1]
    raise KeyError(name)


_SRC = {}


def boundary_src():
    """고정 태그 계약 소스(한 번만 받는다)."""
    if "p" not in _SRC:
        d = pathlib.Path(tempfile.mkdtemp(prefix="ops-bc-")) / "src"
        _SRC["p"] = sh("bash", str(ROOT / "scripts/fetch-boundary-src.sh"), str(d)).stdout.strip()
    return _SRC["p"]


def build(variant, tag):
    """scripts/build-image.sh 로 변형 이미지를 빌드한다. 반환: BuildImageResult(dict)."""
    ver = "v" + sh(PY, "-c", "import importlib.metadata as m;print(m.version('boundary-contracts'))").stdout.strip()
    d = pathlib.Path(tempfile.mkdtemp(prefix="ops-req-"))
    req = {"source_dir": str(ROOT), "revision": "abcdef1", "versions": {"boundary": ver}, "dependency_sources": {"boundary": boundary_src()}, "image_tag": tag, "variant": variant}
    (d / "r.json").write_text(json.dumps(req))
    b = subprocess.run(["bash", str(ROOT / "scripts/build-image.sh"), str(d / "r.json")], text=True, capture_output=True)
    shutil.rmtree(d, ignore_errors=True)
    assert b.returncode == 0, "이미지를 만들지 못했다:\n" + b.stderr[-1500:]
    return json.loads(b.stdout.strip().splitlines()[-1])


class Stack:
    """시험이 띄운 컨테이너·네트워크·볼륨만 지운다(이름을 기록해 둔 것만)."""
    def __init__(self, prefix):
        self.tag = uuid.uuid4().hex[:8]
        self.net = f"{prefix}-{self.tag}"
        self.d = pathlib.Path(tempfile.mkdtemp(prefix=prefix + "-"))
        self.d.chmod(0o755)
        self.containers, self.volumes = [], []
        sh("docker", "network", "create", self.net)

    def run(self, name, *args, detach=True):
        full = f"{name}-{self.tag}"
        if detach:
            self.containers.append(full)
            sh("docker", "run", "-d", "--name", full, "--network", self.net, *args)
        return full

    def volume(self, name):
        v = f"{name}-{self.tag}"
        self.volumes.append(v)
        sh("docker", "volume", "create", v)
        return v

    def logs(self, name):
        r = sh("docker", "logs", name, check=False)
        return r.stdout + r.stderr

    def close(self):
        for c in self.containers:
            sh("docker", "rm", "-f", c, check=False)
        sh("docker", "network", "rm", self.net, check=False)
        for v in self.volumes:
            sh("docker", "volume", "rm", "-f", v, check=False)
        shutil.rmtree(self.d, ignore_errors=True)


def make_ca(d, name, *sans):
    """일회용 루트 CA 와 그가 서명한 잎 인증서(d/<name>.crt, .key, root_ca.crt)."""
    d = pathlib.Path(d)
    if not (d / "root_ca.crt").exists():
        sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(d / "root.key"), "-out", str(d / "root_ca.crt"), "-subj", "/CN=openit-ops-test-root", "-days", "2")
    sh("openssl", "req", "-newkey", "rsa:2048", "-nodes", "-keyout", str(d / f"{name}.key"), "-out", str(d / f"{name}.csr"), "-subj", f"/CN={name}")
    (d / f"{name}.ext").write_text("subjectAltName=" + ",".join(f"DNS:{s}" for s in (sans or (name,))) + "\n")
    sh("openssl", "x509", "-req", "-in", str(d / f"{name}.csr"), "-CA", str(d / "root_ca.crt"), "-CAkey", str(d / "root.key"), "-CAcreateserial", "-out", str(d / f"{name}.crt"), "-days", "2", "-extfile", str(d / f"{name}.ext"))
    for p in d.glob("*"):
        if p.is_file():
            p.chmod(0o644)
