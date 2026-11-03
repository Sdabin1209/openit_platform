#!/usr/bin/env bash
# 영역 환경 준비의 정본(platform). 설치는 requirements.txt 의 핀으로만 한다. 인자 없음, 멱등, 비밀 없음.
# 결과: 표준 출력 마지막 줄에 계약 SetupEnvReport JSON 한 줄. 진행 기록은 표준 오류로 낸다.
# 원격 동결 동안 계약 패키지 태그는 로컬 미러로 받는다: 호출자가 GIT_CONFIG_GLOBAL 을 준다(구조 점검 S14). 이 스크립트는 경로를 모른다.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
start=$SECONDS
emit() { printf '{"area":"platform","status":"%s","exit_code":%d,"seconds":%d,"environment":{"kind":"python-venv","path":".venv","test_command":[".venv/bin/python","-m","pytest","-q"]}}\n' "$1" "$2" "$((SECONDS - start))"; }
trap 'rc=$?; if [ "$rc" -eq 0 ]; then emit ok 0; else emit fail "$rc"; fi' EXIT
[ -d .venv ] || python3 -m venv .venv >&2
.venv/bin/python -m pip install -q --disable-pip-version-check --upgrade -r requirements.txt >&2
.venv/bin/python -m pip install -q --disable-pip-version-check -e . >&2
.venv/bin/python -m pip check >&2 || { echo "setup-env: 의존 충돌(pip check 실패)" >&2; exit 1; }
echo "setup-env: 완료" >&2
