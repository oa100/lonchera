#!/usr/bin/env bash
set -euo pipefail
IMAGE_NAME="lonchera"

echo "Stopping any existing container named ${IMAGE_NAME}"
docker stop "${IMAGE_NAME}" || true

docker rm "${IMAGE_NAME}" 2>/dev/null || true