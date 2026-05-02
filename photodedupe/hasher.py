"""Perceptual hashing (pHash) and exact-duplicate grouping via Hamming distance."""

from __future__ import annotations

from typing import Dict, List, Tuple

import imagehash
from PIL import Image
from tqdm import tqdm

from .models import PhotoFile

_HASH_SIZE = 8  # Produces 64-bit hashes.


def compute_phash(path: str) -> str | None:
    """Return a hex-string pHash for the image, or None if unreadable."""
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            return str(imagehash.phash(img, hash_size=_HASH_SIZE))
    except Exception:
        return None


def compute_phashes(photos: List[PhotoFile], *, show_progress: bool = True) -> None:
    """Populate `photo.phash` for every photo. Mutates input list in place."""
    iterator = tqdm(photos, desc="pHash", unit="img") if show_progress else photos
    for photo in iterator:
        if photo.phash is not None:
            continue
        photo.phash = compute_phash(photo.path)


def _hex_to_int(hash_hex: str) -> int:
    return int(hash_hex, 16)


def _hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def group_by_phash(
    photos: List[PhotoFile], threshold: int
) -> List[List[PhotoFile]]:
    """Return groups of photos within Hamming distance ≤ threshold of each other.

    Uses Union-Find so transitive matches collapse into a single cluster.
    Returns only groups with size ≥ 2.
    """
    n = len(photos)
    if n < 2:
        return []

    indexed: List[Tuple[int, int]] = []  # (orig_index, hash_int)
    for i, p in enumerate(photos):
        if p.phash is None:
            continue
        try:
            indexed.append((i, _hex_to_int(p.phash)))
        except ValueError:
            continue

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    if threshold == 0:
        # Fast path: bucket by hash, group identicals.
        buckets: Dict[int, List[int]] = {}
        for orig_i, h in indexed:
            buckets.setdefault(h, []).append(orig_i)
        for members in buckets.values():
            if len(members) >= 2:
                first = members[0]
                for other in members[1:]:
                    union(first, other)
    else:
        # O(n^2) pairwise compare. Acceptable since pHash is cheap and most
        # libraries are well under 100k photos.
        for i in range(len(indexed)):
            oi, hi = indexed[i]
            for j in range(i + 1, len(indexed)):
                oj, hj = indexed[j]
                if _hamming(hi, hj) <= threshold:
                    union(oi, oj)

    clusters: Dict[int, List[PhotoFile]] = {}
    for orig_i, _ in indexed:
        root = find(orig_i)
        clusters.setdefault(root, []).append(photos[orig_i])

    return [members for members in clusters.values() if len(members) >= 2]
