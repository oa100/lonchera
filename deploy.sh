#!/usr/bin/env bash
set -euo pipefail

# Read the version from the VERSION file
VERSION=$(cat VERSION)

# Get the short commit hash of the current branch
COMMIT=$(git rev-parse --short HEAD)

# Get the current branch name
BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Check if there are uncommitted changes
if [[ -n $(git status --porcelain) ]]; then
    DIRTY=" (dirty)"
else
    DIRTY=""
fi

# Construct the version string
if [[ "$BRANCH" == "master" || "$BRANCH" == "main" ]]; then
    FULL_VERSION="${VERSION}-${COMMIT}${DIRTY}"
else
    FULL_VERSION="${VERSION}-${COMMIT}@${BRANCH}${DIRTY}"
fi

# Run the deploy command with the constructed version
fly deploy --env VERSION="$FULL_VERSION" --env COMMIT="$COMMIT"