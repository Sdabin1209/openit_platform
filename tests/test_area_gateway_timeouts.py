"""Exposure timing budgets apply to each area route, including placement overrides."""
import pytest
from test_exposure_gateway_scopes import generator


@pytest.mark.parametrize('service,header', [('release-gate', '178.000s'), ('question-authoring', '118.000s'),
                                         ('ops-feedback', '58.000s'), ('survey-service', '53.000s')])
def test_chain_defaults_cover_declared_placement_and_fallback_routes(service, header):
    cfg, _ = generator().build({'service': service, 'routes': [{'paths': ['/v1/*'], 'auth': {'kind': 'none'}}]},
                              '127.0.0.1:8080', '/certs/tls.crt', '/certs/tls.key', 443, 3128,
                              {'/v1/special': '127.0.0.1:9090'})
    routes = cfg['static_resources']['listeners'][0]['filter_chains'][0]['filters'][0]['typed_config']['route_config']['virtual_hosts'][0]['routes']
    forwarded = [r['route'] for r in routes if 'route' in r]
    assert len(forwarded) == 4
    for action in forwarded:
        assert action['timeout'] == '0s'  # response body/SSE is not a header wait
        assert action['idle_timeout'] == '0s'  # no hidden 120s cap
        assert action['retry_policy'] == {'num_retries': 0, 'per_try_timeout': header}


def test_explicit_millisecond_budgets_and_different_dial_values_are_preserved():
    exp = {'service': 'release-gate', 'routes': [
        {'paths': ['/fast'], 'auth': {'kind': 'none'}, 'timeouts_ms': {'dial': 250, 'response_header': 750, 'read': 1500}},
        {'paths': ['/slow'], 'auth': {'kind': 'none'}, 'timeouts_ms': {'dial': 1600, 'response_header': 180000}}]}
    cfg, _ = generator().build(exp, '127.0.0.1:8080', 'c', 'k', 443, 3128)
    clusters = {c['name']: c for c in cfg['static_resources']['clusters']}
    assert clusters['area_dial250']['connect_timeout'] == '0.250s'
    assert clusters['area_dial1600']['connect_timeout'] == '1.600s'
    routes = generator().ingress_routes(exp, {})
    fast, slow = [r['route'] for r in routes if 'route' in r]
    assert fast['retry_policy']['per_try_timeout'] == '0.499s'
    assert fast['idle_timeout'] == '1.500s'
    assert slow['retry_policy']['per_try_timeout'] == '177.400s'


def test_placement_preserves_declared_timeout_and_body_limit_before_fallback():
    exp = {'service': 'release-gate', 'routes': [{'paths': ['/v1/*'], 'methods': ['POST'], 'auth': {'kind': 'none'},
           'max_body_bytes': 100, 'timeouts_ms': {'dial': 250, 'response_header': 180000}}]}
    routes = generator().ingress_routes(exp, {'/v1/job': '127.0.0.1:9090'})
    assert routes[0]['direct_response']['status'] == 413
    assert routes[0]['match']['headers'][-1]['range_match']['start'] == 101
    placed = routes[1]
    assert placed['route']['cluster'] == 'up0_dial250'
    assert placed['route']['retry_policy']['per_try_timeout'] == '178.750s'
    assert placed['match']['headers'][-1] == {'name': ':path', 'string_match': {'prefix': '/v1/job'}}
    assert routes[3]['route']['cluster'] == 'area_dial250'


@pytest.mark.parametrize('timeouts', [{'read': 100}, {'read': 100, 'response_header': 200}])
def test_invalid_read_header_order_is_rejected(timeouts):
    with pytest.raises(ValueError, match='read must be >= response_header'):
        generator().route_action({'service': 'release-gate'}, {'timeouts_ms': timeouts}, 'area')


