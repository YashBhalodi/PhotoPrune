"""PhotoPrune — find and remove near-duplicate photos, offline."""

import os
import sys
from pathlib import Path

__version__ = "0.2.0"

# ---------------------------------------------------------------------------
# Library import-order guard
# ---------------------------------------------------------------------------
# faiss-cpu and PyTorch each link their own OpenMP runtime. On macOS (and
# some Linux configs) loading both with multi-threaded OMP causes a
# segfault during faiss search(). Pin OMP to a single thread BEFORE either
# library is imported, then load faiss first so its libomp wins. This
# applies to anyone who does `import photoprune`, not just the CLI.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import faiss as _faiss  # noqa: E402,F401

try:
    _faiss.omp_set_num_threads(1)
except Exception:
    pass

# ---------------------------------------------------------------------------
# Model cache redirect
# ---------------------------------------------------------------------------
# Pin model caches (CLIP weights ~340 MB, MobileNet ~14 MB) to the install
# prefix so that uninstalling photoprune cleanly removes them along with
# the rest of the venv. Without this, downloads land in
# ~/.cache/huggingface/ and ~/.cache/torch/ where `brew uninstall` can't
# reach. setdefault means a user-set HF_HOME / TORCH_HOME still wins.
_cache_root = Path(sys.prefix) / ".cache" / "photoprune"
os.environ.setdefault("HF_HOME", str(_cache_root / "huggingface"))
os.environ.setdefault("TORCH_HOME", str(_cache_root / "torch"))

# ---------------------------------------------------------------------------
# Public library API
# ---------------------------------------------------------------------------
from .models import Config, DuplicateGroup, PhotoFile  # noqa: E402
from .pipeline import find_duplicate_groups  # noqa: E402
from .scanner import scan  # noqa: E402

__all__ = [
    "Config",
    "DuplicateGroup",
    "PhotoFile",
    "find_duplicate_groups",
    "scan",
]
