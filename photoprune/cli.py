"""Command-line entry point. Wires the full pipeline together."""

from __future__ import annotations

# faiss-cpu and PyTorch each link their own OpenMP runtime. On macOS
# (and some Linux configs) loading both with multi-threaded OMP causes
# a segfault during faiss search(). Pin OMP to a single thread BEFORE
# either library is imported, then load faiss first.
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import faiss as _faiss  # noqa: E402,F401

try:
    _faiss.omp_set_num_threads(1)
except Exception:
    pass

import shutil  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import webbrowser  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Dict, Iterable, List, Optional, Tuple  # noqa: E402

import click  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from tqdm import tqdm  # noqa: E402

from . import __version__
from .cleaner import cleanup as run_cleanup
from .embedder import embed_photos
from .hasher import compute_phashes, group_by_phash
from .indexer import find_near_duplicate_groups
from .models import Config, DetectionType, DuplicateGroup, PhotoFile
from .reporter import render_report
from .scanner import heic_supported, scan


def _compute_sharpness(path: str) -> float | None:
    try:
        import cv2
    except Exception:
        return None
    try:
        with Image.open(path) as img:
            arr = np.asarray(img.convert("L"), dtype=np.uint8)
        if arr.ndim != 2 or arr.size == 0:
            return None
        return float(cv2.Laplacian(arr, cv2.CV_64F).var())
    except Exception:
        return None


def _add_sharpness(photos: Iterable[PhotoFile], *, show_progress: bool = True) -> None:
    iterator = list(photos)
    if show_progress:
        iterator = tqdm(iterator, desc="sharpness", unit="img")
    for p in iterator:
        if p.sharpness is None:
            p.sharpness = _compute_sharpness(p.path)


def _quality_rank(p: PhotoFile, max_s: float, max_r: float, max_f: float) -> float:
    s = (p.sharpness or 0.0) / max_s if max_s > 0 else 0.0
    r = p.resolution / max_r if max_r > 0 else 0.0
    f = p.size_bytes / max_f if max_f > 0 else 0.0
    return 0.5 * s + 0.3 * r + 0.2 * f


def _pick_keep_and_rank(group: List[PhotoFile]) -> str:
    max_s = max((p.sharpness or 0.0) for p in group)
    max_r = max(p.resolution for p in group)
    max_f = max(p.size_bytes for p in group)
    best_path = group[0].path
    best_score = -1.0
    for p in group:
        score = _quality_rank(p, max_s, max_r, max_f)
        p.quality_rank = score
        if score > best_score:
            best_score = score
            best_path = p.path
    return best_path


def _merge_groups(
    photos: List[PhotoFile],
    exact_groups: List[List[PhotoFile]],
    near_groups: List[Tuple[List[PhotoFile], float]],
) -> List[DuplicateGroup]:
    """Merge exact and near groups via Union-Find on photo path."""
    path_to_idx: Dict[str, int] = {p.path: i for i, p in enumerate(photos)}
    n = len(photos)
    parent = list(range(n))
    in_exact: set[int] = set()
    in_near: set[int] = set()
    near_max: Dict[int, float] = {}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for grp in exact_groups:
        idxs = [path_to_idx[p.path] for p in grp if p.path in path_to_idx]
        in_exact.update(idxs)
        for i in idxs[1:]:
            union(idxs[0], i)

    for members, sim in near_groups:
        idxs = [path_to_idx[p.path] for p in members if p.path in path_to_idx]
        in_near.update(idxs)
        for i in idxs[1:]:
            union(idxs[0], i)
        for i in idxs:
            near_max[find(i)] = max(near_max.get(find(i), 0.0), sim)

    clusters: Dict[int, List[int]] = {}
    relevant = in_exact | in_near
    for i in relevant:
        clusters.setdefault(find(i), []).append(i)

    out: List[DuplicateGroup] = []
    for gid, (root, members) in enumerate(
        sorted(clusters.items(), key=lambda kv: -len(kv[1])), start=1
    ):
        if len(members) < 2:
            continue
        photo_members = [photos[i] for i in members]
        has_exact = any(i in in_exact for i in members)
        has_near = any(i in in_near for i in members)
        if has_exact and has_near:
            detection: DetectionType = "mixed"
        elif has_exact:
            detection = "exact"
        else:
            detection = "near"

        max_sim = 1.0 if detection == "exact" else near_max.get(root, 1.0 if has_exact else 0.0)
        keep = _pick_keep_and_rank(photo_members)
        out.append(
            DuplicateGroup(
                group_id=str(gid),
                detection_type=detection,
                members=photo_members,
                max_similarity=max_sim,
                suggested_keep_path=keep,
            )
        )
    return out


def _model_already_cached(model: str) -> bool:
    """Best-effort check: are this model's weights already on disk?"""
    if model == "clip":
        cache = Path.home() / ".cache" / "huggingface" / "hub"
        if not cache.exists():
            return False
        for child in cache.iterdir():
            name = child.name.lower()
            if "clip" in name and "vit" in name and "32" in name:
                return True
        return False
    if model == "mobilenet":
        cache = Path.home() / ".cache" / "torch" / "hub" / "checkpoints"
        if not cache.exists():
            return False
        return any("mobilenet_v2" in p.name for p in cache.iterdir())
    return True


