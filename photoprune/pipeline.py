"""The grouping pipeline.

Takes a list of `PhotoFile` and returns the merged duplicate `DuplicateGroup`s,
each with a suggested keeper picked by the quality score. Composes the
lower-level building blocks:

    hasher (pHash)  →  embedder (CLIP / MobileNet)
                          ↓
                     indexer (Faiss + Union-Find)
                          ↓
                     quality scoring + merge

This module is the standalone grouping core. Anything in the codebase
that wants duplicate groups calls `find_duplicate_groups()`. New modes
that need different grouping behavior can either:

    - call `find_duplicate_groups` with different config
    - compose the lower-level modules directly (hasher, embedder, indexer)
    - add a sibling pipeline function alongside this one
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
from PIL import Image
from tqdm import tqdm

from .embedder import embed_photos
from .hasher import compute_phashes, group_by_phash
from .indexer import find_near_duplicate_groups
from .models import DetectionType, DuplicateGroup, PhotoFile


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------


def _compute_sharpness(path: str) -> float | None:
    try:
        import cv2
    except Exception:
        return None
    try:
        with Image.open(path) as img:
            arr = np.asarray(img.convert("L"), dtype=np.uint8)
        if arr.ndim != 2 or arr.size == 0:
            return None
        return float(cv2.Laplacian(arr, cv2.CV_64F).var())
    except Exception:
        return None


def _add_sharpness(
    photos: Iterable[PhotoFile], *, show_progress: bool = True
) -> None:
    iterator = list(photos)
    if show_progress:
        iterator = tqdm(iterator, desc="sharpness", unit="img")
    for p in iterator:
        if p.sharpness is None:
            p.sharpness = _compute_sharpness(p.path)


def _quality_rank(
    p: PhotoFile, max_s: float, max_r: float, max_f: float
) -> float:
    s = (p.sharpness or 0.0) / max_s if max_s > 0 else 0.0
    r = p.resolution / max_r if max_r > 0 else 0.0
    f = p.size_bytes / max_f if max_f > 0 else 0.0
    return 0.5 * s + 0.3 * r + 0.2 * f


def _pick_keep_and_rank(group: List[PhotoFile]) -> str:
    """Score each member, set its `quality_rank`, return the keeper's path."""
    max_s = max((p.sharpness or 0.0) for p in group)
    max_r = max(p.resolution for p in group)
    max_f = max(p.size_bytes for p in group)
    best_path = group[0].path
    best_score = -1.0
    for p in group:
        score = _quality_rank(p, max_s, max_r, max_f)
        p.quality_rank = score
        if score > best_score:
            best_score = score
            best_path = p.path
    return best_path


# ---------------------------------------------------------------------------
# Group merge (Union-Find over exact + near results)
# ---------------------------------------------------------------------------


def _merge_groups(
    photos: List[PhotoFile],
    exact_groups: List[List[PhotoFile]],
    near_groups: List[Tuple[List[PhotoFile], float]],
) -> List[DuplicateGroup]:
    """Union-Find merge of pHash and embedding-similarity groups.

    A photo present in both an exact group and a near group ends up in
    the same merged group ("mixed" detection). Returns groups of size ≥ 2,
    largest first.
    """
    path_to_idx: Dict[str, int] = {p.path: i for i, p in enumerate(photos)}
    n = len(photos)
    parent = list(range(n))
    in_exact: set[int] = set()
    in_near: set[int] = set()
    near_max: Dict[int, float] = {}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for grp in exact_groups:
        idxs = [path_to_idx[p.path] for p in grp if p.path in path_to_idx]
        in_exact.update(idxs)
        for i in idxs[1:]:
            union(idxs[0], i)

    for members, sim in near_groups:
        idxs = [path_to_idx[p.path] for p in members if p.path in path_to_idx]
        in_near.update(idxs)
        for i in idxs[1:]:
            union(idxs[0], i)
        for i in idxs:
            near_max[find(i)] = max(near_max.get(find(i), 0.0), sim)

    clusters: Dict[int, List[int]] = {}
    relevant = in_exact | in_near
    for i in relevant:
        clusters.setdefault(find(i), []).append(i)

    out: List[DuplicateGroup] = []
    for gid, (root, members) in enumerate(
        sorted(clusters.items(), key=lambda kv: -len(kv[1])), start=1
    ):
        if len(members) < 2:
            continue
        photo_members = [photos[i] for i in members]
        has_exact = any(i in in_exact for i in members)
        has_near = any(i in in_near for i in members)
        if has_exact and has_near:
            detection: DetectionType = "mixed"
        elif has_exact:
            detection = "exact"
        else:
            detection = "near"

        max_sim = (
            1.0
            if detection == "exact"
            else near_max.get(root, 1.0 if has_exact else 0.0)
        )
        keep = _pick_keep_and_rank(photo_members)
        out.append(
            DuplicateGroup(
                group_id=str(gid),
                detection_type=detection,
                members=photo_members,
                max_similarity=max_sim,
                suggested_keep_path=keep,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def find_duplicate_groups(
    photos: List[PhotoFile],
    *,
    output_dir: Path,
    model: str = "clip",
    threshold: float = 0.94,
    phash_threshold: int = 10,
    use_embedding_cache: bool = True,
    compute_sharpness: bool = True,
    progress: bool = True,
) -> List[DuplicateGroup]:
    """Run the full grouping pipeline.

    Mutates each photo in `photos` to populate `phash`, `embedding_index`,
    `sharpness`, and `quality_rank`. Returns the merged duplicate groups
    (size ≥ 2, largest first), with a suggested keeper picked per group.

    Parameters
    ----------
    photos
        The photos to group. Mutated in place.
    output_dir
        Where to read/write the embedding cache.
    model
        Embedding model: "clip" (accurate, ViT-B/32) or "mobilenet" (fast).
    threshold
        Cosine-similarity cutoff for the near-duplicate pass (0.0–1.0).
    phash_threshold
        Hamming-distance cutoff for the exact-duplicate pHash pass.
    use_embedding_cache
        Reuse cached embeddings when mtime/size match.
    compute_sharpness
        Run the Laplacian-variance sharpness pass. Disable to skip it
        if the caller doesn't need quality scores.
    progress
        Show tqdm progress bars for the slow passes.
    """
    compute_phashes(photos, show_progress=progress)
    exact_groups = group_by_phash(photos, threshold=phash_threshold)

    vectors = embed_photos(
        photos,
        output_dir,
        model,
        use_cache=use_embedding_cache,
        show_progress=progress,
    )

    photos_with_emb = [p for p in photos if p.embedding_index is not None]
    if vectors.shape[0] != len(photos_with_emb):
        # Defensive: realign vectors with photos in their embedding_index order.
        photos_with_emb = sorted(
            photos_with_emb, key=lambda p: p.embedding_index or 0
        )

    near_groups = find_near_duplicate_groups(
        photos_with_emb, vectors, threshold=threshold
    )

    if compute_sharpness:
        _add_sharpness(photos, show_progress=progress)

    return _merge_groups(photos, exact_groups, near_groups)
