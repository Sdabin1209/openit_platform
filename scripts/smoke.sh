#!/usr/bin/env bash
# D22 스모크 한 번에: 변형(area-gateway, public-ingress, monitoring, backup-store, step-ca)마다 빌드 -> 실행 -> 상태 확인 -> 비루트·라벨. 종료 코드 0 = 통과.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -x "$ROOT/.venv/bin/python" ] || bash "$ROOT/scripts/setup-env.sh" >/dev/null
# R9.1: 상속 환경을 통째로 넘기지 않는다. 시험이 쓰는 이름만(docker 설정·git 미러·KEEP_DIR 등)
exec env -i PATH="$PATH" HOME="$HOME" ${LANG:+LANG="$LANG"} ${TMPDIR:+TMPDIR="$TMPDIR"} ${DOCKER_CONFIG:+DOCKER_CONFIG="$DOCKER_CONFIG"} ${DOCKER_HOST:+DOCKER_HOST="$DOCKER_HOST"} ${DOCKER:+DOCKER="$DOCKER"} ${KEEP_DIR:+KEEP_DIR="$KEEP_DIR"} ${GIT_CONFIG_GLOBAL:+GIT_CONFIG_GLOBAL="$GIT_CONFIG_GLOBAL"} ${SSH_AUTH_SOCK:+SSH_AUTH_SOCK="$SSH_AUTH_SOCK"} "$ROOT/.venv/bin/python" "$ROOT/scripts/smoke.py"
