"""Exposure.auth is the public entrance policy; peer calls still reach the service token validator."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def generator():
    spec = importlib.util.spec_from_file_location('area_config', ROOT / 'area-gateway/gen-area-gateway-config.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_denial_does_not_remove_internal_service_route():
    exposure = {'service': 'dataset-store', 'routes': [{'paths': ['/v1/datasets', '/v1/datasets/*'], 'auth': {'kind': 'denied'}, 'max_body_bytes': 1073741824}]}
    routes = generator().ingress_routes(exposure, {})
    forwarded = [route for route in routes if 'route' in route]
    assert len(forwarded) == 2
    assert all(route['route']['cluster'] == 'area_dial1000' for route in forwarded)
    assert len([route for route in routes if route.get('direct_response', {}).get('status') == 413]) == 2


def test_public_entry_still_omits_denied_internal_route():
    spec = importlib.util.spec_from_file_location('public_routes', ROOT / 'ingress/gen-ingress-routes.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    declaration = {'service':'dataset-store','routes':[{'paths':['/v1/datasets','/v1/datasets/*'],'auth':{'kind':'denied'}}]}
    assert '/v1/datasets' not in module.gen([declaration])
