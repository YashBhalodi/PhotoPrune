# Changelog

All notable changes to PhotoPrune will be documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] — 2026-05-02

### Changed (small CLI behavior change)

- Removed TTY auto-detection. Mode is now the single source of truth.
  - **Before:** in `--mode interactive`, if stdin/stdout weren't a TTY, photoprune silently skipped the auto-open and the watch-for-selections steps and just printed the report path.
  - **After:** `--mode interactive` always opens the browser and waits for selections. Users who want non-blocking output should pick `--mode json` or `--mode text` explicitly.
  - Affects only piped or backgrounded `--mode interactive` runs. The analytical modes are unchanged.

### Added

- `--mode text` and `--mode json` sample outputs in the README, plus guidance on when to use which: **json** when programmatically processing the result, **text** when reading or feeding to an LLM (more compact / token-efficient).

### Fixed

- "How it works" section no longer references `--phash-threshold` and `--model mobilenet` (both removed in 0.3.0).

## [0.4.0] — 2026-05-02

### Added

- `--mode` flag with three values: `interactive` (default; today's UX), `json`, and `text`.
- `json` mode runs the pipeline and prints groups as a stable, versioned JSON object to stdout. Schema documented in [docs/json-schema.md](docs/json-schema.md). Designed to be LLM- and script-friendly: status messages go to stderr, the result goes to stdout, schema carries a `"version"` field.
- `text` mode is the same idea but human-readable and parseable.
- Both analytical modes (`json`, `text`) leave **no files behind** — the embedding cache lives in a `tempfile.TemporaryDirectory` that's cleaned up on exit. Useful for AI-agent calls that want a one-shot answer without polluting the album.
- New `photoprune.output` module exposes `format_json` and `format_text` for library callers who want the formatters without going through the CLI.

### Changed

- Help text restructured to lead with the three modes.
- `--output-dir` is rejected when combined with `--mode json|text` (no output dir is created — the temp dir is invisible).

### Internal

- 8 new tests covering the JSON schema, text formatting, and edge cases (empty albums, missing quality scores). Total now 34.

## [0.3.0] — 2026-05-02

### Removed (breaking, CLI surface only)

Trimmed five CLI flags whose current defaults are the right behavior for everyone today. They'll come back if/when there's a real use case:

- `--model` (was: choose between CLIP and MobileNetV2). CLIP is the only mode now.
- `--phash-threshold` (Hamming-distance cutoff for the exact-dup pHash pass). Hardcoded to 10.
- `--no-cache` (re-encode from scratch). Caching is always on; delete `<output-dir>/embeddings_cache.npy` manually if you really need to re-encode.
- `--no-open` (don't auto-open the report). Auto-open now driven entirely by TTY detection — interactive sessions open the browser, CI / piped runs don't.
- `--no-wait` (don't block on selections.json). Same TTY-driven logic.

The library API is unaffected — `find_duplicate_groups()` in `photoprune.pipeline` still accepts `model`, `phash_threshold`, and `use_embedding_cache` as keyword arguments.

### Changed

- `photoprune.models.Config` slimmed to `(album_path, output_dir, threshold)` to match the trimmed CLI surface. The dropped fields stay available on `find_duplicate_groups` for library users.
- `_model_load_notice` now honors `$HF_HOME` (the package init redirects this into the install prefix), so the "Loading from cache" message is accurate again on v0.2+ installs.

### Internal

- Library bootstrap (OMP/faiss-import-order guard, model-cache redirect) moved fully out of `cli.py` in v0.2; this release removes the now-redundant guard duplication.

## [0.2.0] — 2026-05-02

### Changed
- Model caches (CLIP weights ~340 MB, MobileNetV2 ~14 MB) now download into `<install-prefix>/.cache/photoprune/` instead of the global `~/.cache/huggingface/` and `~/.cache/torch/`. Effect: `brew uninstall photoprune` is now genuinely clean — it reaches the model weights along with the rest of the venv. Old caches from 0.1.x still work; see the README's Uninstall section for how to reclaim that disk space.
- Bumped to 0.2.0 to surface the cache-location change.

### Added
- README "Uninstall" section documenting brew + from-source removal and how to clean up per-album `.photoprune/` directories.

## [0.1.0] — 2026-05-02

Initial public release.

### Added
- Two-phase duplicate detection: pHash for exact/near-identical, CLIP embeddings + Faiss for visual near-duplicates.
- `--model mobilenet` for a lighter (~14 MB) alternative to CLIP ViT-B/32.
- Self-contained HTML review report with click-to-toggle Keep / Trash, lightbox for full-size review, per-group reset, suggested-keep based on a `0.5·sharpness + 0.3·resolution + 0.2·filesize` quality score.
- End-to-end UX: `cd ~/Pictures/Trip && photoprune` scans, opens the report, watches for `selections.json` from Downloads or the output dir, then auto-cleans flagged files to `<album>/.photoprune/_trash/`.
- Embedding cache so re-runs only encode new or changed photos.
- `photoprune cleanup OUTPUT_DIR` to apply a saved selections file later.
- `--no-wait` and `--no-open` for unattended runs (auto-disabled outside TTYs).
- HEIC/iPhone photo support via the `[heic]` extra (bundled in the brew install).
- Homebrew tap at [YashBhalodi/homebrew-photoprune](https://github.com/YashBhalodi/homebrew-photoprune) for one-command install on macOS / Linux.

[Unreleased]: https://github.com/YashBhalodi/PhotoPrune/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/YashBhalodi/PhotoPrune/releases/tag/v0.5.0
[0.4.0]: https://github.com/YashBhalodi/PhotoPrune/releases/tag/v0.4.0
[0.3.0]: https://github.com/YashBhalodi/PhotoPrune/releases/tag/v0.3.0
[0.2.0]: https://github.com/YashBhalodi/PhotoPrune/releases/tag/v0.2.0
[0.1.0]: https://github.com/YashBhalodi/PhotoPrune/releases/tag/v0.1.0
