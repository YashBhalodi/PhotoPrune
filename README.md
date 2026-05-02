# PhotoPrune

A local, offline CLI tool for finding near-duplicate photos in a directory and helping you remove them safely. Runs entirely on CPU — no GPU, no cloud.

## Install

### macOS / Linux (Homebrew)

```bash
brew install YashBhalodi/photoprune/photoprune
```

This pulls in everything (Python, the model stack, etc.) into an isolated install — no setup required.

### From source

PhotoPrune uses [uv](https://docs.astral.sh/uv/) for development. Install uv (`brew install uv`) once, then:

```bash
git clone https://github.com/YashBhalodi/PhotoPrune.git
cd PhotoPrune
uv tool install --editable .          # exposes `photoprune` on $PATH
```

For HEIC/iPhone photo support:

```bash
uv tool install --editable ".[heic]"
```

## Usage

The fast path:

```bash
cd ~/Pictures/My-Trip
photoprune
```

That's it. PhotoPrune scans the current directory, opens a review report in your browser, waits for you to click **Save Selections**, then moves the flagged files to `./.photoprune/_trash/`. Originals are never hard-deleted.

### Flags

```bash
# Scan a different directory
photoprune /path/to/photos

# Faster, less accurate model
photoprune --model mobilenet

# Flag more aggressively
photoprune --threshold 0.90

# Don't auto-open the report
photoprune --no-open

# Just produce the report and exit (don't wait for selections)
photoprune --no-wait

# Apply a selections.json that you saved earlier
photoprune cleanup ./.photoprune
```

| Flag | Default | Description |
|------|---------|-------------|
| `album_path` | `.` | Directory to scan |
| `--model` | `clip` | `clip` (accurate) or `mobilenet` (fast) |
| `--threshold` | `0.94` | Cosine similarity cutoff (0.0–1.0) |
| `--phash-threshold` | `10` | Hamming distance for exact-dupe detection |
| `--output-dir` | `<album>/.photoprune/` | Where the report, cache, and trash live |
| `--no-cache` | off | Re-encode all photos from scratch |
| `--no-open` | off | Don't auto-open the HTML report |
| `--no-wait` | off | Don't block waiting for selections.json |

### How it works

1. **pHash** — Compute a perceptual hash for every photo. Group hashes within Hamming distance `--phash-threshold` (exact-ish duplicates).
2. **Embeddings** — Pass each photo through CLIP ViT-B/32 (or MobileNetV2 with `--model mobilenet`) to get a semantic vector. Vectors are cached to disk so re-runs only encode new photos.
3. **Faiss** — Build an index, find pairs whose cosine similarity ≥ `--threshold`, and Union-Find them into groups.
4. **Quality scoring** — Within each group, photos are ranked by `0.5 × sharpness + 0.3 × resolution + 0.2 × filesize`. The top-ranked photo is auto-suggested as the keeper; the rest are pre-selected for removal.
5. **Report** — A self-contained HTML report opens in your browser. Check or uncheck the photos to remove, then click **Save Selections**.
6. **Auto-cleanup** — PhotoPrune watches your `~/Downloads/` and the output dir for the saved `selections.json`, then moves flagged photos to `_trash/`. `Ctrl-C` skips this step; you can run `photoprune cleanup OUTPUT_DIR` later instead.

### Output layout

```
<album>/.photoprune/
├── duplicates_report.html
├── selections.json          # Created when you click "Save Selections"
├── audit_log.csv            # Created by cleanup
├── embeddings_cache.npy
├── embeddings_manifest.json
└── _trash/                  # Moved files (mirrors original directory layout)
```

The output dir is hidden (`.photoprune/`) so it doesn't clutter the album, and the scanner ignores hidden directories so re-runs don't re-scan the trash.

### Supported formats

`.jpg` `.jpeg` `.png` `.webp` `.bmp` `.tif` `.tiff` `.heic` (with `pillow-heif`)

## Development

PhotoPrune uses [uv](https://docs.astral.sh/uv/) for dependency management. The repo ships a `uv.lock` for reproducible installs.

```bash
brew install uv               # one-time
uv sync --extra dev --extra heic
uv run pytest
```

Run the CLI from a checkout without installing:

```bash
uv run photoprune ~/Pictures/Trip
```

### Cutting a release

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
gh release create vX.Y.Z --generate-notes
```

The Homebrew formula in [YashBhalodi/homebrew-photoprune](https://github.com/YashBhalodi/homebrew-photoprune) needs to be updated with the new version + sha256 (`shasum -a 256 <release-tarball>`).
