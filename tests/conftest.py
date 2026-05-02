"""Shared fixtures: synthetic test images that don't require model downloads."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def _make_pattern_image(seed: int, size: tuple[int, int] = (200, 200)) -> Image.Image:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, size=(size[1], size[0], 3), dtype=np.uint8)
    return Image.fromarray(arr, "RGB")


def _slight_variant(img: Image.Image) -> Image.Image:
    arr = np.asarray(img).copy()
    # Small per-pixel jitter to simulate a near-duplicate (same scene, different shot).
    noise = np.random.default_rng(42).integers(-5, 6, size=arr.shape, dtype=np.int16)
    arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


@pytest.fixture
def album_dir(tmp_path: Path) -> Path:
    """Create a small album with: an exact-duplicate pair, a near-dup pair, and a unique image."""
    album = tmp_path / "album"
    album.mkdir()

    img_a = _make_pattern_image(seed=1)
    img_a.save(album / "a.jpg", "JPEG", quality=92)
    img_a.save(album / "a_copy.jpg", "JPEG", quality=92)  # exact duplicate

    img_b = _make_pattern_image(seed=2)
    img_b.save(album / "b.jpg", "JPEG", quality=92)
    _slight_variant(img_b).save(album / "b_variant.jpg", "JPEG", quality=92)

    img_c = _make_pattern_image(seed=999)
    img_c.save(album / "unique.jpg", "JPEG", quality=92)

    return album


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    out.mkdir()
    yield out
    shutil.rmtree(out, ignore_errors=True)
