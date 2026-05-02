import json
from pathlib import Path

from photoprune.cleaner import cleanup


def test_cleanup_moves_selected_files(tmp_path: Path, album_dir: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    target = album_dir / "a_copy.jpg"
    assert target.exists()

    selections = {"remove": [str(target)]}
    (output_dir / "selections.json").write_text(json.dumps(selections))

    moved, skipped, audit = cleanup(output_dir)

    assert moved == 1
    assert skipped == 0
    assert not target.exists()  # original moved
    trash = list((output_dir / "_trash").rglob("a_copy.jpg"))
    assert len(trash) == 1  # exists under trash
    assert audit.exists()


def test_cleanup_dry_run_does_not_move(tmp_path: Path, album_dir: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    target = album_dir / "a_copy.jpg"

    (output_dir / "selections.json").write_text(json.dumps({"remove": [str(target)]}))
    moved, skipped, _ = cleanup(output_dir, dry_run=True)
    assert moved == 1
    assert target.exists()  # nothing actually moved


def test_cleanup_handles_missing_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "selections.json").write_text(
        json.dumps({"remove": [str(tmp_path / "ghost.jpg")]})
    )
    moved, skipped, _ = cleanup(output_dir)
    assert moved == 0
    assert skipped == 1
