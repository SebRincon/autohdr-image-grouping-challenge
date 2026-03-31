#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGES_DIR="$ROOT_DIR/data/sample_500/images"
OUTPUT_DIR="$ROOT_DIR/output"

if [[ ! -d "$IMAGES_DIR" ]]; then
  echo "Missing sample images at $IMAGES_DIR" >&2
  echo "Run scripts/download_sample.sh first." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
rm -f "$OUTPUT_DIR/predictions.csv"

echo "Running solution.py on the host against sample data"
INPUT_DIR="$IMAGES_DIR" OUTPUT_DIR="$OUTPUT_DIR" python3 "$ROOT_DIR/solution.py"
echo "Predictions written to $OUTPUT_DIR/predictions.csv"