def test_override_headers_are_removed_before_router_consumes_them():
    cfg, _ = generator().build({'service': 'release-gate', 'routes': []}, '127.0.0.1:8080', 'c', 'k', 443, 3128)
    filters = cfg['static_resources']['listeners'][0]['filter_chains'][0]['filters'][0]['typed_config']['http_filters']
    assert filters[0]['name'] == 'envoy.filters.http.header_mutation'
    removed = {m['remove'] for m in filters[0]['typed_config']['mutations']['request_mutations']}
    assert {'x-envoy-upstream-rq-timeout-ms', 'x-envoy-upstream-rq-per-try-timeout-ms',
            'x-envoy-max-retries', 'x-envoy-upstream-rq-timeout-alt-response'} <= removed
    assert filters[-1]['name'] == 'envoy.filters.http.router'


@pytest.mark.parametrize('header,dial,inner', [(3000, 1000, 1000), (2999, 1000, 1998), (2000, 1000, 999), (200, 10, 189), (1002, 1000, 1)])
def test_inner_connect_and_header_are_strictly_inside_public_header_budget(header, dial, inner):
    action = generator().route_action({'service': 'release-gate'},
        {'timeouts_ms': {'dial': dial, 'response_header': header}}, 'area')
    assert action['retry_policy']['per_try_timeout'] == generator().duration(inner)
    assert dial + inner < header


@pytest.mark.parametrize('header,dial', [(999, 1000), (1000, 1000), (1001, 1000)])
def test_no_representable_inner_budget_is_rejected(header, dial):
    with pytest.raises(ValueError, match='response_header must exceed dial'):
        generator().route_action({'service': 'release-gate'},
            {'timeouts_ms': {'dial': dial, 'response_header': header}}, 'area')


def hcm(cfg):
    return cfg['static_resources']['listeners'][0]['filter_chains'][0]['filters'][0]['typed_config']


def test_route_with_read_has_no_total_timeout_header_wait_is_per_try_and_read_is_the_idle_limit():
    # 옛 실시간 시험(스트림 0.15s 통과·0.8s 끊김)이 지키려던 설정. 생성기는 streaming 플래그를 쓰지 않고 read 유무로만 갈린다.
    # 헤더 대기는 per_try_timeout 으로만, 전체 응답 timeout 은 0(무제한), read 는 idle_timeout.
    # response_header 를 100+11 로 준 이유: 내부 헤더 대기 = response_header - dial(10) - 여유(차이가 2초 미만이면 1ms) 이므로 111 - 10 - 1 = 100ms 가 나온다.
    exp = {'service': 'survey-service', 'routes': [{'paths': ['/*'], 'auth': {'kind': 'none'}, 'streaming': True,
           'timeouts_ms': {'dial': 10, 'response_header': 100 + 11, 'read': 400}}]}
    action = [r['route'] for r in generator().ingress_routes(exp, {}) if 'route' in r][0]
    assert action['timeout'] == '0s'
    assert action['idle_timeout'] == '0.400s'
    assert action['retry_policy'] == {'num_retries': 0, 'per_try_timeout': '0.100s'}


def test_release_gate_default_header_wait_outlasts_old_120s_cutoff_and_the_170s_server_cap():
    # 옛 실시간 시험(121초 응답 생존)이 지키려던 설정: 경로 단계(기본 헤더 대기 > 170초, timeout·idle 0)와
    # HCM 단계(stream_idle_timeout 0s: 값이 없으면 Envoy 기본 5분, 120s 로 바꾸면 121초 응답이 끊긴다)를 모두 본다.
    exp = {'service': 'release-gate', 'routes': [{'paths': ['/*'], 'auth': {'kind': 'none'}}]}
    action = [r['route'] for r in generator().ingress_routes(exp, {}) if 'route' in r][0]
    per_try = float(action['retry_policy']['per_try_timeout'].rstrip('s'))
    assert per_try > 170 and per_try > 120
    assert action['idle_timeout'] == '0s' and action['timeout'] == '0s'
    cfg, _ = generator().build(exp, '127.0.0.1:8080', 'c', 'k', 443, 3128)
    assert hcm(cfg)['stream_idle_timeout'] == '0s'
