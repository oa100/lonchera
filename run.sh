#!/usr/bin/env bash
set -euo pipefail

# Generate version based on current date and time
VERSION=$(date +"%Y%m%d_%H%M")

# Name of the Docker image
IMAGE_NAME="lonchera"

# Full image name with version
FULL_IMAGE_NAME="${IMAGE_NAME}:${VERSION}"

echo "Stopping any existing container named ${IMAGE_NAME}"
docker stop "${IMAGE_NAME}" 2>/dev/null || true
docker rm "${IMAGE_NAME}" 2>/dev/null || true

echo "Building Docker image: ${FULL_IMAGE_NAME}"

# Build the Docker image
docker build -t "${FULL_IMAGE_NAME}" .

echo "Docker image built successfully"

echo "Running Docker container as daemon"

# Run the Docker container as a daemon
docker run -d --name "${IMAGE_NAME}" "${FULL_IMAGE_NAME}"

echo "Docker container is now running as a daemon"

# Print the container ID
CONTAINER_ID=$(docker ps -q -f name="${IMAGE_NAME}")
echo "Container ID: ${CONTAINER_ID}"