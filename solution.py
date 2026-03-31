"""
AutoHDR Challenge submission.

This implementation is a simple, scalable heuristic:
1. Normalize each image to reduce exposure differences.
2. Build edge-focused perceptual hashes and low-res structural embeddings.
3. Use a BK-tree over hashes to find likely bracket mates.
4. Merge images when both edge and grayscale structure are highly similar.

It is intentionally lightweight so it can be tuned quickly on the public sample.
"""

from __future__ import annotations

import csv
import os
import time
import zlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

INPUT_DIR = Path(os.getenv("INPUT_DIR", "/input/images"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/output"))
SUPPORTED = {".jpg", ".jpeg", ".png"}

HASH_SIZE = 8
VERIFY_SIZE = 16
PROGRESS_EVERY = int(os.getenv("PROGRESS_EVERY", "250"))
EDGE_QUERY_RADIUS = int(os.getenv("EDGE_QUERY_RADIUS", "8"))
MAX_CANDIDATES_PER_IMAGE = int(os.getenv("MAX_CANDIDATES_PER_IMAGE", "48"))
MIN_EDGE_SIM = float(os.getenv("MIN_EDGE_SIM", "0.965"))
MIN_GRAY_SIM = float(os.getenv("MIN_GRAY_SIM", "0.925"))
MIN_COMBINED_SIM = float(os.getenv("MIN_COMBINED_SIM", "0.952"))


@dataclass
class ImageFeatures:
    filename: str
    gray_hash: int
    edge_hash: int
    gray_vec: np.ndarray
    edge_vec: np.ndarray
    valid: bool


class DisjointSet:
    def __init__(self, size: int):
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> bool:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return False

        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root

        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1
        return True


class BKTree:
    def __init__(self):
        self.root: BKNode | None = None

    def add(self, value: int, index: int) -> None:
        if self.root is None:
            self.root = BKNode(value=value, index=index)
            return

        node = self.root
        while True:
            distance = hamming_distance(value, node.value)
            child = node.children.get(distance)
            if child is None:
                node.children[distance] = BKNode(value=value, index=index)
                return
            node = child

    def search(self, value: int, radius: int) -> list[int]:
        if self.root is None:
            return []

        matches: list[int] = []
        stack = [self.root]
        while stack:
            node = stack.pop()
            distance = hamming_distance(value, node.value)
            if distance <= radius:
                matches.append(node.index)

            lower = distance - radius
            upper = distance + radius
            for child_distance, child in node.children.items():
                if lower <= child_distance <= upper:
                    stack.append(child)
        return matches


@dataclass
class BKNode:
    value: int
    index: int
    children: dict[int, "BKNode"] | None = None

    def __post_init__(self) -> None:
        if self.children is None:
            self.children = {}


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def dhash(image: np.ndarray, size: int = HASH_SIZE) -> int:
    resized = cv2.resize(image, (size + 1, size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    value = 0
    for bit in diff.reshape(-1):
        value = (value << 1) | int(bit)
    return value


def make_unit_vector(image: np.ndarray, size: int = VERIFY_SIZE) -> np.ndarray:
    resized = cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)
    resized -= float(resized.mean())
    norm = float(np.linalg.norm(resized))
    if norm < 1e-6:
        return np.zeros(size * size, dtype=np.float32)
    return (resized / norm).reshape(-1)


def preprocess_gray(image: np.ndarray) -> np.ndarray:
    image = cv2.resize(image, (96, 96), interpolation=cv2.INTER_AREA)
    image = cv2.GaussianBlur(image, (3, 3), 0)
    image = cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(image)


def preprocess_edges(image: np.ndarray) -> np.ndarray:
    grad_x = cv2.Sobel(image, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(image, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(grad_x, grad_y)
    magnitude = cv2.GaussianBlur(magnitude, (3, 3), 0)
    peak = float(magnitude.max())
    if peak > 1e-6:
        magnitude /= peak
    return (magnitude * 255.0).astype(np.uint8)


def fallback_features(filename: str) -> ImageFeatures:
    unique_hash = zlib.crc32(filename.encode("utf-8"))
    zeros = np.zeros(VERIFY_SIZE * VERIFY_SIZE, dtype=np.float32)
    return ImageFeatures(
        filename=filename,
        gray_hash=unique_hash,
        edge_hash=unique_hash,
        gray_vec=zeros,
        edge_vec=zeros,
        valid=False,
    )


def extract_features(path: str) -> ImageFeatures:
    filename = os.path.basename(path)
    image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if image is None:
        print(f"Warning: failed to read {path}; leaving it as a singleton group")
        return fallback_features(filename)

    gray = preprocess_gray(image)
    edges = preprocess_edges(gray)
    return ImageFeatures(
        filename=filename,
        gray_hash=dhash(gray),
        edge_hash=dhash(edges),
        gray_vec=make_unit_vector(gray),
        edge_vec=make_unit_vector(edges),
        valid=True,
    )


def should_merge(left: ImageFeatures, right: ImageFeatures) -> bool:
    if not left.valid or not right.valid:
        return False

    edge_sim = float(np.dot(left.edge_vec, right.edge_vec))
    gray_sim = float(np.dot(left.gray_vec, right.gray_vec))
    combined_sim = 0.7 * edge_sim + 0.3 * gray_sim

    return (
        edge_sim >= MIN_EDGE_SIM
        and gray_sim >= MIN_GRAY_SIM
        and combined_sim >= MIN_COMBINED_SIM
    )


def group_images(image_paths: list[str]) -> list[list[str]]:
    start = time.time()
    sorted_paths = sorted(image_paths)
    total = len(sorted_paths)

    print(f"Extracting features for {total} images")
    features: list[ImageFeatures] = []
    for idx, path in enumerate(sorted_paths, start=1):
        features.append(extract_features(path))
        if idx % PROGRESS_EVERY == 0 or idx == total:
            print(f"  feature extraction: {idx}/{total}")

    tree = BKTree()
    for idx, feature in enumerate(features):
        tree.add(feature.edge_hash, idx)

    dsu = DisjointSet(total)
    compared_pairs = 0
    merged_pairs = 0
    candidate_total = 0

    print("Comparing likely matches")
    for idx, feature in enumerate(features):
        candidates = []
        for other_idx in tree.search(feature.edge_hash, EDGE_QUERY_RADIUS):
            if other_idx <= idx:
                continue

            other = features[other_idx]
            candidates.append((
                hamming_distance(feature.edge_hash, other.edge_hash),
                hamming_distance(feature.gray_hash, other.gray_hash),
                other_idx,
            ))

        candidates.sort()
        limited = candidates[:MAX_CANDIDATES_PER_IMAGE]
        candidate_total += len(limited)

        for _, _, other_idx in limited:
            compared_pairs += 1
            if should_merge(feature, features[other_idx]) and dsu.union(idx, other_idx):
                merged_pairs += 1

        progress_idx = idx + 1
        if progress_idx % PROGRESS_EVERY == 0 or progress_idx == total:
            print(f"  candidate scan: {progress_idx}/{total}")

    groups: dict[int, list[str]] = defaultdict(list)
    for idx, feature in enumerate(features):
        groups[dsu.find(idx)].append(feature.filename)

    output_groups = [sorted(group) for group in groups.values()]
    output_groups.sort(key=lambda group: (len(group), group[0]))

    elapsed = time.time() - start
    avg_candidates = candidate_total / max(total, 1)
    print(f"Compared {compared_pairs} candidate pairs")
    print(f"Merged {merged_pairs} pairs into {len(output_groups)} groups")
    print(f"Average candidates per image: {avg_candidates:.2f}")
    print(f"Grouping completed in {elapsed:.1f}s")
    return output_groups


def validate_groups(groups: list[list[str]], image_paths: list[str]) -> None:
    expected = {os.path.basename(path) for path in image_paths}
    seen: dict[str, int] = {}

    for group_id, group in enumerate(groups):
        for filename in group:
            basename = os.path.basename(filename)
            if basename in seen:
                raise ValueError(
                    f"Duplicate filename {basename!r} found in groups {seen[basename]} and {group_id}"
                )
            seen[basename] = group_id

    missing = expected - set(seen)
    extra = set(seen) - expected
    if missing or extra:
        raise ValueError(
            f"Grouping mismatch: missing={len(missing)} extra={len(extra)}"
        )


def main() -> None:
    images = sorted(
        str(path)
        for path in INPUT_DIR.iterdir()
        if path.suffix.lower() in SUPPORTED
    )
    print(f"Loaded {len(images)} images from {INPUT_DIR}")

    groups = group_images(images)
    validate_groups(groups, images)
    print(f"Predicted {len(groups)} groups")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "predictions.csv"
    with out_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["filename", "group_id"])
        for group_id, group in enumerate(groups):
            for filename in group:
                writer.writerow([filename, group_id])

    print(f"Wrote {sum(len(group) for group in groups)} predictions to {out_path}")


if __name__ == "__main__":
    main()
