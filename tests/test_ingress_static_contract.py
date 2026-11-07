"""Collected replacements for the retired ingress header and health checks."""
import importlib.util
import json
from pathlib import Path
import re

from boundary_contracts import load_schema, validator
from jsonschema import Draft202012Validator
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def blocks(text, prefix):
    lines = text.splitlines()
    found = []
    for index, line in enumerate(lines):
        if not line.strip().startswith(prefix):
            continue
        depth, body = 1, []
        for nested in lines[index + 1:]:
            code = nested.split('#', 1)[0].strip()
            depth += int(code.endswith(' {')) - int(code == '}')
            if depth == 0:
                break
            body.append(code)
        assert depth == 0, 'unclosed Caddy block'
        found.append('\n'.join(body))
    return found


def generated():
    spec = importlib.util.spec_from_file_location('public_routes', ROOT / 'ingress/gen-ingress-routes.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    exposures = [json.loads(p.read_text()) for p in sorted((ROOT / 'ingress/tests/exposures').glob('*.json'))]
    return module.gen(exposures)


def check_identity_headers(text):
    proxies = blocks(text, 'reverse_proxy https://')
    assert proxies, 'no proxies checked'
    sets = strips = 0
    for body in proxies:
        if 'header_up X-Openit-User "' in body:
            assert 'header_up X-Openit-Roles "{http.request.header.X-Auth-Request-Groups}"' in body
            sets += 1
        else:
            assert 'header_up -X-Openit-User' in body
            assert 'header_up -X-Openit-Roles' in body
            strips += 1
    return sets, strips


def test_every_generated_and_static_proxy_handles_user_and_roles_together():
    sets, strips = check_identity_headers(generated())
    assert sets > 0 and strips > 0, 'both authenticated and anonymous routes must be covered'
    check_identity_headers((ROOT / 'ingress/config/Caddyfile').read_text())


@pytest.mark.parametrize('line', [
    '\theader_up X-Openit-Roles "{http.request.header.X-Auth-Request-Groups}"',
    '\theader_up -X-Openit-Roles',
])
def test_missing_roles_header_handling_is_detected(line):
    text = generated()
    assert line in text
    with pytest.raises(AssertionError):
        check_identity_headers(text.replace(line, '', 1))


def test_retired_qa_user_role_map_is_rejected_by_its_owner_contract():
    # QA configuration belongs to its area: inspect the installed contract,
    # rather than nonexistent platform copies or a neighbour working tree.
    names = load_schema('QuestionAuthoringEnv')['propertyNames']
    check = Draft202012Validator({'type': 'object', 'propertyNames': names})
    assert check.is_valid({'QA_HOST': '127.0.0.1'})
    assert not check.is_valid({'QA_USER_ROLES': '{}'})


def check_health_bodies(text):
    health = blocks(text, 'handle /healthz {')
    assert len(health) == 2, 'HTTP and HTTPS health endpoints must be checked'
    for block in health:
        assert 'header Content-Type application/json' in block
        outputs = re.findall(r'respond `([^`]+)` 200', block)
        assert len(outputs) == 1
        body = json.loads(outputs[0])
        assert validator('HealthStatus').is_valid(body)
        assert body == {'status': 'ok'}
    ready = blocks(text, 'handle /readyz {')
    assert len(ready) == 1
    outputs = re.findall(r'respond `([^`]+)` (200|\{rp.status_code\})', ready[0])
    assert len(outputs) == 2
    for raw, status in outputs:
        body = json.loads(raw)
        assert validator('HealthStatus').is_valid(body)
        assert body == {'status': 'ready' if status == '200' else 'not_ready'}
    assert ready[0].count('header Content-Type application/json') == 2


def test_http_and_https_health_and_readiness_bodies_follow_the_contract():
    check_health_bodies((ROOT / 'ingress/config/Caddyfile').read_text())


@pytest.mark.parametrize('before,after', [
    ('{"status":"ok"}', 'ok'),
    ('{"status":"ready"}', '{"ready":true}'),
    ('{"status":"not_ready"}', '{"status":"ok"}'),
])
def test_wrong_health_or_readiness_body_is_detected(before, after):
    text = (ROOT / 'ingress/config/Caddyfile').read_text()
    needle = 'respond `' + before + '`'
    assert needle in text
    with pytest.raises((AssertionError, ValueError)):
        check_health_bodies(text.replace(needle, 'respond `' + after + '`', 1))


def test_owned_monitoring_probes_require_a_nonempty_status_field():
    template = (ROOT / 'monitoring/config/blackbox.yml.tmpl').read_text()
    modules = yaml.safe_load(template.replace('@ROOT_CA@', '/test/root-ca.crt'))['modules']
    for name in ('readyz', 'public_healthz'):
        patterns = modules[name]['http']['fail_if_body_not_matches_regexp']
        assert patterns
        assert all(re.search(p, '{"status":"ready"}') for p in patterns)
        for wrong in ('', 'ok', '{}', '{"status":""}'):
            assert any(not re.search(p, wrong) for p in patterns), (name, wrong)
