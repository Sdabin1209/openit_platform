#!/usr/bin/env bash
# 영역 빌드 진입점(계약 BuildImageRequest/BuildImageResult). 사용: bash scripts/build-image.sh <요청 JSON 파일>   (영역 리포 루트에서)
# 표준 출력 마지막 줄 = BuildImageResult JSON 한 줄. 진행 기록은 표준 오류. 종료 0 성공. 환경 변수: DOCKER(기본 docker)뿐. 비밀 없음.
# 이 영역이 만드는 이미지(variant): 없음=영역 게이트웨이(area-gateway), public-ingress(공개 입구), monitoring, backup-store, step-ca. identity(Keycloak 위), identity-proxy(oauth2-proxy 위), identity-db(postgres 위) — 3.4.10(ADR 0004).
set -euo pipefail
cd "$(dirname "$0")/.."
DOCKER=${DOCKER:-docker}; PYTHON=.venv/bin/python
die() { echo "build-image: $*" >&2; exit 1; }
[ -x "$PYTHON" ] || die "$PYTHON 이 없다. 먼저 bash scripts/setup-env.sh 로 환경을 만든다"
[ $# -eq 1 ] && [ -f "$1" ] || die "사용: bash scripts/build-image.sh <요청 JSON 파일>"
VARS=$("$PYTHON" - "$1" <<'PY'
import json, shlex, sys
from boundary_contracts import validator
req = json.load(open(sys.argv[1], encoding="utf-8"))
errs = list(validator("BuildImageRequest").iter_errors(req))
if errs: sys.exit("build-image: BuildImageRequest 를 어긴 요청: " + errs[0].message[:200])
VAR = {"": ("area-gateway", "area-gateway"), "public-ingress": ("ingress", "public-ingress"), "monitoring": ("monitoring", "monitoring"), "backup-store": ("backup-store", "backup-store"), "step-ca": ("pki", "step-ca"), "identity": ("identity", "identity", "Dockerfile"), "identity-proxy": ("identity", "identity-proxy", "Dockerfile.proxy"), "identity-db": ("identity", "identity-db", "Dockerfile.db")}
v = req.get("variant") or ""
if v not in VAR: sys.exit("build-image: 이 영역은 variant 를 모른다: " + v)
if not (req.get("versions") or {}).get("boundary"): sys.exit("build-image: 이 영역이 쓰는 키가 요청에 없다: versions.boundary")
for k, val in {"SRC": req["source_dir"], "REVISION": req["revision"], "BOUNDARY_TAG": req["versions"]["boundary"], "IMAGE_TAG": req["image_tag"], "CTX": VAR[v][0], "SERVICE": VAR[v][1], "DOCKERFILE": (VAR[v][2] if len(VAR[v]) > 2 else "Dockerfile"), "BOUNDARY_SRC": (req.get("dependency_sources") or {}).get("boundary", "")}.items():
    print(f"{k}={shlex.quote(val)}")
PY
) || exit 1
eval "$VARS"
[ "$(cd "$SRC" && pwd -P)" = "$(pwd -P)" ] || die "source_dir($SRC)이 이 리포 루트가 아니다"
# 라벨 정직성: 요청 버전이 아니라 이 영역이 실제로 설치한 계약 패키지 버전으로 찍는다
ACTUAL="v$("$PYTHON" -c 'import importlib.metadata as m; print(m.version("boundary-contracts"))')"
[ "$ACTUAL" = "$BOUNDARY_TAG" ] || die "요청 versions.boundary($BOUNDARY_TAG)와 이 영역 환경의 계약 패키지($ACTUAL)가 다르다. setup-env.sh 를 다시 실행한다"
echo "build-image: $IMAGE_TAG (revision $REVISION, boundary $ACTUAL)" >&2
CTXARGS=()
# 모든 이미지가 기동 때 자기 Env 계약 스키마로 환경을 검증한다(common/envcheck): 스키마와 계약 패키지는 요청의 소스 트리에서만 받는다(빌드 중 이웃 리포·SSH 없음)
if true; then
  [ -d "$BOUNDARY_SRC" ] || die "이 이미지는 요청의 dependency_sources.boundary(계약 소스 트리)가 필요하다"
  BA="v$(sed -n 's/^version = "\(.*\)"$/\1/p' "$BOUNDARY_SRC/pyproject.toml" | head -1)"; [ "$BA" = "$ACTUAL" ] || die "dependency_sources.boundary 의 실제 버전($BA)이 환경의 계약 패키지($ACTUAL)와 다르다"
  CTXARGS=(--build-context "boundary_contracts=$BOUNDARY_SRC" --build-context "common=$PWD/common")
fi
# 노출 선언 라벨(io.openit.exposure, 계약 Exposure): 이 서비스가 받는 경로와 내보내는 호출. 정본은 $CTX/exposure-$SERVICE.json 한 곳이고 deploy 가 라벨에서 영역 게이트웨이·공개 입구 선언을 만든다(다른 영역 서비스와 같은 방식).
EXPARGS=(); if [ -f "$CTX/exposure-$SERVICE.json" ]; then
  EXPJSON=$("$PYTHON" - "$CTX/exposure-$SERVICE.json" "$SERVICE" <<'PY'
import json, sys
from boundary_contracts import validator
d = json.load(open(sys.argv[1], encoding="utf-8"))
errs = list(validator("Exposure").iter_errors(d))
if errs or d.get("service") != sys.argv[2]: sys.exit("build-image: 노출 선언이 계약 Exposure 를 어기거나 service 가 게시 이름과 다르다: " + (errs[0].message[:150] if errs else d.get("service", "")))
print(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
PY
  ) || exit 1
  EXPARGS=(--build-arg "EXPOSURE_JSON=$EXPJSON")
fi
"$DOCKER" build -q -t "$IMAGE_TAG" "${EXPARGS[@]}" --build-arg COMMIT="$REVISION" --build-arg BOUNDARY_TAG="$ACTUAL" -f "$CTX/$DOCKERFILE" "${CTXARGS[@]}" "$CTX" >&2
"$DOCKER" image inspect "$IMAGE_TAG" | "$PYTHON" -c '
import json, sys
from boundary_contracts import validator
img = json.load(sys.stdin)[0]
labels = {k: v for k, v in (img["Config"].get("Labels") or {}).items() if k.startswith("io.openit.")}
if labels.get("io.openit.service") != sys.argv[2]: sys.exit("build-image: 라벨 io.openit.service(%s)가 기대 %s 와 다르다" % (labels.get("io.openit.service"), sys.argv[2]))
res = {"image": sys.argv[1], "image_id": img["Id"], "labels": labels}
errs = list(validator("BuildImageResult").iter_errors(res)) + list(validator("ImageLabels").iter_errors(labels))
if errs: sys.exit("build-image: 결과가 계약을 어겼다: " + errs[0].message[:200])
print(json.dumps(res, ensure_ascii=False, separators=(",", ":")))' "$IMAGE_TAG" "$SERVICE"
