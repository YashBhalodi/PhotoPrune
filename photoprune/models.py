"""Core dataclasses shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Optional

DetectionType = Literal["exact", "near", "mixed"]

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic",
}


@dataclass
class PhotoFile:
    path: str
    size_bytes: int
    mtime: float
    width: int = 0
    height: int = 0
    date_taken: Optional[datetime] = None
    phash: Optional[str] = None
    embedding_index: Optional[int] = None
    sharpness: Optional[float] = None
    quality_rank: Optional[float] = None

    @property
    def filename(self) -> str:
        return Path(self.path).name

    @property
    def resolution(self) -> int:
        return self.width * self.height


@dataclass
class DuplicateGroup:
    group_id: str
    detection_type: DetectionType
    members: List[PhotoFile]
    max_similarity: float
    suggested_keep_path: str = ""

    @property
    def size(self) -> int:
        return len(self.members)


@dataclass
class Config:
    album_path: Path
    output_dir: Path
    model: str = "clip"
    threshold: float = 0.94
    phash_threshold: int = 10
    no_cache: bool = False
    open_report: bool = False

    def __post_init__(self) -> None:
        self.album_path = Path(self.album_path).expanduser().resolve()
        self.output_dir = Path(self.output_dir).expanduser().resolve()
