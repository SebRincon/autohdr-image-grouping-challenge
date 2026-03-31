#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 DOCKER_IMAGE EMAIL [MACHINE_TYPE]" >&2
  echo "Example: $0 youruser/autohdr-solution:v1 you@example.com cpu-xlarge" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_IMAGE="$1"
EMAIL="$2"
MACHINE_TYPE="${3:-cpu-xlarge}"

BUILD_CMD=(docker build -t "$DOCKER_IMAGE" .)
if [[ "$(uname -s)" == "Darwin" ]]; then
  BUILD_CMD=(docker build --platform linux/amd64 -t "$DOCKER_IMAGE" .)
fi

echo "Building $DOCKER_IMAGE"
(
  cd "$ROOT_DIR"
  "${BUILD_CMD[@]}"
)

echo "Pushing $DOCKER_IMAGE"
docker push "$DOCKER_IMAGE"

"$ROOT_DIR/scripts/package_submission.sh" "$DOCKER_IMAGE" "$EMAIL" "$MACHINE_TYPE"

echo
echo "Next:"
echo "  1. Verify the Docker Hub repo is public"
echo "  2. Upload $ROOT_DIR/submission.zip to Codabench"
