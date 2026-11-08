#!/usr/bin/env bash
# common/ 의 Go 시험(envcheck)을 도커의 Go 빌더 이미지로 돌린다(호스트에 go 가 없어도 된다). 종료 코드 0 = 통과.
# 왜 이 이미지: ingress/Dockerfile 의 ARG GO_BUILDER 와 같은 digest 라 이미지의 Go 빌드와 같은 툴체인이다(digest 고정, 워크스페이스 규칙). 그 ARG 가 정본이라 여기서 읽는다.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
eval "$(bash "$ROOT/scripts/docker-env.sh")"   # 사용자 전역 ~/.docker 설정에 기대지 않는다
IMG=$(sed -n 's/^ARG GO_BUILDER=//p' "$ROOT/ingress/Dockerfile")
[ -n "$IMG" ] || { echo "go-test: ingress/Dockerfile 에서 GO_BUILDER 를 읽지 못했다" >&2; exit 1; }
mkdir -p "$ROOT/build/gocache"   # build/ 는 git 제외
exec docker run --rm -v "$ROOT/common:/src:ro" -v "$ROOT/build/gocache:/gc" -e GOCACHE=/gc/c -e GOPATH=/gc/p -e GOFLAGS=-mod=mod -w /src "$IMG" go test ./...