def _model_load_notice(model: str) -> None:
    if _model_already_cached(model):
        click.echo(f"Loading {model} model from cache ...")
        return
    size = "~340 MB" if model == "clip" else "~14 MB"
    click.echo(
        f"Loading {model} model — first-run download ({size}, then cached)."
    )


def _wait_for_selections(
    output_dir: Path, *, started_at: float, poll_secs: float = 1.0
) -> Optional[Path]:
    """Block until a fresh selections.json appears, or KeyboardInterrupt.

    Watches the output dir and the user's Downloads folder. A file is
    considered fresh if its mtime is newer than `started_at`, so old
    leftovers from previous runs are ignored.
    """
    candidates_globs = [
        (output_dir, "selections*.json"),
        (Path.home() / "Downloads", "selections*.json"),
    ]
    click.echo(
        "\nWaiting for selections.json — review the report and click 'Save Selections'."
    )
    click.echo("(Ctrl-C to skip cleanup; you can run `photoprune cleanup` later.)")

    try:
        while True:
            best: Optional[Tuple[float, Path]] = None
            for folder, pattern in candidates_globs:
                if not folder.exists():
                    continue
                for match in folder.glob(pattern):
                    try:
                        mt = match.stat().st_mtime
                    except OSError:
                        continue
                    if mt < started_at:
                        continue
                    if best is None or mt > best[0]:
                        best = (mt, match)
            if best is not None:
                # Avoid racing the browser's download write — wait until
                # the file size is stable for two ticks.
                stable = best[1]
                first_size = stable.stat().st_size
                time.sleep(poll_secs)
                if stable.exists() and stable.stat().st_size == first_size:
                    return stable
            time.sleep(poll_secs)
    except KeyboardInterrupt:
        return None


def _print_summary(
    *,
    scanned: int,
    groups: int,
    photos_in_groups: int,
    removed: int,
    output_dir: Path,
) -> None:
    bar = "─" * 48
    click.echo()
    click.echo(bar)
    click.echo(f"  scanned:   {scanned} photo(s)")
    click.echo(f"  groups:    {groups} ({photos_in_groups} photos in groups)")
    if removed:
        click.echo(f"  removed:   {removed} file(s) → {output_dir}/_trash")
    click.echo(bar)


def _run_scan(
    cfg: Config,
    *,
    auto_open: bool = True,
    wait_for_save: bool = True,
) -> Path:
    if not cfg.album_path.exists():
        raise click.UsageError(f"Album path does not exist: {cfg.album_path}")
    if not cfg.album_path.is_dir():
        raise click.UsageError(f"Album path is not a directory: {cfg.album_path}")

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()

    click.echo(f"Scanning {cfg.album_path} ...")
    photos = scan(cfg.album_path, exclude_dirs=[cfg.output_dir])
    if not photos:
        click.echo("No supported image files found.")
        if not heic_supported():
            click.echo("(HEIC support disabled — install with: pip install pillow-heif)")
        empty_report = render_report(
            [], cfg.output_dir / "duplicates_report.html", album_path=cfg.album_path
        )
        return empty_report

    click.echo(f"Found {len(photos)} image(s).")

    compute_phashes(photos)
    exact_groups = group_by_phash(photos, threshold=cfg.phash_threshold)

    _model_load_notice(cfg.model)
    vectors = embed_photos(
        photos,
        cfg.output_dir,
        cfg.model,
        use_cache=not cfg.no_cache,
    )

    photos_with_emb = [p for p in photos if p.embedding_index is not None]
    if vectors.shape[0] != len(photos_with_emb):
        ordered = sorted(photos_with_emb, key=lambda p: p.embedding_index or 0)
        photos_with_emb = ordered

    near_groups = find_near_duplicate_groups(
        photos_with_emb, vectors, threshold=cfg.threshold
    )

    _add_sharpness(photos)
    groups = _merge_groups(photos, exact_groups, near_groups)
    photos_in_groups = sum(g.size for g in groups)

    report_path = render_report(
        groups,
        cfg.output_dir / "duplicates_report.html",
        album_path=cfg.album_path,
    )

    if not groups:
        click.echo("\nNo duplicate groups found.")
        _print_summary(
            scanned=len(photos),
            groups=0,
            photos_in_groups=0,
            removed=0,
            output_dir=cfg.output_dir,
        )
        return report_path

    click.echo(f"\nFound {len(groups)} duplicate group(s) covering {photos_in_groups} photos.")
    click.echo(f"Report: {report_path}")

    if auto_open:
        webbrowser.open(report_path.as_uri())

    removed = 0
    if wait_for_save:
        sel = _wait_for_selections(cfg.output_dir, started_at=started_at)
        if sel is None:
            click.echo("\nSkipped cleanup. Apply later with:")
            click.echo(f"  photoprune cleanup {cfg.output_dir}")
            return report_path

        target = cfg.output_dir / "selections.json"
        if sel.resolve() != target.resolve():
            shutil.move(str(sel), str(target))
        click.echo(f"Selections received: {target}")
        moved, skipped, audit = run_cleanup(cfg.output_dir)
        removed = moved
        click.echo(f"Moved {moved} file(s) to {cfg.output_dir}/_trash")
        if skipped:
            click.echo(f"Skipped {skipped} file(s) (see {audit})")
    else:
        click.echo("Open the report, click 'Save Selections', then run:")
        click.echo(f"  photoprune cleanup {cfg.output_dir}")

    _print_summary(
        scanned=len(photos),
        groups=len(groups),
        photos_in_groups=photos_in_groups,
        removed=removed,
        output_dir=cfg.output_dir,
    )
    return report_path


