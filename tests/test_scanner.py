from pathlib import Path

from photoprune.scanner import scan


def test_scan_finds_all_jpegs(album_dir: Path) -> None:
    photos = scan(album_dir)
    paths = sorted(p.path for p in photos)
    assert len(photos) == 5
    assert all(p.endswith(".jpg") for p in paths)
    for p in photos:
        assert p.size_bytes > 0
        assert p.width == 200 and p.height == 200


def test_scan_skips_non_image(album_dir: Path) -> None:
    (album_dir / "notes.txt").write_text("hello")
    photos = scan(album_dir)
    assert len(photos) == 5  # txt file ignored
