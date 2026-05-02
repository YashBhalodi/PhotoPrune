"""PhotoPrune — find and remove near-duplicate photos, offline."""

import os
import sys
from pathlib import Path

__version__ = "0.2.0"

# Pin model caches (CLIP weights ~340 MB, MobileNet ~14 MB) to the install
# prefix so that uninstalling photoprune cleanly removes them along with
# the rest of the venv. Without this, downloads land in
# ~/.cache/huggingface/ and ~/.cache/torch/ where `brew uninstall` can't
# reach. setdefault means a user-set HF_HOME / TORCH_HOME still wins.
_cache_root = Path(sys.prefix) / ".cache" / "photoprune"
os.environ.setdefault("HF_HOME", str(_cache_root / "huggingface"))
os.environ.setdefault("TORCH_HOME", str(_cache_root / "torch"))
