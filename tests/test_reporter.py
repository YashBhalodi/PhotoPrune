from pathlib import Path

from photoprune.models import DuplicateGroup, PhotoFile
from photoprune.reporter import render_report
from photoprune.scanner import scan


def test_report_is_self_contained(album_dir: Path, tmp_path: Path) -> None:
    photos = scan(album_dir)
    group = DuplicateGroup(
        group_id="1",
        detection_type="exact",
        members=photos[:2],
        max_similarity=1.0,
        suggested_keep_path=photos[0].path,
    )
    out = tmp_path / "report.html"
    render_report([group], out, album_path=album_dir, show_progress=False)

    text = out.read_text()
    assert "data:image/jpeg;base64," in text
    # No external CDN references.
    assert "https://cdn" not in text
    assert "<title>PhotoPrune" in text


def test_report_handles_empty(tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    render_report([], out, album_path=tmp_path, show_progress=False)
    text = out.read_text()
    assert "No duplicate groups found" in text
