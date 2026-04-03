"""
AutoHDR singleton baseline submission.

This intentionally puts every image in its own group so you can validate
container execution, CSV formatting, scoring, and Codabench plumbing.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

INPUT_DIR = Path("/input/images")
OUTPUT_DIR = Path("/output")
SUPPORTED = {".jpg", ".jpeg", ".png"}


def group_images(image_paths: list[str]) -> list[list[str]]:
    return [[os.path.basename(path)] for path in sorted(image_paths)]


def main() -> None:
    images = sorted(
        str(path)
        for path in INPUT_DIR.iterdir()
        if path.suffix.lower() in SUPPORTED
    )
    print(f"Loaded {len(images)} images from {INPUT_DIR}")

    groups = group_images(images)
    print(f"Predicted {len(groups)} singleton groups")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "predictions.csv"
    with out_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["filename", "group_id"])
        for group_id, group in enumerate(groups):
            writer.writerow([group[0], group_id])

    print(f"Wrote {len(groups)} predictions to {out_path}")


if __name__ == "__main__":
    main()
