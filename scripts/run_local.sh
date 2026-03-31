#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_TAG="${IMAGE_TAG:-autohdr-local:latest}"
IMAGES_DIR="$ROOT_DIR/data/sample_500/images"
OUTPUT_DIR="$ROOT_DIR/output"
SKIP_BUILD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--skip-build] [--tag IMAGE_TAG]" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$IMAGES_DIR" ]]; then
  echo "Missing sample images at $IMAGES_DIR" >&2
  echo "Run scripts/download_sample.sh first." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
rm -f "$OUTPUT_DIR/predictions.csv"

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  BUILD_CMD=(docker build -t "$IMAGE_TAG" .)
  if [[ "$(uname -s)" == "Darwin" ]]; then
    BUILD_CMD=(docker build --platform linux/amd64 -t "$IMAGE_TAG" .)
  fi

  echo "Building Docker image: $IMAGE_TAG"
  "${BUILD_CMD[@]}"
fi

echo "Running container against sample dataset"
RUN_CMD=(docker run --rm)
if [[ "$(uname -s)" == "Darwin" ]]; then
  RUN_CMD+=(--platform linux/amd64)
fi

"${RUN_CMD[@]}" \
  -v "$IMAGES_DIR:/input/images:ro" \
  -v "$OUTPUT_DIR:/output" \
  "$IMAGE_TAG"

echo "Predictions written to $OUTPUT_DIR/predictions.csv"
