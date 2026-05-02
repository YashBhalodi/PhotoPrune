import numpy as np

from photoprune.indexer import cluster_pairs, find_similar_pairs


def _normalize(x: np.ndarray) -> np.ndarray:
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def test_find_similar_pairs_basic() -> None:
    rng = np.random.default_rng(0)
    base_a = rng.standard_normal(64).astype(np.float32)
    base_b = rng.standard_normal(64).astype(np.float32)
    near_a = base_a + rng.standard_normal(64).astype(np.float32) * 0.01
    far = rng.standard_normal(64).astype(np.float32)

    vectors = _normalize(np.stack([base_a, near_a, base_b, far]))
    pairs = find_similar_pairs(vectors, threshold=0.95)

    pair_set = {(a, b) for a, b, _ in pairs}
    assert (0, 1) in pair_set
    assert (0, 3) not in pair_set
    assert (1, 3) not in pair_set


def test_cluster_pairs_unions_transitively() -> None:
    pairs = [(0, 1, 0.99), (1, 2, 0.97), (4, 5, 0.96)]
    clusters = cluster_pairs(6, pairs)
    cluster_sets = [set(c) for c in clusters]
    assert {0, 1, 2} in cluster_sets
    assert {4, 5} in cluster_sets
    assert all(3 not in c for c in cluster_sets)
