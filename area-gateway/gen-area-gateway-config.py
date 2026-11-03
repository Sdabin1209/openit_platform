#!/usr/bin/env python3
"""영역 게이트웨이 설정 생성기(platform 영역, ADR 0001). 영역의 Exposure 선언(라벨 io.openit.exposure 의 내용)과 배치 값에서 Envoy 설정을 만든다.
들어오는 쪽: 서비스 이름 인증서로 TLS 를 끝내고 영역 안 컴포넌트(upstream)로 넘긴다(RUNTIME R1.1, CONVENTIONS 13절). 인증서·키 파일이 바뀌면 Envoy 가 SDS 파일 감시로 다시 읽는다(재시작·reload 불필요).
나가는 쪽: 영역 안 컴포넌트의 영역 밖 호출은 같은 네트워크 공간의 loopback(127.0.0.1:3128, 계약 R1.8·CommonEnv OPENIT_EGRESS_PROXY)에서 받아 HTTP CONNECT 터널(RFC 9110 9.3.6)로 나간다. Exposure.egress 에 선언한 상대의 `<이름>:443` 에만 터널을 열고 그 밖은 403 BoundaryError(PERMISSION_DENIED, details.reason=EGRESS_DENIED)로 거절한다(R1.8·R6.2).
이미지 안에서는 entrypoint.sh 가 부른다(입력은 Dockerfile 머리말). 사용: gen-area-gateway-config.py --exposure <Exposure JSON 파일> --upstream <host:port> [--cert F --key F] [--ingress-port 443 --egress-port 3128] > envoy.yaml
입력은 Exposure 계약 스키마로 검증한다(CONVENTIONS 3절). 비밀 값 없음."""
import argparse, json, re, sys

DENIED = {"pipeline_schema_version": "2.0", "code": "PERMISSION_DENIED", "message": "EGRESS_DENIED", "retryable": False, "details": {"reason": "EGRESS_DENIED"}}
BACKUP_HOST = "backup-store"   # platform 백업 저장소의 서비스 이름(external:backup, RUNTIME R10.1)


def allowed_authorities(egress):
    """CONNECT 의 :authority(host:port) 허용 목록 -> (정확한 문자열 목록, 공인 443 정규식 또는 None)."""
    exact, public = [], None
    for e in egress:
        if e == "external:backup":
            exact.append(f"{BACKUP_HOST}:443")
        elif e == "external:web-push":
            public = r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+:443$"   # 공인 이름의 443: 점 없는 이름(영역 안 서비스 이름)은 해당하지 않는다
        else:
            exact.append(f"{e}:443")
    return sorted(set(exact)), public


DEFAULT_MAX_BODY = 8 * 1024 * 1024   # 계약: Exposure.routes[].max_body_bytes 가 없으면 8MiB(RUNTIME R3.5, 3.4.7)


def glob_regex(path):
    """Exposure 경로 패턴 -> 정규식. 끝의 `/*` 는 그 아래 전부, 가운데 `*` 는 한 구간."""
    out = re.escape(path)
    if path.endswith("/*"):
        out = re.escape(path[:-2]) + "(/.*)?"
    return "^" + out.replace(r"\*", "[^/]+") + "$"


def too_large(limit):
    body = json.dumps({"pipeline_schema_version": "2.0", "code": "INVALID_RECORD", "message": "request body too large", "retryable": False, "details": {"max_body_bytes": limit}}, ensure_ascii=False, separators=(",", ":"))
    return {"direct_response": {"status": 413, "body": {"inline_string": body}}, "response_headers_to_add": [{"header": {"key": "Content-Type", "value": "application/json"}}]}


def ingress_routes(exposure, route_upstreams):
    """들어오는 쪽 경로 규칙: 경로·메서드별 본문 상한(Content-Length 로 앞에서 거절 413)과 상류(upstream_port: 같은 네트워크 공간 loopback 포트). 인증은 platform 공개 입구의 몫이다.
    한계: Content-Length 없는 청크 전송은 이 규칙으로 못 센다(미해결, ADR 0001)."""
    routes = []
    def one(match, limit, cluster):
        routes.append({"match": {**match, "headers": match.get("headers", []) + [{"name": "content-length", "range_match": {"start": limit + 1, "end": 2**62}}]}, **too_large(limit)})
        routes.append({"match": match, "route": {"cluster": cluster, "timeout": "0s", "idle_timeout": "120s"}})
    for r in exposure.get("routes", []):
        if (r.get("auth") or {}).get("kind") == "denied":
            continue
        limit = r.get("max_body_bytes", DEFAULT_MAX_BODY)
        cluster = "port%d" % r["upstream_port"] if r.get("upstream_port") else "area"
        hdr = [{"name": ":method", "string_match": {"safe_regex": {"regex": "^(%s)$" % "|".join(r["methods"])}}}] if r.get("methods") else []
        for path in r["paths"]:
            one({"safe_regex": {"regex": glob_regex(path)}, "headers": hdr}, limit, cluster)
    return routes


