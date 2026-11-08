"""조립: 영역 내부 스키마 파일을 읽어 device_authorization 컴포넌트를 만들고, 진입점(HTTP 서버)이 쓸 함수로 내놓는다."""
import json
from pathlib import Path

from openit_platform.components.device_authorization import Authorizer, failure


def build(schema_path: Path) -> Authorizer:
    return Authorizer(json.loads(Path(schema_path).read_text(encoding="utf-8")))


__all__ = ["build", "failure"]
