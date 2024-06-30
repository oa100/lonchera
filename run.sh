#!/usr/bin/env bash
set -euo pipefail

# Generate version based on current date and time
VERSION=$(date +"%Y%m%d_%H%M")

# Name of the Docker image
IMAGE_NAME="lonchera"

# Full image name with version
FULL_IMAGE_NAME="${IMAGE_NAME}:${VERSION}"

docker rm "${IMAGE_NAME}" 2>/dev/null || true

echo "Building Docker image: ${FULL_IMAGE_NAME}"

# Build the Docker image
docker build -t "${FULL_IMAGE_NAME}" .

echo "Docker image built successfully"

echo "Stopping any existing container named ${IMAGE_NAME}"
docker stop "${IMAGE_NAME}" 2>/dev/null || true

echo "Running Docker container as daemon"

# Run the Docker container as a daemon
docker run -d --name "${IMAGE_NAME}" "${FULL_IMAGE_NAME}"

echo "Docker container is now running as a daemon"

# Print the container ID
CONTAINER_ID=$(docker ps -q -f name="${IMAGE_NAME}")
echo "Container ID: ${CONTAINER_ID}"

# if CONTAINER_ID is empty, then the container is not running
# show an error message and exit with a non-zero status
if [ -z "${CONTAINER_ID}" ]; then
  echo "Container is not running"
  exit 1
fi