#!/usr/bin/env bash
# 샌드박스 도커 이미지를 만든다. (처음에는 10~20분 걸리고 용량이 수 GB 입니다)
set -euo pipefail
cd "$(dirname "$0")/.."
IMAGE="${DOCKER_IMAGE:-research-lab-sandbox:latest}"
if ! docker info >/dev/null 2>&1; then
  echo "도커가 꺼져 있습니다. 먼저 'colima start --cpu 6 --memory 12' 를 실행하세요." >&2
  exit 1
fi
docker build -t "$IMAGE" docker/
echo "완료: $IMAGE"
