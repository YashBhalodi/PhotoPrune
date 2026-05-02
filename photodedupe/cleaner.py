"""Safe file mover for cleanup. Files go to _trash/, never deleted."""

from __future__ import annotations

import csv
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

_AUDIT_FIELDS = ["timestamp", "original_path", "trash_path", "size_bytes", "status"]


def _common_root(paths: List[Path]) -> Path:
    if not paths:
        return Path("/")
    if len(paths) == 1:
        return paths[0].parent
    try:
        return Path(os.path.commonpath([str(p) for p in paths]))
    except ValueError:
        # Different drives on Windows.
        return Path("/")


def _trash_path_for(original: Path, common: Path, trash_root: Path) -> Path:
    try:
        rel = original.relative_to(common)
    except ValueError:
        # Fall back to using filename only.
        rel = Path(original.name)
    return trash_root / rel


def _ensure_unique(target: Path) -> Path:
    """Append a numeric suffix if `target` already exists."""
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    parent = target.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def cleanup(output_dir: Path, *, dry_run: bool = False) -> Tuple[int, int, Path]:
    """Read selections.json, move flagged files to _trash/, write audit_log.csv.

    Returns (moved, skipped, audit_log_path).
    """
    output_dir = Path(output_dir).expanduser().resolve()
    selections_path = output_dir / "selections.json"
    if not selections_path.exists():
        raise FileNotFoundError(
            f"selections.json not found in {output_dir}. "
            f"Open the report and click 'Save Selections' first."
        )

    payload = json.loads(selections_path.read_text())
    raw_paths = payload.get("remove", [])
    if not isinstance(raw_paths, list):
        raise ValueError("selections.json: 'remove' must be a list of paths")

    paths = [Path(p) for p in raw_paths]
    existing = [p for p in paths if p.exists()]
    common = _common_root(existing) if existing else Path("/")
    trash_root = output_dir / "_trash"
    audit_log = output_dir / "audit_log.csv"

    moved = 0
    skipped = 0
    rows: List[dict] = []
    now = datetime.now().isoformat(timespec="seconds")

    for original in paths:
        if not original.exists():
            skipped += 1
            rows.append({
                "timestamp": now,
                "original_path": str(original),
                "trash_path": "",
                "size_bytes": 0,
                "status": "missing",
            })
            continue

        target = _ensure_unique(_trash_path_for(original, common, trash_root))
        try:
            size = original.stat().st_size
        except OSError:
            size = 0

        status = "moved"
        if dry_run:
            status = "dry-run"
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(original), str(target))
            except Exception as exc:
                status = f"error: {exc}"
                skipped += 1
                rows.append({
                    "timestamp": now,
                    "original_path": str(original),
                    "trash_path": str(target),
                    "size_bytes": size,
                    "status": status,
                })
                continue

        moved += 1
        rows.append({
            "timestamp": now,
            "original_path": str(original),
            "trash_path": str(target),
            "size_bytes": size,
            "status": status,
        })

    write_header = not audit_log.exists()
    with audit_log.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_AUDIT_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)

    return moved, skipped, audit_log
