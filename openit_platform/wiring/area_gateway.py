"""조립: 인자·Exposure 파일을 읽어 area_gateway_config 컴포넌트로 설정을 만들어 낸다."""
import argparse, json, sys
from boundary_contracts import BoundaryError, strict_json, validate, validator
from openit_platform.components.area_gateway_config import build


def main(argv):
    ap = argparse.ArgumentParser(description="영역 게이트웨이 설정 생성기(platform, ADR 0001)")
    ap.add_argument("--exposure", required=True); ap.add_argument("--upstream", required=True)
    ap.add_argument("--cert", default="/certs/tls.crt"); ap.add_argument("--key", default="/certs/tls.key")
    ap.add_argument("--ingress-port", type=int, default=443); ap.add_argument("--egress-port", type=int, default=3128)
    ap.add_argument("--route-upstream", action="append", default=[], metavar="PREFIX=host:port", help="경로 접두사별 상류(영역 안 컴포넌트가 여럿일 때). 여러 번 줄 수 있다")
    ap.add_argument("--sds-path", default="/etc/envoy/sds.yaml", help="Envoy 가 SDS 파일을 읽는 경로(설정에 들어간다)")
    ap.add_argument("--no-ingress", action="store_true", help="들어오는 쪽 listener 를 열지 않는다(나가는 쪽 전용). entrypoint 가 인증서 폴더(/certs)가 마운트되지 않았을 때 준다")
    ap.add_argument("--sds-out", help="SDS 파일을 이 경로에 쓴다(기본: 표준 출력에 설정만)")
    a = ap.parse_args(argv)
    if not validator("_common#/$defs/LoopbackHostPort").is_valid(a.upstream):
        sys.exit("upstream 은 host:port 여야 한다")
    try:
        exposure = strict_json.loads(open(a.exposure, encoding="utf-8").read())   # 계약 JSON 공통 규칙
        validate("Exposure", exposure)
    except BoundaryError as e:   # 오류에 값을 싣지 않는다(INTERFACES I7): 스키마 위치와 키워드만
        sys.exit("Exposure 선언이 계약을 어겼다: %s" % (e.details,))
    ru = {}
    for x in a.route_upstream:
        pre, _, hp = x.partition("=")
        if not pre.startswith("/") or not validator("_common#/$defs/LoopbackHostPort").is_valid(hp):
            sys.exit("--route-upstream 은 /접두사=host:port 여야 한다: " + x)
        ru[pre] = hp
    cfg, sds = build(exposure, a.upstream, a.cert, a.key, a.ingress_port, a.egress_port, ru, a.sds_path, ingress=not a.no_ingress)
    if a.sds_out and sds:
        json.dump(sds, open(a.sds_out, "w"), indent=1)
    json.dump(cfg, sys.stdout, indent=1, ensure_ascii=False)
    print()
