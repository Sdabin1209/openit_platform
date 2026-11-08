#!/usr/bin/env python3
"""영역 내부 스키마(ingress/schemas/*.json)에서 openit_platform/types/ 의 타입을 만든다(DESIGN.md 6절 5항). 사용: gen-types.py [--check]
--check 는 파일을 쓰지 않고 지금 있는 것과 같은지만 본다(rc 0 같음, 1 다름). 계약 스키마의 타입은 만들지 않는다: 계약 칸은 x-contract 로 위임한다."""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def render(schema: dict) -> str:
    name = schema["title"]
    lines = ["# 생성됨: scripts/gen-types.py 가 ingress/schemas/%s.json 에서 만든다. 손으로 고치지 않는다." % name,
             "from __future__ import annotations", "", "from typing import TypedDict", "", "",
             "class %s(TypedDict):" % name, '    """%s"""' % schema["description"]]
    for prop in schema["properties"]:   # 이 영역의 내부 스키마 속성은 모두 문자열이다(x-contract 위임 칸도 계약이 문자열 ID 로 정의한다)
        lines.append("    %s: str" % prop)
    return "\n".join(lines) + "\n"


def main(argv):
    bad = 0
    for path in sorted((ROOT / "ingress/schemas").glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        out = ROOT / "openit_platform/types" / (__import__("re").sub(r"(?<!^)(?=[A-Z])", "_", schema["title"]).lower() + ".py")
        text = render(schema)
        if "--check" in argv:
            if not out.exists() or out.read_text(encoding="utf-8") != text:
                print("낡음: %s" % out.relative_to(ROOT), file=sys.stderr); bad = 1
        else:
            out.write_text(text, encoding="utf-8")
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
