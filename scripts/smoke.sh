#!/usr/bin/env bash
# D22 스모크 한 번에: 변형(area-gateway, public-ingress, monitoring, backup-store, step-ca)마다 빌드 -> 실행 -> 상태 확인 -> 비루트·라벨. 종료 코드 0 = 통과.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -x "$ROOT/.venv/bin/python" ] || bash "$ROOT/scripts/setup-env.sh" >/dev/null
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/smoke.py"
