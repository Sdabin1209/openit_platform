#!/usr/bin/env bash
# docker 를 부르는 모든 스크립트·시험이 쓰는 환경 한 곳(admin-console/scripts/docker-env.mjs, kiosk-frontend 와 같은 규칙). 사용자 전역 ~/.docker 설정(자격 도우미 credsStore)에 기대지 않게 한다.
# 왜: 이 영역이 받는 이미지는 공개 이미지를 digest 로 고정한 것이라 레지스트리 자격이 필요 없다. 전역 설정의 자격 도우미가 응답하지 않으면 docker build 가 실패한다. 표준 환경 변수 DOCKER_CONFIG 로 리포 안 빈 설정({})을 주면 도우미를 부르지 않는다.
# 왜 DOCKER_HOST: DOCKER_CONFIG 를 바꾸면 사용자의 docker 컨텍스트(다른 소켓·원격 엔진)도 안 보인다. 기본 소켓이 아닐 때만 그 엔드포인트를 DOCKER_HOST 로 넘긴다(docker CLI 에게 묻는다).
# DOCKER_CONFIG 가 이미 주어졌으면 그대로 쓴다. 사용자 ~/.docker 는 이 파일이 읽지도 고치지도 않는다. 설정 폴더는 git 제외 폴더 build/docker-config 다.
# 사용: eval "$(bash scripts/docker-env.sh)"   (export 줄을 출력한다. 값에 비밀 없음)
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -z "${DOCKER_HOST:-}" ]; then
  host=$("${DOCKER:-docker}" context inspect --format '{{.Endpoints.docker.Host}}' 2>/dev/null || true)   # 바꾸기 전의 설정이 가리키는 엔진을 묻는다
  if [ -n "$host" ] && [ "$host" != unix:///var/run/docker.sock ]; then printf "export DOCKER_HOST='%s'\n" "$host"; fi
fi
if [ -z "${DOCKER_CONFIG:-}" ]; then
  mkdir -p "$ROOT/build/docker-config" && printf '{}\n' > "$ROOT/build/docker-config/config.json" && printf "export DOCKER_CONFIG='%s'\n" "$ROOT/build/docker-config"
fi
