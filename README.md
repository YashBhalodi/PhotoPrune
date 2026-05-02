# PhotoPrune

[![CI](https://github.com/YashBhalodi/PhotoPrune/actions/workflows/test.yml/badge.svg)](https://github.com/YashBhalodi/PhotoPrune/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org/)

A local, offline CLI for finding near-duplicate photos in a directory and helping you remove them safely. Runs entirely on CPU — no GPU, no cloud, no telemetry. Originals are never hard-deleted; everything moves to a `_trash/` folder you can verify before discarding.

```text
$ cd ~/Pictures/Trip
$ photoprune
Scanning ~/Pictures/Trip ...
Found 250 photo(s).
Loading clip model from cache ...

Found 8 duplicate group(s) covering 24 photos.
Report: ~/Pictures/Trip/.photoprune/duplicates_report.html
[browser opens — review, click "Save & move N to trash"]

Selections received. Moved 16 file(s) to ~/Pictures/Trip/.photoprune/_trash
────────────────────────────────────────────────
  scanned:   250 photo(s)
  groups:    8 (24 photos in groups)
  removed:   16 file(s)
────────────────────────────────────────────────
```

## Install

### macOS (Homebrew)

```bash
brew tap YashBhalodi/photoprune
brew install photoprune
```

That's all. The formula brings in Python and the entire ML stack (PyTorch, faiss, CLIP, etc.) into a sandboxed install — you don't need Python on your system. First install downloads ~880 MB of dependencies and takes a few minutes; updates with `brew upgrade photoprune` are fast.

If you'd rather not tap, the explicit equivalent is `brew install YashBhalodi/photoprune/photoprune`.

> **Linuxbrew users:** the same formula should work via `brew tap YashBhalodi/photoprune && brew install photoprune`, but this hasn't been tested on Linux. The from-source path below is the more idiomatic option for Linux. Windows is not currently supported via Homebrew.

### From source (with [uv](https://docs.astral.sh/uv/)) — macOS, Linux

```bash
# Install uv if you don't have it (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/YashBhalodi/PhotoPrune.git && cd PhotoPrune
uv tool install --editable ".[heic]"             # exposes photoprune on $PATH
```

## Usage

```bash
cd ~/Pictures/My-Trip
photoprune
```

PhotoPrune scans the current directory, opens an HTML review report in your browser, waits for you to click **Save & move N to trash**, then moves the flagged files into `<album>/.photoprune/_trash/`. Press <kbd>Ctrl</kbd>+<kbd>C</kbd> at any point to skip cleanup — the report and selections stay put for you to apply later with `photoprune cleanup OUTPUT_DIR`.

### Common flags

```bash
photoprune /path/to/photos          # scan a different directory
photoprune --model mobilenet        # faster, less accurate model
photoprune --threshold 0.90         # flag more aggressively (default 0.94)
photoprune --no-open                # don't auto-open the report
photoprune --no-wait                # don't block on selections — print instructions and exit
photoprune cleanup ./.photoprune    # apply a previously saved selections.json
```

### All flags

| Flag | Default | Description |
|------|---------|-------------|
| `album_path` | `.` | Directory to scan |
| `--model` | `clip` | `clip` (accurate, ViT-B/32) or `mobilenet` (fast, smaller) |
| `--threshold` | `0.94` | Cosine similarity cutoff for near-duplicate detection (0.0–1.0) |
| `--phash-threshold` | `10` | Hamming distance for exact-dupe detection |
| `--output-dir` | `<album>/.photoprune/` | Where the report, cache, and trash live |
| `--no-cache` | off | Re-encode every photo from scratch |
| `--no-open` | off | Don't auto-open the HTML report |
| `--no-wait` | off | Don't block waiting for `selections.json` |

## How it works

1. **pHash** — A perceptual hash for every photo. Hashes within Hamming distance `--phash-threshold` are grouped (exact / near-identical re-encodes).
2. **Embeddings** — Each photo passes through CLIP ViT-B/32 (or MobileNetV2 with `--model mobilenet`) to get a semantic vector. Vectors are cached to disk so re-runs only encode new or changed photos.
3. **Faiss** — Builds an index over the vectors, finds pairs whose cosine similarity ≥ `--threshold`, and Union-Finds them into groups.
4. **Quality scoring** — Within each group, photos are ranked by `0.5 · sharpness + 0.3 · resolution + 0.2 · filesize`. Sharpness is the variance of the Laplacian. The top-ranked photo is auto-suggested as the keeper.
5. **Report** — A self-contained HTML report (base64 thumbnails, no CDN) opens in your browser. Each card is either **Keep** (highlighted) or **Trash** (quiet) — click to toggle. The ★ marks the auto-suggested keeper. Click **View** for a lightbox at full resolution; arrow keys navigate, <kbd>K</kbd> toggles, <kbd>Esc</kbd> closes.
6. **Auto-cleanup** — PhotoPrune polls `~/Downloads/` and the output dir for a fresh `selections.json`. The moment you click **Save & move N to trash** in the report, photoprune picks it up and moves the flagged files to `_trash/`. An `audit_log.csv` records every move.

## Output layout

```
<album>/.photoprune/
├── duplicates_report.html       # Self-contained, no internet needed
├── selections.json              # Written by the report's Save button
├── audit_log.csv                # Written by cleanup; CSV of every move
├── embeddings_cache.npy         # Vector cache (skip re-encoding next run)
├── embeddings_manifest.json     # Maps file paths → cache rows + mtimes
└── _trash/                      # Moved files (mirror of original dir layout)
```

The output dir is hidden (`.photoprune/`) so it doesn't clutter the album, and the scanner ignores hidden directories — re-runs don't crawl back into the cache or `_trash`.

## Supported formats

`.jpg` `.jpeg` `.png` `.webp` `.bmp` `.tif` `.tiff` `.heic` (HEIC requires `pillow-heif`, bundled with the brew install).

## Uninstall

PhotoPrune is designed to leave nothing behind in places you can't see. Model weights download into the install prefix (not `~/.cache/`) so brew can clean them up along with everything else.

### Homebrew

```bash
brew uninstall photoprune
brew untap YashBhalodi/photoprune
brew autoremove                     # removes Python 3.11 if no other formula needs it
```

That removes:
- The ~880 MB venv (PyTorch, faiss, CLIP, etc.)
- The CLIP and MobileNetV2 model weights downloaded on first run (cached inside the venv at `<prefix>/.cache/photoprune/`)
- The `photoprune` and `photodedupe` commands from your PATH

What it intentionally **leaves behind**:
- `<album>/.photoprune/` directories — your per-album review reports, embedding caches, and `_trash/` folders. These hold *your data*, so PhotoPrune never auto-deletes them. Photos in `_trash/` can be moved back with `mv` once you're sure you don't need them.

If you want to nuke every PhotoPrune output across your photo library, after the brew uninstall:

```bash
# Dry run — see what would be removed
find ~/Pictures -type d -name '.photoprune'

# Actually remove (review the list first!)
find ~/Pictures -type d -name '.photoprune' -exec rm -rf {} +
```

### From-source install

```bash
uv tool uninstall photoprune        # if installed via `uv tool install`
rm -rf ~/.cache/photoprune          # only present if you ran with HF_HOME unset
```

If you ever previously ran an older PhotoPrune (pre-0.2) that downloaded weights into the global Hugging Face / torch caches, you can also reclaim that space:

```bash
rm -rf ~/.cache/huggingface/hub/models--*clip*vit-b-32*
rm -rf ~/.cache/torch/hub/checkpoints/mobilenet_v2*
```

## Privacy

PhotoPrune never uploads anything anywhere. The model weights are downloaded once on first run from the official Hugging Face / torchvision caches; everything after that is local. The HTML report is fully self-contained — base64 thumbnails, no external links — so it works offline and reveals nothing about your photos to network observers.

## Development

```bash
brew install uv                          # one-time
git clone https://github.com/YashBhalodi/PhotoPrune.git && cd PhotoPrune
uv sync --extra dev --extra heic
uv run pytest                            # run the test suite
uv run photoprune ~/Pictures/Trip        # run the CLI from this checkout
```

The repo ships a `uv.lock` so installs are byte-reproducible.

### Cutting a release

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
gh release create vX.Y.Z --generate-notes
```

Then update the formula in [YashBhalodi/homebrew-photoprune](https://github.com/YashBhalodi/homebrew-photoprune) with the new version + tarball sha256 (`shasum -a 256 <release-tarball>`).

## Acknowledgments

PhotoPrune stands on the shoulders of:

- [OpenAI CLIP](https://github.com/openai/CLIP) via [open-clip-torch](https://github.com/mlfoundations/open_clip) — semantic image embeddings.
- [Faiss](https://github.com/facebookresearch/faiss) — efficient similarity search.
- [imagehash](https://github.com/JohannesBuchner/imagehash) — perceptual hashing.
- [PyTorch](https://pytorch.org/), [torchvision](https://github.com/pytorch/vision), [Pillow](https://python-pillow.org/), [OpenCV](https://opencv.org/), [Click](https://click.palletsprojects.com/), [tqdm](https://github.com/tqdm/tqdm).

## License

[MIT](LICENSE) © 2026 Yash Bhalodi and PhotoPrune Contributors.