@click.command("scan")
@click.argument("album_path", type=click.Path(), required=False, default=None)
@click.option(
    "--model",
    type=click.Choice(["clip", "mobilenet"], case_sensitive=False),
    default="clip",
    show_default=True,
    help="Embedding model: clip (accurate) or mobilenet (fast).",
)
@click.option(
    "--threshold",
    type=click.FloatRange(0.0, 1.0),
    default=0.94,
    show_default=True,
    help="Cosine similarity cutoff for near-duplicate detection.",
)
@click.option(
    "--phash-threshold",
    type=click.IntRange(0, 64),
    default=10,
    show_default=True,
    help="Hamming-distance cutoff for perceptual-hash duplicate detection.",
)
@click.option(
    "--output-dir",
    type=click.Path(),
    default=None,
    help="Where to write report, cache, and trash. Default: <album>/.photoprune/",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Re-encode all photos from scratch, ignoring cached embeddings.",
)
@click.option(
    "--no-open",
    is_flag=True,
    default=False,
    help="Do not auto-open the HTML report in a browser.",
)
@click.option(
    "--no-wait",
    is_flag=True,
    default=False,
    help="Don't block waiting for selections.json. Print review instructions and exit.",
)
def scan_cmd(
    album_path: Optional[str],
    model: str,
    threshold: float,
    phash_threshold: int,
    output_dir: Optional[str],
    no_cache: bool,
    no_open: bool,
    no_wait: bool,
) -> None:
    """Scan ALBUM_PATH (default: current directory) for duplicates."""
    album = Path(album_path).expanduser() if album_path else Path.cwd()
    out = Path(output_dir).expanduser() if output_dir else album / ".photoprune"

    interactive = sys.stdout.isatty() and sys.stdin.isatty()
    auto_open = not no_open and interactive
    wait = not no_wait and interactive

    cfg = Config(
        album_path=album,
        output_dir=out,
        model=model.lower(),
        threshold=threshold,
        phash_threshold=phash_threshold,
        no_cache=no_cache,
        open_report=auto_open,
    )
    _run_scan(cfg, auto_open=auto_open, wait_for_save=wait)


@click.command("cleanup")
@click.argument("output_dir", type=click.Path(file_okay=False, exists=True))
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be moved, but don't move anything.",
)
def cleanup_cmd(output_dir: str, dry_run: bool) -> None:
    """Apply selections.json — move flagged files to <output_dir>/_trash/."""
    moved, skipped, audit = run_cleanup(Path(output_dir), dry_run=dry_run)
    label = "would move" if dry_run else "moved"
    click.echo(f"{label}: {moved} file(s)")
    if skipped:
        click.echo(f"skipped: {skipped} file(s)")
    click.echo(f"audit log: {audit}")


class _DefaultGroup(click.Group):
    """Click group that runs `scan` whenever no subcommand is named.

    Lets users type:
      photoprune                       # scan cwd
      photoprune /path/to/photos       # scan that path
      photoprune --threshold 0.85      # scan cwd with options
      photoprune cleanup ./out         # explicit subcommand still works
    """

    _DEFAULT = "scan"
    _GROUP_FLAGS = {"--help", "-h", "--version"}

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if not args:
            args = [self._DEFAULT]
        elif args[0] in self._GROUP_FLAGS or args[0] in self.commands:
            pass
        else:
            args = [self._DEFAULT, *args]
        return super().parse_args(ctx, args)


@click.group(cls=_DefaultGroup)
@click.version_option(__version__, prog_name="photoprune")
def main() -> None:
    """PhotoPrune — find near-duplicate photos in a directory.

    \b
    Most common usage — cd into your album and just run:

        photoprune

    PhotoPrune scans the current directory, opens a review report in your
    browser, waits for you to click 'Save Selections', then moves the
    flagged files to <album>/.photoprune/_trash/. Originals are never
    hard-deleted.

    \b
    Other forms:
        photoprune /path/to/photos          # scan a different directory
        photoprune --no-wait                # scan only; review later
        photoprune cleanup OUTPUT_DIR       # apply a saved selections.json
    """


main.add_command(scan_cmd)
main.add_command(cleanup_cmd)


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
