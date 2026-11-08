"""조립: Exposure 선언 파일·폴더를 읽고 계약으로 검증해 ingress_routes 컴포넌트로 경로 표를 만든다."""
import pathlib, sys
from boundary_contracts import BoundaryError, strict_json, validate
from openit_platform.components.ingress_routes import gen


def load(args):
    files = []
    for a in args:
        p = pathlib.Path(a)
        files += sorted(p.glob("*.json")) if p.is_dir() else [p]
    if not files:
        sys.exit("Exposure 선언이 없다")
    ex = []
    for f in files:
        try:
            d = strict_json.loads(f.read_text(encoding="utf-8"))   # 이웃 영역이 쓴 선언: 계약 JSON 공통 규칙을 지난다
            validate("Exposure", d)
        except BoundaryError as e:   # 오류에 값을 싣지 않는다(INTERFACES I7): 스키마 위치와 키워드만
            sys.exit("%s: Exposure 선언이 계약을 어겼다: %s" % (f.name, e.details))
        ex.append(d)
    return ex


def main(argv):
    sys.stdout.write(gen(load(argv)))
