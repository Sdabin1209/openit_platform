#!/usr/bin/env python3
"""GATEWAY_HOSTS(계약 PublicIngressEnv)에서 CSRF 허용 호스트 이름 목록을 만든다: 포트를 뗀 이름들을 `"a", "b"` 모양(Caddy 식 안의 문자열 목록)으로 낸다. 파생 값이라 deploy 가 주지 않는다. 사용: gen-host-names.py '<GATEWAY_HOSTS>'"""
import re, sys
names = []
for h in re.split(r"\s*,\s*", sys.argv[1].strip()):
    name = h.partition(":")[0]
    if not re.fullmatch(r"[A-Za-z0-9.-]+", name):
        sys.exit("GATEWAY_HOSTS 항목의 호스트 이름 규칙 위반(영문·숫자·.·- 만)")
    if name not in names:
        names.append(name)
print(", ".join('"%s"' % n for n in names))
