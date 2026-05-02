# Changelog

All notable changes to PhotoPrune will be documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/YashBhalodi/PhotoPrune/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/YashBhalodi/PhotoPrune/releases/tag/v0.1.0
