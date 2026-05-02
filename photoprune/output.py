"""Output formatters for the analytical (`json`, `text`) modes.

These produce a representation of the duplicate groups that is meant to
be consumed by a downstream caller (an AI agent, a script, a human in
a terminal). Nothing here writes files or otherwise persists state —
the caller writes the returned string wherever it likes (typically
stdout).
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import List, Optional

from .models import DuplicateGroup, PhotoFile

# Bump when the JSON schema changes incompatibly.
JSON_SCHEMA_VERSION = "1"


def _round(value: Optional[float], digits: int) -> Optional[float]:
    return round(value, digits) if value is not None else None


def _sorted_members(group: DuplicateGroup) -> List[PhotoFile]:
    """Suggested keeper first, then descending quality rank."""
    return sorted(
        group.members,
        key=lambda m: (
            m.path != group.suggested_keep_path,
            -(m.quality_rank or 0.0),
        ),
    )


def format_json(
    groups: List[DuplicateGroup],
    *,
    scanned: int,
    album_path: Path,
    threshold: float,
) -> str:
    """Stable JSON representation of the grouping result.

    Schema (version 1):

        {
          "version": "1",
          "album_path": "<absolute path>",
          "threshold": <float>,
          "scanned": <int>,
          "groups": [
            {
              "group_id": "<str>",
              "detection_type": "exact" | "near" | "mixed",
              "size": <int>,
              "max_similarity": <float, 0..1>,
              "suggested_keep": "<absolute path>",
              "members": [
                {
                  "path": "<absolute path>",
                  "size_bytes": <int>,
                  "width": <int>,
                  "height": <int>,
                  "sharpness": <float|null>,
                  "quality_rank": <float|null, 0..1>,
                  "is_suggested_keep": <bool>
                },
                ...
              ]
            },
            ...
          ]
        }
    """
    payload = {
        "version": JSON_SCHEMA_VERSION,
        "album_path": str(album_path),
        "threshold": threshold,
        "scanned": scanned,
        "groups": [
            {
                "group_id": g.group_id,
                "detection_type": g.detection_type,
                "size": g.size,
                "max_similarity": _round(g.max_similarity, 4),
                "suggested_keep": g.suggested_keep_path,
                "members": [
                    {
                        "path": p.path,
                        "size_bytes": p.size_bytes,
                        "width": p.width,
                        "height": p.height,
                        "sharpness": _round(p.sharpness, 2),
                        "quality_rank": _round(p.quality_rank, 4),
                        "is_suggested_keep": p.path == g.suggested_keep_path,
                    }
                    for p in _sorted_members(g)
                ],
            }
            for g in groups
        ],
    }
    return _json.dumps(payload, indent=2)


def format_text(
    groups: List[DuplicateGroup],
    *,
    scanned: int,
    album_path: Path,
    threshold: float,
) -> str:
    """Human-readable but greppable text representation."""
    lines: List[str] = []

    if not groups:
        lines.append(
            f"No duplicate groups found in {album_path} (threshold {threshold:.2f})."
        )
        lines.append(f"Scanned {scanned} photo(s).")
        return "\n".join(lines)

    in_groups = sum(g.size for g in groups)
    lines.append(
        f"album:     {album_path}"
    )
    lines.append(
        f"threshold: {threshold:.2f}    scanned: {scanned}    "
        f"groups: {len(groups)}    photos in groups: {in_groups}"
    )
    lines.append("")

    for g in groups:
        lines.append(
            f"Group {g.group_id}  [{g.detection_type}]  "
            f"{g.size} photos  max-sim {g.max_similarity:.2f}"
        )
        for p in _sorted_members(g):
            keep = "KEEP " if p.path == g.suggested_keep_path else "     "
            size_mb = p.size_bytes / (1024 * 1024)
            sharp = f"{p.sharpness:.0f}" if p.sharpness is not None else "—"
            qual = f"{p.quality_rank:.2f}" if p.quality_rank is not None else "—"
            lines.append(
                f"  {keep} {p.path}  "
                f"{p.width}x{p.height}  {size_mb:.1f}MB  "
                f"sharp {sharp}  q {qual}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
