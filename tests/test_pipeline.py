"""Tests for the grouping pipeline.

Tests the merge / quality-scoring logic directly with crafted inputs (no
model load), and tests the public `find_duplicate_groups` orchestration
end-to-end with the embedder stubbed out.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np
import pytest

from photoprune.models import DuplicateGroup, PhotoFile
from photoprune.pipeline import (
    _add_sharpness,
    _merge_groups,
    _pick_keep_and_rank,
    _quality_rank,
    find_duplicate_groups,
)
from photoprune.scanner import scan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _photo(
    path: str,
    *,
    width: int = 4000,
    height: int = 3000,
    size_bytes: int = 1_000_000,
    sharpness: float | None = 100.0,
) -> PhotoFile:
    return PhotoFile(
        path=path,
        size_bytes=size_bytes,
        mtime=0.0,
        width=width,
        height=height,
        sharpness=sharpness,
    )


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------


def test_quality_rank_picks_sharpest_when_others_equal() -> None:
    a = _photo("a.jpg", sharpness=100.0)
    b = _photo("b.jpg", sharpness=200.0)  # twice as sharp
    keep = _pick_keep_and_rank([a, b])
    assert keep == "b.jpg"
    assert b.quality_rank is not None and a.quality_rank is not None
    assert b.quality_rank > a.quality_rank


def test_quality_rank_balances_resolution_and_filesize() -> None:
    # a is sharper but tiny, b is less sharp but huge res + filesize.
    a = _photo("a.jpg", width=200, height=200, size_bytes=10_000, sharpness=500.0)
    b = _photo("b.jpg", width=4000, height=3000, size_bytes=5_000_000, sharpness=100.0)
    # sharpness weight 0.5 vs (resolution 0.3 + filesize 0.2 = 0.5) — b should win
    # because it dominates two of three factors at equal weight.
    keep = _pick_keep_and_rank([a, b])
    assert keep == "b.jpg"


def test_quality_rank_handles_missing_sharpness() -> None:
    # If sharpness is None on every photo, falls back to res + size only.
    a = _photo("a.jpg", width=2000, height=1500, size_bytes=500_000, sharpness=None)
    b = _photo("b.jpg", width=4000, height=3000, size_bytes=2_000_000, sharpness=None)
    keep = _pick_keep_and_rank([a, b])
    assert keep == "b.jpg"


def test_quality_rank_zero_inputs_dont_crash() -> None:
    a = _photo("a.jpg", width=0, height=0, size_bytes=0, sharpness=0.0)
    score = _quality_rank(a, max_s=0.0, max_r=0.0, max_f=0.0)
    assert score == 0.0


# ---------------------------------------------------------------------------
# Merge: union-find over exact + near results
# ---------------------------------------------------------------------------


def test_merge_only_exact_groups() -> None:
    photos = [_photo("a.jpg"), _photo("a_copy.jpg"), _photo("c.jpg")]
    groups = _merge_groups(
        photos, exact_groups=[[photos[0], photos[1]]], near_groups=[]
    )
    assert len(groups) == 1
    assert groups[0].detection_type == "exact"
    assert groups[0].size == 2
    assert groups[0].max_similarity == 1.0


def test_merge_only_near_groups() -> None:
    photos = [_photo("a.jpg"), _photo("b.jpg"), _photo("c.jpg")]
    groups = _merge_groups(
        photos,
        exact_groups=[],
        near_groups=[([photos[0], photos[1]], 0.96)],
    )
    assert len(groups) == 1
    assert groups[0].detection_type == "near"
    assert groups[0].max_similarity == pytest.approx(0.96)


def test_merge_unions_overlapping_exact_and_near_into_mixed() -> None:
    a = _photo("a.jpg")
    b = _photo("b.jpg")
    c = _photo("c.jpg")
    photos = [a, b, c]
    # a and b are exact dups; b and c are near dups → merged single group.
    groups = _merge_groups(
        photos, exact_groups=[[a, b]], near_groups=[([b, c], 0.97)]
    )
    assert len(groups) == 1
    assert groups[0].detection_type == "mixed"
    assert groups[0].size == 3
    assert {p.path for p in groups[0].members} == {"a.jpg", "b.jpg", "c.jpg"}


def test_merge_keeps_groups_separate_when_no_overlap() -> None:
    a, b, c, d = (_photo(f"{n}.jpg") for n in "abcd")
    groups = _merge_groups(
        [a, b, c, d],
        exact_groups=[[a, b]],
        near_groups=[([c, d], 0.95)],
    )
    assert len(groups) == 2
    detection_types = sorted(g.detection_type for g in groups)
    assert detection_types == ["exact", "near"]


def test_merge_drops_singletons() -> None:
    # An "exact group" of size 1 (which shouldn't happen but be defensive):
    photos = [_photo("a.jpg"), _photo("b.jpg")]
    groups = _merge_groups(photos, exact_groups=[[photos[0]]], near_groups=[])
    assert groups == []


def test_merge_orders_largest_first() -> None:
    photos = [_photo(f"p{i}.jpg") for i in range(5)]
    groups = _merge_groups(
        photos,
        exact_groups=[
            [photos[0], photos[1]],            # size 2
            [photos[2], photos[3], photos[4]], # size 3
        ],
        near_groups=[],
    )
    assert [g.size for g in groups] == [3, 2]


def test_merge_picks_keeper_per_group() -> None:
    a = _photo("a.jpg", sharpness=50.0)
    b = _photo("b.jpg", sharpness=200.0)
    groups = _merge_groups([a, b], exact_groups=[[a, b]], near_groups=[])
    assert groups[0].suggested_keep_path == "b.jpg"


# ---------------------------------------------------------------------------
# Public entry point — full orchestration with a stubbed embedder
# ---------------------------------------------------------------------------


def test_find_duplicate_groups_end_to_end_with_stubbed_embedder(
    monkeypatch: pytest.MonkeyPatch, album_dir: Path, tmp_path: Path
) -> None:
    """Run the full pipeline against the synthetic-image fixtures.

    We stub `embed_photos` so the test doesn't need to download / load
    a real CLIP model. The stub returns a vector that's nearly identical
    for `b.jpg` and `b_variant.jpg` (so they group as near-dups), and
    distinct from everything else.
    """
    photos = scan(album_dir)
    assert len(photos) == 5

    # Map filename → (vector, is_near_dup_of_b)
    def _stub_embed_photos(photos, output_dir, model, *, use_cache, show_progress=True):
        rng = np.random.default_rng(0)
        n = len(photos)
        dim = 32
        # Start with random-but-distinct vectors.
        matrix = rng.standard_normal((n, dim)).astype(np.float32)
        # Force `b.jpg` and `b_variant.jpg` to be 99% similar (cosine).
        b_idx = next(i for i, p in enumerate(photos) if p.filename == "b.jpg")
        v_idx = next(i for i, p in enumerate(photos) if p.filename == "b_variant.jpg")
        base = rng.standard_normal(dim).astype(np.float32)
        matrix[b_idx] = base
        matrix[v_idx] = base + rng.standard_normal(dim).astype(np.float32) * 0.02
        # Normalize for cosine = inner product.
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
        # Set embedding_index to match row positions, like the real embedder.
        for i, p in enumerate(photos):
            p.embedding_index = i
        return matrix

    monkeypatch.setattr("photoprune.pipeline.embed_photos", _stub_embed_photos)

    groups = find_duplicate_groups(
        photos,
        output_dir=tmp_path,
        threshold=0.95,
        phash_threshold=10,
        progress=False,
    )

    # Expect at least the byte-identical pair (a.jpg / a_copy.jpg) to land in one
    # group. The stubbed embeddings put b.jpg / b_variant.jpg close enough that
    # they may cluster too — either as a separate "near" group or merged with
    # the pHash near-match (depending on exactly how the synthetic noise lands).
    paths_in_groups = {p.path for g in groups for p in g.members}
    a_paths = {p.path for p in photos if p.filename in {"a.jpg", "a_copy.jpg"}}
    assert a_paths.issubset(paths_in_groups)
    # Quality rank populated on every grouped photo.
    for g in groups:
        for p in g.members:
            assert p.quality_rank is not None
        assert g.suggested_keep_path in {p.path for p in g.members}


def test_find_duplicate_groups_no_dupes(
    monkeypatch: pytest.MonkeyPatch, album_dir: Path, tmp_path: Path
) -> None:
    """High threshold + dissimilar embeddings → no near groups returned.

    Byte-identical `a.jpg` / `a_copy.jpg` still group via pHash, so we
    expect exactly 1 group of detection_type 'exact'.
    """
    photos = scan(album_dir)

    def _orthogonal_embed(photos, output_dir, model, *, use_cache, show_progress=True):
        n = len(photos)
        # Identity-ish: each photo gets its own basis vector → cosine 0 with others.
        matrix = np.eye(n, 32, dtype=np.float32)
        for i, p in enumerate(photos):
            p.embedding_index = i
        return matrix

    monkeypatch.setattr("photoprune.pipeline.embed_photos", _orthogonal_embed)

    groups = find_duplicate_groups(
        photos,
        output_dir=tmp_path,
        threshold=0.99,
        phash_threshold=0,  # only byte-identical pHashes group
        progress=False,
    )
    assert len(groups) == 1
    assert groups[0].detection_type == "exact"
    assert {p.filename for p in groups[0].members} == {"a.jpg", "a_copy.jpg"}


def test_find_duplicate_groups_skips_sharpness_on_request(
    monkeypatch: pytest.MonkeyPatch, album_dir: Path, tmp_path: Path
) -> None:
    photos = scan(album_dir)

    def _stub_embed(photos, output_dir, model, *, use_cache, show_progress=True):
        n = len(photos)
        matrix = np.eye(n, 32, dtype=np.float32)
        for i, p in enumerate(photos):
            p.embedding_index = i
        return matrix

    monkeypatch.setattr("photoprune.pipeline.embed_photos", _stub_embed)

    find_duplicate_groups(
        photos,
        output_dir=tmp_path,
        threshold=0.99,
        phash_threshold=0,
        compute_sharpness=False,
        progress=False,
    )
    # When sharpness is skipped, no photo should have it set.
    for p in photos:
        assert p.sharpness is None


# ---------------------------------------------------------------------------
# Library import smoke
# ---------------------------------------------------------------------------


def test_top_level_imports() -> None:
    """`from photoprune import find_duplicate_groups` should work."""
    import photoprune

    assert callable(photoprune.find_duplicate_groups)
    assert "find_duplicate_groups" in photoprune.__all__
    assert "scan" in photoprune.__all__
    assert "DuplicateGroup" in photoprune.__all__
