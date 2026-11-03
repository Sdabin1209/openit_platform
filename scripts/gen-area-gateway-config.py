#!/usr/bin/env python3
"""영역 게이트웨이 설정 생성기(platform 영역, ADR 0001). 영역의 Exposure 선언(라벨 io.openit.exposure 의 내용)과 배치 값에서 Envoy 설정을 만든다.
들어오는 쪽: 서비스 이름 인증서로 TLS 를 끝내고 영역 안 컴포넌트(upstream)로 넘긴다(RUNTIME R1.1, CONVENTIONS 13절). 인증서·키 파일이 바뀌면 Envoy 가 SDS 파일 감시로 다시 읽는다(재시작·reload 불필요).
나가는 쪽: 영역 안 컴포넌트의 영역 밖 호출은 HTTP CONNECT 터널(RFC 9110 9.3.6)로 나간다. Exposure.egress 에 선언한 상대의 `<이름>:443` 에만 터널을 열고 그 밖은 403 BoundaryError(PERMISSION_DENIED, details.reason=EGRESS_DENIED)로 거절한다(R1.8·R6.2).
사용: gen-area-gateway-config.py --exposure <Exposure JSON 파일> --upstream <host:port> [--cert F --key F] [--ingress-port 443 --egress-port 3128] > envoy.yaml
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


def build(exposure, upstream, cert, key, ingress_port, egress_port):
    exact, public = allowed_authorities(exposure.get("egress") or [])
    uh, up = upstream.rsplit(":", 1)
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
                                                "tls_certificate_sds_secret_configs": [{"name": "tls", "sds_config": {"path_config_source": {"path": "/etc/envoy/sds.yaml", "watched_directory": {"path": "/certs"}}}}]}}},
                     "filters": [{"name": "envoy.filters.network.http_connection_manager", "typed_config": {
                         "@type": "type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager",
                         "stat_prefix": "ingress", "stream_idle_timeout": "0s",
                         "route_config": {"name": "ingress", "virtual_hosts": [{"name": "area", "domains": ["*"], "routes": [
                             {"match": {"prefix": "/"}, "route": {"cluster": "area", "timeout": "0s", "idle_timeout": "120s"}}]}]},
                         "http_filters": [{"name": "envoy.filters.http.router", "typed_config": {"@type": "type.googleapis.com/envoy.extensions.filters.http.router.v3.Router"}}]}}]}]},
                {"name": "egress", "address": {"socket_address": {"address": "0.0.0.0", "port_value": egress_port}},
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
    ap.add_argument("--sds-out", help="SDS 파일을 이 경로에 쓴다(기본: 표준 출력에 설정만)")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9.-]+:\d{1,5}", a.upstream):
        sys.exit("upstream 은 host:port 여야 한다")
    exposure = json.load(open(a.exposure, encoding="utf-8"))
    from boundary_contracts import validator
    errs = list(validator("Exposure").iter_errors(exposure))
    if errs:
        sys.exit("Exposure 선언이 계약을 어겼다: " + errs[0].message[:200])
    cfg, sds = build(exposure, a.upstream, a.cert, a.key, a.ingress_port, a.egress_port)
    if a.sds_out:
        json.dump(sds, open(a.sds_out, "w"), indent=1)
    json.dump(cfg, sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main(sys.argv[1:])
