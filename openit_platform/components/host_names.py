"""GATEWAY_HOSTS(계약 PublicIngressEnv)에서 CSRF 허용 호스트 이름 목록과 Caddy 사이트 주소 목록을 만든다.
형식 검사는 하지 않는다: 값은 entrypoint 가 계약(envcheck)으로 먼저 검증했다(D117, R7 '낸 값은 받는 쪽이 다시 검증하지 않는다')."""
import re


def parse(raw: str, sites: bool) -> str:
    """포트를 뗀 이름들을 `"a", "b"` 모양(Caddy 식 안 문자열 목록)으로, sites 면 `a:8443, b` 로 정규화해 돌려준다. 계약은 쉼표 앞뒤 공백을 선택으로 두는데 Caddy 는 쉼표 뒤 공백을 요구한다."""
    names, addrs = [], []
    for h in re.split(r"\s*,\s*", raw.strip()):
        addrs.append(h)
        name = h.partition(":")[0]
        if name not in names:
            names.append(name)
    return ", ".join(addrs) if sites else ", ".join('"%s"' % n for n in names)
