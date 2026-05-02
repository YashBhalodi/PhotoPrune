"""Faiss similarity search and Union-Find clustering."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from .models import PhotoFile

_IVF_THRESHOLD = 50_000


def _build_index(vectors: np.ndarray):
    import faiss

    dim = vectors.shape[1]
    n = vectors.shape[0]
    if n < _IVF_THRESHOLD:
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)
        return index

    nlist = max(64, min(int(np.sqrt(n)), 4096))
    quantizer = faiss.IndexFlatIP(dim)
    index = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)
    index.train(vectors)
    index.add(vectors)
    index.nprobe = min(16, nlist)
    return index


def find_similar_pairs(
    vectors: np.ndarray, threshold: float
) -> List[Tuple[int, int, float]]:
    """Return all (i, j, similarity) pairs with i < j and similarity ≥ threshold.

    Vectors must be L2-normalized so inner product == cosine similarity.
    """
    if vectors.size == 0 or vectors.shape[0] < 2:
        return []

    import faiss  # noqa: F401  (import for side-effects / informative error)

    index = _build_index(vectors)

    # k-NN search is more reliable across faiss-cpu builds than range_search,
    # which doesn't work for IVF indexes with all metrics.
    k = min(50, vectors.shape[0])
    sims, idx = index.search(vectors, k)

    pairs: List[Tuple[int, int, float]] = []
    seen: set[Tuple[int, int]] = set()
    for i in range(vectors.shape[0]):
        for col in range(k):
            j = int(idx[i, col])
            if j == -1 or j == i:
                continue
            s = float(sims[i, col])
            if s < threshold:
                continue
            a, b = (i, j) if i < j else (j, i)
            key = (a, b)
            if key in seen:
                continue
            seen.add(key)
            pairs.append((a, b, s))
    return pairs


def cluster_pairs(
    n: int, pairs: List[Tuple[int, int, float]]
) -> List[List[int]]:
    """Union-Find cluster from similarity pairs. Returns lists of indices, size ≥ 2."""
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

    for a, b, _ in pairs:
        union(a, b)

    clusters: Dict[int, List[int]] = {}
    in_any = {x for pair in pairs for x in (pair[0], pair[1])}
    for i in in_any:
        clusters.setdefault(find(i), []).append(i)

    return [sorted(group) for group in clusters.values() if len(group) >= 2]


def max_similarity_for_group(
    indices: List[int], pairs: List[Tuple[int, int, float]]
) -> float:
    """Highest similarity among intra-group pairs (or 1.0 if no recorded pair)."""
    members = set(indices)
    best = 0.0
    for a, b, s in pairs:
        if a in members and b in members and s > best:
            best = s
    return best if best > 0 else 1.0


def find_near_duplicate_groups(
    photos_with_embeddings: List[PhotoFile],
    vectors: np.ndarray,
    threshold: float,
) -> List[Tuple[List[PhotoFile], float]]:
    """Find near-duplicate clusters from embeddings.

    photos_with_embeddings must align with vectors row-by-row (i.e. their
    embedding_index matches their position in this list).
    Returns a list of (members, max_similarity) tuples.
    """
    pairs = find_similar_pairs(vectors, threshold)
    clusters = cluster_pairs(len(photos_with_embeddings), pairs)
    out: List[Tuple[List[PhotoFile], float]] = []
    for cluster in clusters:
        members = [photos_with_embeddings[i] for i in cluster]
        max_sim = max_similarity_for_group(cluster, pairs)
        out.append((members, max_sim))
    return out
