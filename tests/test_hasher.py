from pathlib import Path

from photodedupe.hasher import compute_phashes, group_by_phash
from photodedupe.scanner import scan


def test_phash_groups_exact_duplicates(album_dir: Path) -> None:
    photos = scan(album_dir)
    compute_phashes(photos, show_progress=False)
    for p in photos:
        assert p.phash is not None and len(p.phash) > 0

    # With threshold 0, only true exact-match hashes group.
    groups = group_by_phash(photos, threshold=0)
    flat = {p.path for grp in groups for p in grp}
    # a.jpg and a_copy.jpg are byte-identical → same hash.
    assert any(path.endswith("a.jpg") for path in flat)
    assert any(path.endswith("a_copy.jpg") for path in flat)


def test_phash_grouping_threshold_includes_near(album_dir: Path) -> None:
    photos = scan(album_dir)
    compute_phashes(photos, show_progress=False)
    # Looser threshold should find b.jpg / b_variant.jpg as related too.
    groups = group_by_phash(photos, threshold=20)
    sizes = sorted(len(g) for g in groups)
    assert sum(sizes) >= 2
