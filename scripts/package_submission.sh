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

cat > "$ROOT_DIR/submission.yaml" <<EOF
docker_image: $DOCKER_IMAGE
machine_type: $MACHINE_TYPE
email: $EMAIL
EOF

rm -f "$ROOT_DIR/submission.zip"
(
  cd "$ROOT_DIR"
  zip -q submission.zip submission.yaml
)

echo "Wrote:"
echo "  $ROOT_DIR/submission.yaml"
echo "  $ROOT_DIR/submission.zip"
