#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZIP_URL="https://grouping-dataset-solution.s3.amazonaws.com/downloads/autohdr_sample_500.zip"
ZIP_PATH="$ROOT_DIR/data/raw/autohdr_sample_500.zip"
DATA_DIR="$ROOT_DIR/data/sample_500"
TMP_DIR="$DATA_DIR/.unpack"

mkdir -p "$(dirname "$ZIP_PATH")"
mkdir -p "$DATA_DIR"

if [[ ! -f "$ZIP_PATH" ]]; then
  echo "Downloading sample dataset to $ZIP_PATH"
  curl -L --fail --progress-bar -o "$ZIP_PATH" "$ZIP_URL"
else
  echo "Using existing archive at $ZIP_PATH"
fi

if [[ -d "$DATA_DIR/images" && -f "$DATA_DIR/public_manifest.csv" ]]; then
  echo "Sample dataset already extracted at $DATA_DIR"
  exit 0
fi

rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

echo "Extracting sample dataset"
unzip -q "$ZIP_PATH" -d "$TMP_DIR"

IMAGES_DIR="$(find "$TMP_DIR" -type d -name images | head -n 1)"
MANIFEST_PATH="$(find "$TMP_DIR" -type f -name public_manifest.csv | head -n 1)"

if [[ -z "$IMAGES_DIR" || -z "$MANIFEST_PATH" ]]; then
  echo "Could not locate images/ and public_manifest.csv inside $ZIP_PATH" >&2
  exit 1
fi

rm -rf "$DATA_DIR/images"
mv "$IMAGES_DIR" "$DATA_DIR/images"
cp "$MANIFEST_PATH" "$DATA_DIR/public_manifest.csv"
rm -rf "$TMP_DIR"

echo "Sample dataset ready:"
echo "  images:   $DATA_DIR/images"
echo "  manifest: $DATA_DIR/public_manifest.csv"
