"""Exposure timing budgets apply to each area route, including placement overrides."""
import pytest
from test_exposure_gateway_scopes import generator


@pytest.mark.parametrize('service,header', [('release-gate', '180.000s'), ('question-authoring', '120.000s'),
                                         ('ops-feedback', '60.000s'), ('survey-service', '55.000s')])
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
    assert fast['retry_policy']['per_try_timeout'] == '0.750s'
    assert fast['idle_timeout'] == '1.500s'
    assert slow['retry_policy']['per_try_timeout'] == '180.000s'


def test_placement_preserves_declared_timeout_and_body_limit_before_fallback():
    exp = {'service': 'release-gate', 'routes': [{'paths': ['/v1/*'], 'methods': ['POST'], 'auth': {'kind': 'none'},
           'max_body_bytes': 100, 'timeouts_ms': {'dial': 250, 'response_header': 180000}}]}
    routes = generator().ingress_routes(exp, {'/v1/job': '127.0.0.1:9090'})
    assert routes[0]['direct_response']['status'] == 413
    assert routes[0]['match']['headers'][-1]['range_match']['start'] == 101
    placed = routes[1]
    assert placed['route']['cluster'] == 'up0_dial250'
    assert placed['route']['retry_policy']['per_try_timeout'] == '180.000s'
    assert placed['match']['headers'][-1] == {'name': ':path', 'string_match': {'prefix': '/v1/job'}}
    assert routes[3]['route']['cluster'] == 'area_dial250'
