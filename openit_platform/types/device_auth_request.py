# 생성됨: scripts/gen-types.py 가 ingress/schemas/DeviceAuthRequest.json 에서 만든다. 손으로 고치지 않는다.
from __future__ import annotations

from typing import TypedDict


class DeviceAuthRequest(TypedDict):
    """영역 안 Caddy→기기 인증 확인기 입력. TLS 속성에서 얻은 CN과 10진 일련번호이며 클라이언트가 보낸 헤더는 Caddy가 덮어쓴다."""
    device_id: str
    serial_decimal: str
