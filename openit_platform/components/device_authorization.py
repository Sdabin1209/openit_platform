"""기기 인증 판정: DeviceAllowlist 를 읽어 (CN, 10진 일련번호)가 허용되는지 정한다. 입출력은 값뿐이고 소켓·HTTP 를 모른다.
TLS 가 인증서를 검증하고 이 컴포넌트는 허용 목록만 본다(ADR 0013·0016). 진단에 자격·환자 값을 싣지 않는다."""
from __future__ import annotations

from pathlib import Path

from boundary_contracts import BoundaryError, schema_validator, strict_json, validator

from openit_platform.types.device_auth_request import DeviceAuthRequest


class Authorizer:
    def __init__(self, input_schema: dict):
        # 영역 내부 스키마(DeviceAuthRequest)용 계약 검증기(5.0.1): 형식 검사·비유한 수 검사 포함
        self._input = schema_validator(input_schema)
        self._allowlist = validator("DeviceAllowlist")
        self._device_id = validator(input_schema["properties"]["device_id"]["x-contract"])

    def load_allowlist(self, path: Path) -> dict[str, set[str]]:
        document = strict_json.loads(path.read_text(encoding="utf-8"))   # 계약 JSON 공통 규칙(깊이 64·1 MiB·I-JSON): 허용 목록은 deploy 가 쓴 파일이다
        self._allowlist.validate(document)
        result: dict[str, set[str]] = {}
        for entry in document["devices"]:
            device = entry["device_id"]
            if device in result:
                raise ValueError("duplicate device_id")   # 스키마로 표현할 수 없는 유일성: 계약 DeviceAllowlist 설명이 소비자 강제로 정했다
            result[device] = set(entry["serials"])
        return result

    def authorize(self, path: Path, device: str, decimal_serial: str) -> tuple[int, dict, bytes]:
        try:
            allowed = self.load_allowlist(path)
        except Exception:
            # 스키마 예외와 읽기 실패를 구분하지 않는다. 오류 때 이전에 허용한 인증서를 남기지 않는다(fail-closed).
            return failure(503, "UNAVAILABLE", "device authorization unavailable")
        try:
            # 인증서 일련번호는 DER 양수 정수 최대 20옥텟이라 10진 48자리면 충분하다: 변환 전에 길이를 막는다.
            request: DeviceAuthRequest = {"device_id": device, "serial_decimal": decimal_serial}
            self._input.validate(request)
            self._device_id.validate(device)
            serial = format(int(decimal_serial), "x")
            self._allowlist.validate({"schema_version": 1, "devices": [{"device_id": device, "serials": [serial]}]})
        except Exception:
            return failure(403, "PERMISSION_DENIED", "device authentication failed")
        if serial not in allowed.get(device, set()):
            return failure(403, "PERMISSION_DENIED", "device authentication failed")
        return 204, {"X-Openit-Device": device, "Cache-Control": "no-store"}, b""

    def ready(self, path: Path) -> tuple[int, dict, bytes]:
        import json
        try:
            self.load_allowlist(path)
            record = {"status": "ready"}
            validator("HealthStatus").validate(record)
            return 200, {"Content-Type": "application/json", "Cache-Control": "no-store"}, json.dumps(record).encode()
        except Exception:
            return failure(503, "UNAVAILABLE", "device authorization unavailable")


def failure(status: int, code: str, message: str) -> tuple[int, dict, bytes]:
    import json
    record = BoundaryError(code, message).to_record()
    body = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json", "Cache-Control": "no-store"}
    if status == 503:
        headers["Retry-After"] = "5"
    return status, headers, body
