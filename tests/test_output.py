"""Tests for the analytical output formatters (json / text modes)."""

from __future__ import annotations

import json
from pathlib import Path

from photoprune.models import DuplicateGroup, PhotoFile
from photoprune.output import JSON_SCHEMA_VERSION, format_json, format_text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _photo(name: str, *, sharpness: float = 100.0, q: float = 0.5) -> PhotoFile:
    return PhotoFile(
        path=f"/album/{name}",
        size_bytes=2_000_000,
        mtime=0.0,
        width=4000,
        height=3000,
        sharpness=sharpness,
        quality_rank=q,
    )


def _sample_groups() -> list[DuplicateGroup]:
    keep = _photo("best.jpg", sharpness=300.0, q=1.0)
    other = _photo("other.jpg", sharpness=100.0, q=0.4)
    return [
        DuplicateGroup(
            group_id="1",
            detection_type="near",
            members=[other, keep],  # deliberately not in keep-first order
            max_similarity=0.97,
            suggested_keep_path=keep.path,
        )
    ]


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def test_json_schema_basic() -> None:
    groups = _sample_groups()
    out = format_json(
        groups, scanned=5, album_path=Path("/album"), threshold=0.85
    )
    parsed = json.loads(out)
    assert parsed["version"] == JSON_SCHEMA_VERSION
    assert parsed["album_path"] == "/album"
    assert parsed["threshold"] == 0.85
    assert parsed["scanned"] == 5
    assert len(parsed["groups"]) == 1

    g = parsed["groups"][0]
    assert g["group_id"] == "1"
    assert g["detection_type"] == "near"
    assert g["size"] == 2
    assert g["max_similarity"] == 0.97
    assert g["suggested_keep"] == "/album/best.jpg"

    # Members ordered with the suggested keeper first.
    paths = [m["path"] for m in g["members"]]
    assert paths == ["/album/best.jpg", "/album/other.jpg"]
    assert g["members"][0]["is_suggested_keep"] is True
    assert g["members"][1]["is_suggested_keep"] is False


def test_json_handles_empty_album() -> None:
    out = format_json(
        [], scanned=0, album_path=Path("/album"), threshold=0.94
    )
    parsed = json.loads(out)
    assert parsed["scanned"] == 0
    assert parsed["groups"] == []


def test_json_handles_missing_quality_fields() -> None:
    p = PhotoFile(
        path="/x.jpg",
        size_bytes=1,
        mtime=0.0,
        width=1,
        height=1,
        sharpness=None,
        quality_rank=None,
    )
    g = DuplicateGroup(
        group_id="1",
        detection_type="exact",
        members=[p, p],
        max_similarity=1.0,
        suggested_keep_path="/x.jpg",
    )
    out = format_json(
        [g], scanned=1, album_path=Path("/album"), threshold=0.94
    )
    parsed = json.loads(out)
    assert parsed["groups"][0]["members"][0]["sharpness"] is None
    assert parsed["groups"][0]["members"][0]["quality_rank"] is None


def test_json_is_pretty_printed() -> None:
    """Output should be human-readable indented JSON, not minified."""
    out = format_json(
        _sample_groups(),
        scanned=2,
        album_path=Path("/album"),
        threshold=0.85,
    )
    assert "\n" in out
    assert "  " in out  # indent


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------


def test_text_format_groups() -> None:
    out = format_text(
        _sample_groups(),
        scanned=5,
        album_path=Path("/album"),
        threshold=0.85,
    )
    assert "Group 1" in out
    assert "[near]" in out
    assert "max-sim 0.97" in out
    # Suggested keeper is marked.
    assert "KEEP" in out
    # Both members appear.
    assert "/album/best.jpg" in out
    assert "/album/other.jpg" in out
    # Summary line includes scanned + groups count.
    assert "scanned: 5" in out
    assert "groups: 1" in out


def test_text_keeper_appears_before_other_members() -> None:
    out = format_text(
        _sample_groups(),
        scanned=2,
        album_path=Path("/album"),
        threshold=0.85,
    )
    keep_pos = out.find("/album/best.jpg")
    other_pos = out.find("/album/other.jpg")
    assert 0 <= keep_pos < other_pos


def test_text_no_groups() -> None:
    out = format_text(
        [], scanned=10, album_path=Path("/album"), threshold=0.94
    )
    assert "No duplicate groups" in out
    assert "Scanned 10" in out


def test_text_no_groups_no_summary_block() -> None:
    """Empty result should be a short message, not a header + empty body."""
    out = format_text(
        [], scanned=0, album_path=Path("/album"), threshold=0.94
    )
    assert "Group" not in out
    assert "KEEP" not in out
