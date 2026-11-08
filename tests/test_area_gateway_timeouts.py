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
