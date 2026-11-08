"""기기 ID 정규식을 계약 DeviceAllowlist 의 device_id 패턴에서 꺼내 앵커 없는 식으로 만든다(Caddy header_regexp 와 device-pki.sh 가 쓴다).
왜: 같은 패턴 사본을 Caddyfile·셸에 박으면 계약이 바뀔 때 어긋난다(D117). 끝 고정 `$(?![\\s\\S])` 는 ECMAScript 문법이라 RE2(Caddy)에 없다: 쓰는 곳이 앞뒤를 직접 고정한다."""
from boundary_contracts import load_schema

SUFFIX = "$(?![\\s\\S])"


def device_id_regex() -> str:
    pattern = load_schema("DeviceAllowlist")["properties"]["devices"]["items"]["properties"]["device_id"]["pattern"]
    if not (pattern.startswith("^") and pattern.endswith(SUFFIX)):
        raise SystemExit("device_id 패턴의 모양이 바뀌었다(^…$(?![\\s\\S])): 이 변환을 다시 본다")
    return pattern[1:-len(SUFFIX)]
