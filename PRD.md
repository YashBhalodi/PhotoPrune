# PhotoPrune — MVP Product Requirements

A local, offline CLI tool that finds near-duplicate photos in an album directory and helps you remove them safely.

---

## Problem

Large photo libraries accumulate near-identical shots — burst sequences, minor pose changes, re-takes. Manually finding and removing them is impractical. Exact-hash tools miss the subtle near-duplicates that are the real problem.

---

## MVP Scope

**In scope:**
- Detect exact duplicates (same image, different filename)
- Detect near-duplicates (same scene, minor variations in pose/lighting/framing)
- Run fully offline on CPU — no GPU required
- Generate a visual HTML report for user review before any deletion
- Move flagged files to a trash folder (never hard-delete)
- Accept album path as a CLI argument

**Out of scope for MVP:**
- GUI
- Cloud/network storage
- RAW camera formats (.NEF, .CR2)
- Video files
- Auto-deletion without review

---

## Installation

```bash
pip install photodedupe
```

Or from source:

```bash
git clone https://github.com/<your-username>/photodedupe
cd photodedupe
pip install -e .
```

---

## Usage

```bash
# Basic scan
photodedupe /path/to/photos

# Use faster model (less accurate, good for large libraries)
photodedupe /path/to/photos --model mobilenet

# Lower similarity threshold (flag more aggressively)
photodedupe /path/to/photos --threshold 0.90

# After reviewing the report, run cleanup
photodedupe cleanup ./photodedupe_out
```

### Key CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `album_path` | *(required)* | Path to photo directory |
| `--model` | `clip` | `clip` (accurate) or `mobilenet` (fast) |
| `--threshold` | `0.94` | Cosine similarity cutoff (0.0–1.0) |
| `--phash-threshold` | `10` | Hamming distance for exact-dupe detection |
| `--output-dir` | `./photodedupe_out` | Where to write report and cache |
| `--no-cache` | `False` | Re-encode all photos from scratch |
| `--open-report` | `False` | Auto-open HTML report in browser |

---

## How It Works

Two-phase pipeline:

**Phase 1 — pHash (exact duplicates)**
Compute a perceptual hash for every photo. Group any two photos whose hashes are within a Hamming distance ≤ `--phash-threshold`. Fast (~300 photos/sec).

**Phase 2 — Embedding + Faiss (near-duplicates)**
Pass each photo through a vision model (CLIP ViT-B/32 or MobileNetV2) to get a semantic vector. Build a Faiss index and find all pairs with cosine similarity ≥ `--threshold`. Embeddings are cached to disk so re-runs only encode new photos.

**Phase 3 — Report**
Generate a self-contained `duplicates_report.html` showing each duplicate group side-by-side with similarity scores. User checks which files to remove, clicks "Save Selections".

**Phase 4 — Cleanup**
`photodedupe cleanup <output-dir>` reads selections and moves flagged files to `_trash/`. Writes `audit_log.csv`.

---

## Project Structure

```
photodedupe/
├── photodedupe/
│   ├── __init__.py
│   ├── cli.py          # Entry point, argument parsing (Click)
│   ├── scanner.py      # Recursive file discovery
│   ├── hasher.py       # pHash + Hamming grouping
│   ├── embedder.py     # CLIP / MobileNet inference + embedding cache
│   ├── indexer.py      # Faiss index + similarity search + clustering
│   ├── reporter.py     # Self-contained HTML report
│   ├── cleaner.py      # Safe file mover + audit log
│   └── models.py       # Dataclasses: PhotoFile, DuplicateGroup, Config
├── tests/
│   └── fixtures/       # Small synthetic test images
├── run.py              # Convenience: python run.py <args>
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## Core Dependencies

| Package | Purpose |
|---------|---------|
| `torch` (CPU) | Model inference |
| `open-clip-torch` | CLIP ViT-B/32 |
| `torchvision` | MobileNetV2 |
| `faiss-cpu` | Similarity search |
| `Pillow` | Image loading |
| `imagehash` | Perceptual hashing |
| `numpy` | Embedding cache (.npy) |
| `tqdm` | Progress bars |
| `click` | CLI |
| `opencv-python-headless` | Sharpness scoring |

Optional: `pillow-heif` for HEIC/iPhone photo support.

---

## Output Files

```
photodedupe_out/
├── duplicates_report.html      # Visual review report (self-contained, no internet needed)
├── selections.json             # Written by report "Save" button; read by cleanup
├── audit_log.csv               # Record of all moves made by cleanup
├── embeddings_cache.npy        # Cached vectors (skip re-encoding on next run)
├── embeddings_manifest.json    # Maps file paths to cache rows + mtimes
└── _trash/                     # Moved files (mirror of original directory structure)
```

---

## Data Models

```python
@dataclass
class PhotoFile:
    path: str
    size_bytes: int
    mtime: float
    width: int
    height: int
    date_taken: Optional[datetime]
    phash: Optional[str]
    embedding_index: Optional[int]
    sharpness: Optional[float]       # Laplacian variance — higher = sharper
    quality_rank: Optional[float]    # Composite score used to auto-suggest "keep"

@dataclass
class DuplicateGroup:
    group_id: str
    detection_type: Literal["exact", "near", "mixed"]
    members: List[PhotoFile]
    max_similarity: float
    suggested_keep_path: str         # Highest quality_rank member
```

---

## Key Implementation Notes

- **Never hard-delete.** Use `shutil.move()` only. The `_trash/` folder mirrors the original directory structure.
- **Embedding cache invalidation:** Re-encode a file only if its `mtime` or `size_bytes` has changed since the last run.
- **Clustering:** Use Union-Find so that if A≈B and B≈C, all three end up in one group (not two overlapping pairs).
- **Auto-suggest:** Within each group, rank by `0.5 × sharpness + 0.3 × resolution + 0.2 × filesize` and pre-select all non-top-ranked photos for removal in the report.
- **Faiss index:** Use `IndexFlatIP` for libraries under 50k photos; auto-switch to `IndexIVFFlat` above that.
- **HTML report:** Must be fully self-contained (base64-encoded thumbnails, no CDN links). User must be able to open it with no internet connection.
- **HEIC support:** If `pillow-heif` is not installed, skip `.heic` files with a warning and print the install command — don't crash.

---

## Supported Formats

`.jpg` `.jpeg` `.png` `.webp` `.bmp` `.tif` `.tiff` `.heic` (requires `pillow-heif`)

---

## MVP Acceptance Criteria

- [ ] `photodedupe ~/Pictures` runs without error on a folder of mixed JPEG/PNG files
- [ ] Exact duplicates (same image, different filename) are detected and grouped
- [ ] Near-duplicates (slight pose variation) appear in the same group with a similarity score
- [ ] `duplicates_report.html` opens in a browser, shows images side-by-side, and lets user check/uncheck files
- [ ] `photodedupe cleanup` moves only user-selected files to `_trash/`; originals are untouched
- [ ] Re-running the scan after adding new photos only encodes the new photos (cache hit for existing ones)
- [ ] Tool works on macOS, Linux, and Windows with Python 3.10+
