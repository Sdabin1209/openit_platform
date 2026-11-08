#!/usr/bin/env python3
"""GATEWAY_HOSTS(계약 PublicIngressEnv)에서 CSRF 허용 호스트 이름 목록을 만든다: 포트를 뗀 이름들을 `"a", "b"` 모양(Caddy 식 안의 문자열 목록)으로 낸다. 파생 값이라 deploy 가 주지 않는다. --sites 를 주면 Caddy 사이트 주소 목록(`a:8443, b`)으로 정규화해 낸다: 계약은 쉼표 앞뒤 공백을 선택으로 두는데 Caddy 는 쉼표 뒤 공백을 요구한다.
사용: gen-host-names.py [--sites] '<GATEWAY_HOSTS>'"""
import re, sys
sites = len(sys.argv) > 2 and sys.argv[1] == "--sites"
raw = sys.argv[-1]
names, addrs = [], []
# 형식 검사는 하지 않는다: 값은 entrypoint 가 계약 PublicIngressEnv(envcheck)로 먼저 검증했다(D117, R7 '낸 값은 받는 쪽이 다시 검증하지 않는다'). 여기서는 나누기만 한다
for h in re.split(r"\s*,\s*", raw.strip()):
    addrs.append(h)
    name = h.partition(":")[0]
    if name not in names:
        names.append(name)
print(", ".join(addrs) if sites else ", ".join('"%s"' % n for n in names))
