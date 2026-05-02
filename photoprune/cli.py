"""Command-line entry point.

Thin orchestration layer over `photoprune.pipeline`. Handles arg parsing,
TTY detection, the watch-and-cleanup loop, and the summary printout.
The actual grouping logic lives in `pipeline.py`.

The faiss/torch import-order workaround and the model-cache redirect
both live in `photoprune/__init__.py` so they apply to library use too.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional, Tuple

import click

from . import __version__
from .cleaner import cleanup as run_cleanup
from .models import Config
from .pipeline import find_duplicate_groups
from .reporter import render_report
from .scanner import heic_supported, scan


# ---------------------------------------------------------------------------
# CLI display helpers
# ---------------------------------------------------------------------------


def _clip_already_cached() -> bool:
    """Best-effort check: are the CLIP weights already on disk?

    Honors $HF_HOME (the package init redirects this into the install
    prefix). Falls back to the platform default.
    """
    hf_home = os.environ.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")
    cache = Path(hf_home) / "hub"
    if not cache.exists():
        return False
    for child in cache.iterdir():
        name = child.name.lower()
        if "clip" in name and "vit" in name and "32" in name:
            return True
    return False


def _model_load_notice() -> None:
    if _clip_already_cached():
        click.echo("Loading model from cache ...")
        return
    click.echo("Loading model — first-run download (~340 MB, then cached).")


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


# ---------------------------------------------------------------------------
# scan command
# ---------------------------------------------------------------------------


def _run_scan(cfg: Config) -> Path:
    if not cfg.album_path.exists():
        raise click.UsageError(f"Album path does not exist: {cfg.album_path}")
    if not cfg.album_path.is_dir():
        raise click.UsageError(f"Album path is not a directory: {cfg.album_path}")

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    interactive = sys.stdout.isatty() and sys.stdin.isatty()

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

    _model_load_notice()
    groups = find_duplicate_groups(
        photos,
        output_dir=cfg.output_dir,
        threshold=cfg.threshold,
    )
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

    if interactive:
        webbrowser.open(report_path.as_uri())

    removed = 0
    if interactive:
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
    "--threshold",
    type=click.FloatRange(0.0, 1.0),
    default=0.94,
    show_default=True,
    help="Cosine similarity cutoff for near-duplicate detection.",
)
@click.option(
    "--output-dir",
    type=click.Path(),
    default=None,
    help="Where to write report, cache, and trash. Default: <album>/.photoprune/",
)
def scan_cmd(
    album_path: Optional[str],
    threshold: float,
    output_dir: Optional[str],
) -> None:
    """Scan ALBUM_PATH (default: current directory) for duplicates."""
    album = Path(album_path).expanduser() if album_path else Path.cwd()
    out = Path(output_dir).expanduser() if output_dir else album / ".photoprune"

    cfg = Config(
        album_path=album,
        output_dir=out,
        threshold=threshold,
    )
    _run_scan(cfg)


# ---------------------------------------------------------------------------
# cleanup command
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Top-level group
# ---------------------------------------------------------------------------


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
        photoprune --threshold 0.90         # flag more aggressively
        photoprune cleanup OUTPUT_DIR       # apply a saved selections.json
    """


main.add_command(scan_cmd)
main.add_command(cleanup_cmd)


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
