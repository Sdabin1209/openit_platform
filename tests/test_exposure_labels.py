"""identity·identity-proxy 이미지의 io.openit.exposure 라벨(계약 Exposure)을 계약 validator 로 검증한다(다른 영역 서비스와 같은 방식, deploy 가 라벨에서 영역 게이트웨이·공개 입구 선언을 만든다).
라벨의 정본은 identity/exposure-<서비스>.json 이고 공개 입구 시험 입력(ingress/tests/exposures/)의 사본과 같아야 한다. 변이: 라벨이 없거나 깨지면 검증이 실패한다."""
import json, pathlib
import pytest
from boundary_contracts import validator
from ops_common import ROOT, build, sh

pytestmark = pytest.mark.usefixtures("docker_required")   # Docker 없으면 실패(ADR 0019)
SERVICES = {"identity": "identity", "identity-proxy": "identity-proxy"}


def exposure_of(labels, service):
    """라벨에서 노출 선언을 꺼내 계약 Exposure 로 검증한다. 어기면 AssertionError."""
    raw = labels.get("io.openit.exposure")
    assert raw, "라벨 io.openit.exposure 가 없다"
    d = json.loads(raw)
    errs = list(validator("Exposure").iter_errors(d))
    assert not errs, errs[0].message
    assert d["service"] == service, "service 가 게시 이름과 다르다"
    return d


@pytest.fixture(scope="module")
def labels():
    out, tags = {}, []
    try:
        for variant in SERVICES:
            t = f"platform-exp-{variant}:t"
            tags.append(t); build(variant, t)
            out[variant] = json.loads(sh("docker", "image", "inspect", t).stdout)[0]["Config"]["Labels"]
        yield out
    finally:
        for t in tags: sh("docker", "rmi", t, check=False)


@pytest.mark.parametrize("variant", list(SERVICES))
def test_label_is_a_valid_exposure_and_equals_the_canonical_file(labels, variant):
    d = exposure_of(labels[variant], SERVICES[variant])
    assert d == json.loads((ROOT / f"identity/exposure-{variant}.json").read_text(encoding="utf-8"))
    # 공개 입구 시험 입력의 사본이 정본과 같다(어긋나면 시험이 낡은 선언으로 돈다)
    assert d == json.loads((ROOT / f"ingress/tests/exposures/{variant}.json").read_text(encoding="utf-8"))


def test_identity_proxy_declares_its_outgoing_call_to_identity(labels):
    assert exposure_of(labels["identity-proxy"], "identity-proxy")["egress"] == ["identity"]   # OIDC 교환·키 조회는 identity 로 간다(identity-entry proxy)
    assert exposure_of(labels["identity"], "identity")["egress"] == []   # DB 는 프로토콜이 HTTP 가 아니라 영역 게이트웨이 출구를 거치지 않는다


def test_mutation_missing_or_broken_label_fails_validation(labels):
    stripped = {k: v for k, v in labels["identity"].items() if k != "io.openit.exposure"}
    with pytest.raises(AssertionError):
        exposure_of(stripped, "identity")
    with pytest.raises((AssertionError, ValueError)):
        exposure_of({"io.openit.exposure": '{"service": "identity"}'}, "identity")   # routes 없음 -> 계약 위반
    with pytest.raises(AssertionError):
        exposure_of(labels["identity"], "identity-proxy")   # 다른 서비스 이름
