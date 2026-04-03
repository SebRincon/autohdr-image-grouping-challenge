#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_IMAGE="${1:-seb4594/autohdr-solution:singleton-v1}"
EMAIL="${2:-seb4594@gmail.com}"
MACHINE_TYPE="${3:-cpu-xlarge}"

BUILD_CMD=(docker build -t "$DOCKER_IMAGE" -f Dockerfile.singleton .)
if [[ "$(uname -s)" == "Darwin" ]]; then
  BUILD_CMD=(docker build --platform linux/amd64 -t "$DOCKER_IMAGE" -f Dockerfile.singleton .)
fi

echo "Building singleton baseline image: $DOCKER_IMAGE"
(
  cd "$ROOT_DIR"
  "${BUILD_CMD[@]}"
)

echo "Pushing $DOCKER_IMAGE"
docker push "$DOCKER_IMAGE"

cat > "$ROOT_DIR/submission-singleton.yaml" <<EOF
docker_image: $DOCKER_IMAGE
machine_type: $MACHINE_TYPE
email: $EMAIL
EOF

rm -f "$ROOT_DIR/submission-singleton.zip"
(
  cd "$ROOT_DIR"
  zip -q submission-singleton.zip submission-singleton.yaml
)

echo "Wrote:"
echo "  $ROOT_DIR/submission-singleton.yaml"
echo "  $ROOT_DIR/submission-singleton.zip"
