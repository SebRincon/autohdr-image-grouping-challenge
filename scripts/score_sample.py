#!/usr/bin/env python3
import csv
import sys
from collections import defaultdict
from pathlib import Path


def load_groups(path: Path) -> set[frozenset[str]]:
    buckets: dict[str, set[str]] = defaultdict(set)
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if "filename" not in reader.fieldnames or "group_id" not in reader.fieldnames:
            raise ValueError(f"{path} must contain filename and group_id columns")

        for row in reader:
            buckets[row["group_id"]].add(row["filename"])

    return {frozenset(files) for files in buckets.values()}


def main() -> int:
    root_dir = Path(__file__).resolve().parents[1]
    manifest_path = root_dir / "data" / "sample_500" / "public_manifest.csv"
    predictions_path = root_dir / "output" / "predictions.csv"

    if len(sys.argv) > 1:
        predictions_path = Path(sys.argv[1]).resolve()
    if len(sys.argv) > 2:
        manifest_path = Path(sys.argv[2]).resolve()

    if not manifest_path.exists():
        print(f"Missing manifest: {manifest_path}", file=sys.stderr)
        return 1
    if not predictions_path.exists():
        print(f"Missing predictions: {predictions_path}", file=sys.stderr)
        return 1

    reference = load_groups(manifest_path)
    predicted = load_groups(predictions_path)
    exact_matches = reference & predicted
    score = len(exact_matches) / len(reference)

    print(f"reference_groups={len(reference)}")
    print(f"predicted_groups={len(predicted)}")
    print(f"exact_matches={len(exact_matches)}")
    print(f"score={score:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
