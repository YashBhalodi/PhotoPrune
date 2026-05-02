# PhotoPrune

A local, offline CLI tool for finding near-duplicate photos in a directory and helping you remove them safely. Runs entirely on CPU — no GPU, no cloud.

## Install

```bash
pip install -e .
```

For HEIC/iPhone photo support:

```bash
pip install -e ".[heic]"
```

## Usage

```bash
# Basic scan
photodedupe /path/to/photos

# Faster, less accurate
photodedupe /path/to/photos --model mobilenet

# Flag more aggressively
photodedupe /path/to/photos --threshold 0.90

# Auto-open the report in your browser
photodedupe /path/to/photos --open-report

# After reviewing the report, apply selections
photodedupe cleanup ./photodedupe_out
```

### How it works

1. **pHash** — Compute a perceptual hash for every photo. Group hashes within Hamming distance `--phash-threshold` (exact-ish duplicates).
2. **Embeddings** — Pass each photo through CLIP ViT-B/32 (or MobileNetV2 with `--model mobilenet`) to get a semantic vector. Vectors are cached to disk so re-runs only encode new photos.
3. **Faiss** — Build an index, find pairs whose cosine similarity ≥ `--threshold`, and Union-Find them into groups.
4. **Quality scoring** — Within each group, photos are ranked by `0.5 × sharpness + 0.3 × resolution + 0.2 × filesize`. The top-ranked photo is auto-suggested as the keeper; the rest are pre-selected for removal.
5. **Report** — A self-contained `duplicates_report.html` opens in your browser. Check or uncheck the photos to remove, then click **Save Selections** to download `selections.json`.
6. **Cleanup** — `photodedupe cleanup` reads that file and moves flagged photos to `_trash/`. Originals are never hard-deleted.

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `album_path` | *(required)* | Path to photo directory |
| `--model` | `clip` | `clip` (accurate) or `mobilenet` (fast) |
| `--threshold` | `0.94` | Cosine similarity cutoff (0.0–1.0) |
| `--phash-threshold` | `10` | Hamming distance for exact-dupe detection |
| `--output-dir` | `./photodedupe_out` | Where to write the report and cache |
| `--no-cache` | `False` | Re-encode all photos from scratch |
| `--open-report` | `False` | Auto-open the HTML report |

### Output layout

```
photodedupe_out/
├── duplicates_report.html
├── selections.json          # Created when you click "Save Selections"
├── audit_log.csv            # Created by `cleanup`
├── embeddings_cache.npy
├── embeddings_manifest.json
└── _trash/                  # Moved files (mirrors original directory layout)
```

### Saving selections

The HTML report runs entirely offline. Clicking **Save Selections** triggers a normal browser download of `selections.json`. Move that file into your `--output-dir` (replacing any existing one), then run `photodedupe cleanup ./photodedupe_out`.

### Supported formats

`.jpg` `.jpeg` `.png` `.webp` `.bmp` `.tif` `.tiff` `.heic` (with `pillow-heif`)

## Development

```bash
pip install -e ".[dev,heic]"
pytest
```
