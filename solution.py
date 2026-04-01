"""
AutoHDR Challenge submission.

Pipeline:
1. Build exposure-normalized grayscale and edge previews for every image.
2. Generate candidate neighbors from exact cosine search on small batches and
   LSH buckets on large batches.
3. Verify promising pairs with ORB + RANSAC homography inliers.
4. Merge only very strong pairs, with a hard cap on group size.

The implementation is tuned to prefer precision over aggressive clustering,
because a single bad merge destroys multiple exact-match groups.
"""

from __future__ import annotations

import csv
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

INPUT_DIR = Path(os.getenv("INPUT_DIR", "/input/images"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/output"))
SUPPORTED = {".jpg", ".jpeg", ".png"}

PREVIEW_SIZE = int(os.getenv("PREVIEW_SIZE", "16"))
NORMALIZE_LONG_SIDE = int(os.getenv("NORMALIZE_LONG_SIDE", "512"))
ORB_LONG_SIDE = int(os.getenv("ORB_LONG_SIDE", "480"))
ORB_FEATURES = int(os.getenv("ORB_FEATURES", "1200"))

PROGRESS_EVERY = int(os.getenv("PROGRESS_EVERY", "250"))
WORKERS = int(os.getenv("WORKERS", str(min(8, os.cpu_count() or 1))))
EXACT_SEARCH_LIMIT = int(os.getenv("EXACT_SEARCH_LIMIT", "3000"))
MAX_CANDIDATES_PER_IMAGE = int(os.getenv("MAX_CANDIDATES_PER_IMAGE", "32"))

LSH_TABLES = int(os.getenv("LSH_TABLES", "8"))
LSH_BITS = int(os.getenv("LSH_BITS", "12"))
LSH_SEED = int(os.getenv("LSH_SEED", "20260331"))

GRAY_WEIGHT = float(os.getenv("GRAY_WEIGHT", "0.35"))
EDGE_WEIGHT = float(os.getenv("EDGE_WEIGHT", "0.65"))

MIN_DESCRIPTOR_COS = float(os.getenv("MIN_DESCRIPTOR_COS", "0.78"))
MIN_EDGE_COS = float(os.getenv("MIN_EDGE_COS", "0.82"))
MIN_GRAY_COS = float(os.getenv("MIN_GRAY_COS", "0.60"))
DIRECT_EDGE_COS = float(os.getenv("DIRECT_EDGE_COS", "0.955"))
DIRECT_GRAY_COS = float(os.getenv("DIRECT_GRAY_COS", "0.93"))

RATIO_TEST = float(os.getenv("RATIO_TEST", "0.75"))
MIN_GOOD_MATCHES = int(os.getenv("MIN_GOOD_MATCHES", "30"))
MIN_INLIERS = int(os.getenv("MIN_INLIERS", "20"))
MIN_INLIER_RATIO = float(os.getenv("MIN_INLIER_RATIO", "0.45"))

MAX_GROUP_SIZE = int(os.getenv("MAX_GROUP_SIZE", "8"))


def resize_long_side(image: np.ndarray, long_side: int) -> np.ndarray:
    height, width = image.shape[:2]
    scale = long_side / max(height, width)
    if scale >= 1.0:
        return image.copy()
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    return cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)


def normalize_unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm < 1e-9:
        return np.zeros_like(vector, dtype=np.float32)
    return (vector / norm).astype(np.float32)


def normalize_centered(image: np.ndarray) -> np.ndarray:
    vector = image.astype(np.float32).reshape(-1)
    vector -= float(vector.mean())
    return normalize_unit(vector)


def normalize_nonnegative(image: np.ndarray) -> np.ndarray:
    return normalize_unit(image.astype(np.float32).reshape(-1))


def pack_signature(bits: np.ndarray) -> int:
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def preprocess_base_gray(image: np.ndarray) -> np.ndarray:
    image = resize_long_side(image, NORMALIZE_LONG_SIDE)
    image = cv2.GaussianBlur(image, (3, 3), 0)
    image = cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(image)


def preprocess_edges(gray: np.ndarray) -> np.ndarray:
    return cv2.Canny(gray, 50, 150)


@dataclass
class ImageFeatures:
    filename: str
    path: str
    gray_vec: np.ndarray
    edge_vec: np.ndarray
    descriptor: np.ndarray
    valid: bool
    orb_points: np.ndarray | None = None
    orb_desc: np.ndarray | None = None


class DisjointSet:
    def __init__(self, size: int):
        self.parent = list(range(size))
        self.rank = [0] * size
        self.component_size = [1] * size

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def can_union(self, left: int, right: int, max_size: int) -> bool:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return False
        return self.component_size[left_root] + self.component_size[right_root] <= max_size

    def union(self, left: int, right: int) -> bool:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return False

        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root

        self.parent[right_root] = left_root
        self.component_size[left_root] += self.component_size[right_root]
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1
        return True


def extract_features(path: str) -> ImageFeatures:
    filename = os.path.basename(path)
    image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if image is None:
        print(f"Warning: failed to read {path}; leaving it as a singleton group")
        zeros = np.zeros(PREVIEW_SIZE * PREVIEW_SIZE, dtype=np.float32)
        return ImageFeatures(
            filename=filename,
            path=path,
            gray_vec=zeros,
            edge_vec=zeros,
            descriptor=zeros,
            valid=False,
        )

    gray = preprocess_base_gray(image)
    edges = preprocess_edges(gray)

    gray_preview = cv2.resize(gray, (PREVIEW_SIZE, PREVIEW_SIZE), interpolation=cv2.INTER_AREA)
    edge_preview = cv2.resize(edges, (PREVIEW_SIZE, PREVIEW_SIZE), interpolation=cv2.INTER_AREA)

    gray_vec = normalize_centered(gray_preview)
    edge_vec = normalize_nonnegative(edge_preview)
    descriptor = normalize_unit(
        np.concatenate(
            [
                gray_vec * GRAY_WEIGHT,
                edge_vec * EDGE_WEIGHT,
            ]
        )
    )

    return ImageFeatures(
        filename=filename,
        path=path,
        gray_vec=gray_vec,
        edge_vec=edge_vec,
        descriptor=descriptor,
        valid=True,
    )


def ensure_orb(feature: ImageFeatures) -> None:
    if feature.orb_desc is not None or not feature.valid:
        return

    image = cv2.imread(feature.path, cv2.IMREAD_GRAYSCALE)
    if image is None:
        feature.orb_points = np.empty((0, 2), dtype=np.float32)
        feature.orb_desc = np.empty((0, 32), dtype=np.uint8)
        return

    image = resize_long_side(image, ORB_LONG_SIDE)
    image = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(image)
    orb = cv2.ORB_create(ORB_FEATURES)
    keypoints, descriptors = orb.detectAndCompute(image, None)

    if descriptors is None or not keypoints:
        feature.orb_points = np.empty((0, 2), dtype=np.float32)
        feature.orb_desc = np.empty((0, 32), dtype=np.uint8)
        return

    feature.orb_points = np.array([kp.pt for kp in keypoints], dtype=np.float32)
    feature.orb_desc = descriptors


def build_features(image_paths: list[str]) -> list[ImageFeatures]:
    total = len(image_paths)
    features: list[ImageFeatures] = [None] * total  # type: ignore[assignment]

    print(f"Extracting preview features for {total} images with {WORKERS} workers")
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        for idx, feature in enumerate(executor.map(extract_features, image_paths), start=1):
            features[idx - 1] = feature
            if idx % PROGRESS_EVERY == 0 or idx == total:
                print(f"  feature extraction: {idx}/{total}")
    return features


def candidate_pairs_exact(features: list[ImageFeatures]) -> list[list[tuple[float, int]]]:
    descriptors = np.stack([feature.descriptor for feature in features]).astype(np.float32)
    similarity = descriptors @ descriptors.T
    np.fill_diagonal(similarity, -1.0)

    candidates: list[list[tuple[float, int]]] = [[] for _ in features]
    for idx in range(len(features)):
        row = similarity[idx]
        shortlist = np.argpartition(row, -MAX_CANDIDATES_PER_IMAGE)[-MAX_CANDIDATES_PER_IMAGE:]
        shortlist = shortlist[np.argsort(row[shortlist])[::-1]]
        candidates[idx] = [
            (float(row[other_idx]), int(other_idx))
            for other_idx in shortlist
            if other_idx > idx and row[other_idx] > 0
        ]
    return candidates


def candidate_pairs_lsh(features: list[ImageFeatures]) -> list[list[tuple[float, int]]]:
    descriptors = np.stack([feature.descriptor for feature in features]).astype(np.float32)
    rng = np.random.default_rng(LSH_SEED)
    projections = rng.standard_normal(
        (LSH_TABLES, LSH_BITS, descriptors.shape[1])
    ).astype(np.float32)

    buckets: list[dict[int, list[int]]] = [defaultdict(list) for _ in range(LSH_TABLES)]
    signatures: list[list[int]] = [[] for _ in features]

    for idx, descriptor in enumerate(descriptors):
        for table_idx in range(LSH_TABLES):
            key = pack_signature((projections[table_idx] @ descriptor) > 0)
            buckets[table_idx][key].append(idx)
            signatures[idx].append(key)

    candidates: list[list[tuple[float, int]]] = [[] for _ in features]
    for idx, descriptor in enumerate(descriptors):
        candidate_set: set[int] = set()
        for table_idx, key in enumerate(signatures[idx]):
            candidate_set.update(buckets[table_idx][key])
        candidate_set.discard(idx)

        scored = []
        for other_idx in candidate_set:
            if other_idx <= idx:
                continue
            score = float(np.dot(descriptor, descriptors[other_idx]))
            if score > 0:
                scored.append((score, other_idx))
        scored.sort(reverse=True)
        candidates[idx] = scored[:MAX_CANDIDATES_PER_IMAGE]

    return candidates


def quick_similarity(left: ImageFeatures, right: ImageFeatures) -> tuple[float, float, float]:
    gray_cos = float(np.dot(left.gray_vec, right.gray_vec))
    edge_cos = float(np.dot(left.edge_vec, right.edge_vec))
    descriptor_cos = float(np.dot(left.descriptor, right.descriptor))
    return gray_cos, edge_cos, descriptor_cos


def orb_inlier_stats(left: ImageFeatures, right: ImageFeatures) -> tuple[int, int, float]:
    ensure_orb(left)
    ensure_orb(right)

    if (
        left.orb_desc is None
        or right.orb_desc is None
        or len(left.orb_desc) < 2
        or len(right.orb_desc) < 2
    ):
        return 0, 0, 0.0

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    knn = matcher.knnMatch(left.orb_desc, right.orb_desc, k=2)
    good = [m for m, n in knn if m.distance < RATIO_TEST * n.distance]
    if len(good) < 4:
        return len(good), 0, 0.0

    left_points = left.orb_points[[m.queryIdx for m in good]]
    right_points = right.orb_points[[m.trainIdx for m in good]]
    _, mask = cv2.findHomography(left_points, right_points, cv2.RANSAC, 4.0)
    inliers = int(mask.sum()) if mask is not None else 0
    ratio = inliers / len(good) if good else 0.0
    return len(good), inliers, ratio


def should_merge(left: ImageFeatures, right: ImageFeatures, descriptor_cos_hint: float) -> bool:
    if not left.valid or not right.valid:
        return False

    gray_cos, edge_cos, descriptor_cos = quick_similarity(left, right)
    descriptor_cos = max(descriptor_cos, descriptor_cos_hint)

    if edge_cos >= DIRECT_EDGE_COS and gray_cos >= DIRECT_GRAY_COS:
        return True

    if (
        descriptor_cos < MIN_DESCRIPTOR_COS
        or edge_cos < MIN_EDGE_COS
        or gray_cos < MIN_GRAY_COS
    ):
        return False

    good_matches, inliers, inlier_ratio = orb_inlier_stats(left, right)
    return (
        good_matches >= MIN_GOOD_MATCHES
        and inliers >= MIN_INLIERS
        and inlier_ratio >= MIN_INLIER_RATIO
    )


def group_images(image_paths: list[str]) -> list[list[str]]:
    start = time.time()
    sorted_paths = sorted(image_paths)
    total = len(sorted_paths)
    features = build_features(sorted_paths)

    if total <= EXACT_SEARCH_LIMIT:
        print("Generating exact descriptor neighbors")
        candidates = candidate_pairs_exact(features)
    else:
        print("Generating LSH descriptor neighbors")
        candidates = candidate_pairs_lsh(features)

    dsu = DisjointSet(total)
    compared_pairs = 0
    merged_pairs = 0
    candidate_total = 0

    print("Verifying candidate pairs")
    for idx, shortlist in enumerate(candidates, start=1):
        candidate_total += len(shortlist)
        for descriptor_cos, other_idx in shortlist:
            compared_pairs += 1
            if not dsu.can_union(idx - 1, other_idx, MAX_GROUP_SIZE):
                continue
            if should_merge(features[idx - 1], features[other_idx], descriptor_cos):
                if dsu.union(idx - 1, other_idx):
                    merged_pairs += 1

        if idx % PROGRESS_EVERY == 0 or idx == total:
            print(f"  candidate verification: {idx}/{total}")

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