def build(exposure, upstream, cert, key, ingress_port, egress_port, route_upstreams=None, sds_path="/etc/envoy/sds.yaml"):
    """route_upstreams: {경로 접두사: host:port}. 영역 안 컴포넌트가 여럿일 때 경로별 상류(가장 긴 접두사 우선). Exposure 스키마에는 경로별 상류 필드가 없어 배치가 준다(변경 요청 후보)."""
    route_upstreams = route_upstreams or {}
    exact, public = allowed_authorities(exposure.get("egress") or [])
    uh, up = upstream.rsplit(":", 1)
    ingress_prefixes = [(pre, "up%d" % i) for i, pre in enumerate(sorted(route_upstreams))]
    denied = json.dumps(DENIED, ensure_ascii=False, separators=(",", ":"))
    allow_routes = [{"match": {"connect_matcher": {}, "headers": [{"name": ":authority", "string_match": {"exact": a}}]},
                     "route": {"cluster": "dfp", "upgrade_configs": [{"upgrade_type": "CONNECT", "connect_config": {}}]}} for a in exact]
    if public:
        allow_routes.append({"match": {"connect_matcher": {}, "headers": [{"name": ":authority", "string_match": {"safe_regex": {"regex": public}}}]},
                             "route": {"cluster": "dfp", "upgrade_configs": [{"upgrade_type": "CONNECT", "connect_config": {}}]}})
    deny_route = {"match": {"prefix": "/"}, "direct_response": {"status": 403, "body": {"inline_string": denied}},
                  "response_headers_to_add": [{"header": {"key": "Content-Type", "value": "application/json"}}]}
    connect_deny = {"match": {"connect_matcher": {}}, "direct_response": {"status": 403, "body": {"inline_string": denied}},
                    "response_headers_to_add": [{"header": {"key": "Content-Type", "value": "application/json"}}]}
    dfp_cache = {"name": "dfp_cache", "dns_lookup_family": "V4_ONLY", "dns_cache_circuit_breaker": {"max_pending_requests": 256}}
    cfg = {
        "node": {"id": "area-gateway", "cluster": "area-gateway"},   # SDS(파일) 설정에 필요하다
        "static_resources": {
            "listeners": [
                {"name": "ingress", "address": {"socket_address": {"address": "0.0.0.0", "port_value": ingress_port}},
                 "filter_chains": [{
                     "transport_socket": {"name": "envoy.transport_sockets.tls", "typed_config": {
                         "@type": "type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext",
                         "common_tls_context": {"tls_params": {"tls_minimum_protocol_version": "TLSv1_2"},
                                                "tls_certificate_sds_secret_configs": [{"name": "tls", "sds_config": {"path_config_source": {"path": sds_path, "watched_directory": {"path": "/certs"}}}}]}}},
                     "filters": [{"name": "envoy.filters.network.http_connection_manager", "typed_config": {
                         "@type": "type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager",
                         "stat_prefix": "ingress", "stream_idle_timeout": "0s",
                         "route_config": {"name": "ingress", "virtual_hosts": [{"name": "area", "domains": ["*"], "routes": [
                             *[{"match": {"prefix": pre}, "route": {"cluster": cl, "timeout": "0s", "idle_timeout": "120s"}} for pre, cl in sorted(ingress_prefixes, key=lambda x: -len(x[0]))],
                             *ingress_routes(exposure, route_upstreams),
                             {"match": {"prefix": "/", "headers": [{"name": "content-length", "range_match": {"start": DEFAULT_MAX_BODY + 1, "end": 2**62}}]}, **too_large(DEFAULT_MAX_BODY)},
                             {"match": {"prefix": "/"}, "route": {"cluster": "area", "timeout": "0s", "idle_timeout": "120s"}}]}]},
                         "http_filters": [{"name": "envoy.filters.http.router", "typed_config": {"@type": "type.googleapis.com/envoy.extensions.filters.http.router.v3.Router"}}]}}]}]},
                {"name": "egress", "address": {"socket_address": {"address": "127.0.0.1", "port_value": egress_port}},
                 "filter_chains": [{"filters": [{"name": "envoy.filters.network.http_connection_manager", "typed_config": {
                     "@type": "type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager",
                     "stat_prefix": "egress", "upgrade_configs": [{"upgrade_type": "CONNECT"}], "http2_protocol_options": {"allow_connect": True},
                     "route_config": {"name": "egress", "virtual_hosts": [{"name": "egress", "domains": ["*"], "routes": allow_routes + [connect_deny, deny_route]}]},
                     "http_filters": [
                         {"name": "envoy.filters.http.dynamic_forward_proxy", "typed_config": {
                             "@type": "type.googleapis.com/envoy.extensions.filters.http.dynamic_forward_proxy.v3.FilterConfig", "dns_cache_config": dfp_cache}},
                         {"name": "envoy.filters.http.router", "typed_config": {"@type": "type.googleapis.com/envoy.extensions.filters.http.router.v3.Router"}}]}}]}]}],
            "clusters": [
                {"name": "area", "type": "STRICT_DNS", "connect_timeout": "1s", "load_assignment": {"cluster_name": "area", "endpoints": [{"lb_endpoints": [{"endpoint": {"address": {"socket_address": {"address": uh, "port_value": int(up)}}}}]}]}},
                *[{"name": "up%d" % i, "type": "STRICT_DNS", "connect_timeout": "1s", "load_assignment": {"cluster_name": "up%d" % i, "endpoints": [{"lb_endpoints": [{"endpoint": {"address": {"socket_address": {"address": route_upstreams[pre].rsplit(":", 1)[0], "port_value": int(route_upstreams[pre].rsplit(":", 1)[1])}}}}]}]}} for i, pre in enumerate(sorted(route_upstreams))],
                *[{"name": "port%d" % pt, "type": "STATIC", "connect_timeout": "1s", "load_assignment": {"cluster_name": "port%d" % pt, "endpoints": [{"lb_endpoints": [{"endpoint": {"address": {"socket_address": {"address": "127.0.0.1", "port_value": pt}}}}]}]}} for pt in sorted({r["upstream_port"] for r in exposure.get("routes", []) if r.get("upstream_port")})],
                {"name": "dfp", "lb_policy": "CLUSTER_PROVIDED", "connect_timeout": "5s", "cluster_type": {"name": "envoy.clusters.dynamic_forward_proxy", "typed_config": {
                    "@type": "type.googleapis.com/envoy.extensions.clusters.dynamic_forward_proxy.v3.ClusterConfig", "dns_cache_config": dfp_cache}}}]},
    }
    sds = {"resources": [{"@type": "type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret", "name": "tls", "tls_certificate": {"certificate_chain": {"filename": cert}, "private_key": {"filename": key}}}]}
    return cfg, sds


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--exposure", required=True); ap.add_argument("--upstream", required=True)
    ap.add_argument("--cert", default="/certs/tls.crt"); ap.add_argument("--key", default="/certs/tls.key")
    ap.add_argument("--ingress-port", type=int, default=443); ap.add_argument("--egress-port", type=int, default=3128)
    ap.add_argument("--route-upstream", action="append", default=[], metavar="PREFIX=host:port", help="경로 접두사별 상류(영역 안 컴포넌트가 여럿일 때). 여러 번 줄 수 있다")
    ap.add_argument("--sds-path", default="/etc/envoy/sds.yaml", help="Envoy 가 SDS 파일을 읽는 경로(설정에 들어간다)")
    ap.add_argument("--sds-out", help="SDS 파일을 이 경로에 쓴다(기본: 표준 출력에 설정만)")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9.-]+:\d{1,5}", a.upstream):
        sys.exit("upstream 은 host:port 여야 한다")
    exposure = json.load(open(a.exposure, encoding="utf-8"))
    from boundary_contracts import validator
    errs = list(validator("Exposure").iter_errors(exposure))
    if errs:
        sys.exit("Exposure 선언이 계약을 어겼다: " + errs[0].message[:200])
    ru = {}
    for x in a.route_upstream:
        pre, _, hp = x.partition("=")
        if not pre.startswith("/") or not re.fullmatch(r"[A-Za-z0-9.-]+:\d{1,5}", hp):
            sys.exit("--route-upstream 은 /접두사=host:port 여야 한다: " + x)
        ru[pre] = hp
    cfg, sds = build(exposure, a.upstream, a.cert, a.key, a.ingress_port, a.egress_port, ru, a.sds_path)
    if a.sds_out:
        json.dump(sds, open(a.sds_out, "w"), indent=1)
    json.dump(cfg, sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main(sys.argv[1:])
