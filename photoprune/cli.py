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
import tempfile
import time
import webbrowser
from pathlib import Path
from typing import Optional, Tuple

import click

from . import __version__
from .cleaner import cleanup as run_cleanup
from .models import Config
from .output import format_json, format_text
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


def _resolve_album(album_path: Optional[str]) -> Path:
    return Path(album_path).expanduser() if album_path else Path.cwd()


def _validate_album(album: Path) -> None:
    if not album.exists():
        raise click.UsageError(f"Album path does not exist: {album}")
    if not album.is_dir():
        raise click.UsageError(f"Album path is not a directory: {album}")


def _run_analytical(
    *, album: Path, threshold: float, fmt: str
) -> None:
    """Run the pipeline and emit results to stdout. No persistent state.

    `fmt` is "json" or "text". Status / progress messages go to stderr so
    stdout is clean for piping into jq, an LLM context, etc.
    """
    _validate_album(album)
    album = album.resolve()

    click.echo(f"photoprune: scanning {album}", err=True)
    photos = scan(album)
    if not photos:
        if not heic_supported():
            click.echo(
                "(HEIC support disabled — install with: pip install pillow-heif)",
                err=True,
            )
        # Emit an empty-but-valid result so downstream parsers don't break.
        if fmt == "json":
            click.echo(
                format_json(
                    [], scanned=0, album_path=album, threshold=threshold
                )
            )
        else:
            click.echo(
                format_text(
                    [], scanned=0, album_path=album, threshold=threshold
                )
            )
        return

    click.echo(f"photoprune: encoding {len(photos)} photos with CLIP", err=True)
    _model_load_notice_stderr()

    # Analytical modes leave nothing on disk — caches and any other
    # working state live inside a temp dir that gets cleaned up here.
    with tempfile.TemporaryDirectory(prefix="photoprune-") as tmpdir:
        groups = find_duplicate_groups(
            photos,
            output_dir=Path(tmpdir),
            threshold=threshold,
            progress=False,
        )

    rendered = (
        format_json(
            groups, scanned=len(photos), album_path=album, threshold=threshold
        )
        if fmt == "json"
        else format_text(
            groups, scanned=len(photos), album_path=album, threshold=threshold
        )
    )
    click.echo(rendered)


def _model_load_notice_stderr() -> None:
    if _clip_already_cached():
        click.echo("photoprune: loading model from cache", err=True)
    else:
        click.echo(
            "photoprune: loading model — first-run download (~340 MB)",
            err=True,
        )


def _run_scan(cfg: Config) -> Path:
    _validate_album(cfg.album_path)

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

    # Interactive mode is now an explicit user choice (`--mode interactive`),
    # so always open the browser and wait for selections. If a user wants
    # non-blocking output, that's `--mode json` or `--mode text`.
    webbrowser.open(report_path.as_uri())

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
    "--mode",
    type=click.Choice(["interactive", "json", "text"], case_sensitive=False),
    default="interactive",
    show_default=True,
    help=(
        "interactive: open a review report in the browser, watch for "
        "Save Selections, then move flagged files to trash (default). "
        "json / text: run the pipeline, print groups to stdout, leave "
        "no files behind. Status messages go to stderr; the result goes "
        "to stdout so it pipes cleanly into jq, an LLM, etc."
    ),
)
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
    help=(
        "Where to write report, cache, and trash. Default: <album>/.photoprune/. "
        "Only valid in --mode interactive (analytical modes use a temp dir)."
    ),
)
def scan_cmd(
    album_path: Optional[str],
    mode: str,
    threshold: float,
    output_dir: Optional[str],
) -> None:
    """Scan ALBUM_PATH (default: current directory) for duplicates."""
    album = _resolve_album(album_path)
    mode = mode.lower()

    if mode != "interactive" and output_dir is not None:
        raise click.UsageError(
            "--output-dir is only valid with --mode interactive. "
            "Analytical modes (--mode json|text) use a temp dir and "
            "leave no files behind."
        )

    if mode == "interactive":
        out = Path(output_dir).expanduser() if output_dir else album / ".photoprune"
        cfg = Config(album_path=album, output_dir=out, threshold=threshold)
        _run_scan(cfg)
    else:
        _run_analytical(album=album, threshold=threshold, fmt=mode)


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
    Modes (--mode):
      interactive  open a browser review, then auto-cleanup (default)
      json         run pipeline, emit JSON to stdout, no residuals
      text         run pipeline, emit human-readable text, no residuals

    \b
    Common forms:
      photoprune                              # interactive on cwd
      photoprune /path/to/photos              # interactive on that dir
      photoprune --threshold 0.90             # flag more aggressively
      photoprune cleanup OUTPUT_DIR           # apply a saved selections.json

    \b
    For scripts / AI agents, use --mode json or --mode text. Status goes
    to stderr; the result goes to stdout, so it pipes cleanly:
      photoprune --mode json /path/to/photos
      photoprune --mode json /path/to/photos | jq '.groups[].suggested_keep'
      photoprune --mode text --threshold 0.85 /path/to/photos
    """


main.add_command(scan_cmd)
main.add_command(cleanup_cmd)


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
