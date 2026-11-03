#!/usr/bin/env bash
# 계약 소스를 requirements.txt 의 고정 태그로 받아 경로를 출력한다(BuildImageRequest.dependency_sources.boundary 용).
# 왜: 이웃 리포의 작업 트리 상태에 기대면 clone 마다 버전이 어긋난다(헤드 재현: 새 clone 에서 v3.4.6 != v3.4.8). 사용: fetch-boundary-src.sh <빈 폴더>
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd); D=${1:?빈 폴더}
TAG=$(sed -n 's#^boundary-contracts @ .*@\(v[0-9.]*\)$#\1#p' "$ROOT/requirements.txt")
[ -n "$TAG" ] || { echo "requirements.txt 에서 계약 태그를 읽지 못했다" >&2; exit 1; }
# 원격 동결 동안은 워크스페이스의 로컬 미러 설정을 쓴다(S14). 환경에 GIT_CONFIG_GLOBAL 이 있으면 그것을 따른다
: "${GIT_CONFIG_GLOBAL:=$ROOT/../head/shared/gitconfig-local-mirrors}"; [ -r "$GIT_CONFIG_GLOBAL" ] || unset GIT_CONFIG_GLOBAL; export GIT_CONFIG_GLOBAL 2>/dev/null || true
git clone -q --branch "$TAG" --depth 1 ssh://git@github.com/Sdabin1209/openit_boundary-contracts.git "$D" >&2
echo "$D"
