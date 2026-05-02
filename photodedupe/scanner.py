"""Recursive file discovery for supported image formats."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from PIL import ExifTags, Image, UnidentifiedImageError

from .models import SUPPORTED_EXTENSIONS, PhotoFile

try:
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
    _HEIC_OK = True
except Exception:
    _HEIC_OK = False


_DATE_TAKEN_TAGS = {tag for tag, name in ExifTags.TAGS.items() if name == "DateTimeOriginal"}


def _parse_exif_datetime(img: Image.Image) -> Optional[datetime]:
    try:
        exif = img.getexif()
    except Exception:
        return None
    if not exif:
        return None
    for tag_id in _DATE_TAKEN_TAGS:
        value = exif.get(tag_id)
        if not value:
            continue
        try:
            return datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
        except ValueError:
            continue
    return None


def heic_supported() -> bool:
    return _HEIC_OK


def iter_image_paths(root: Path) -> Iterable[Path]:
    """Yield image file paths under root, sorted for deterministic ordering."""
    paths: List[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            ext = Path(name).suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                paths.append(Path(dirpath) / name)
    paths.sort()
    return paths


def scan(root: Path, *, warn_heic: bool = True) -> List[PhotoFile]:
    """Walk `root`, returning a PhotoFile for every readable image."""
    photos: List[PhotoFile] = []
    skipped_heic = 0

    for path in iter_image_paths(root):
        ext = path.suffix.lower()
        if ext == ".heic" and not _HEIC_OK:
            skipped_heic += 1
            continue

        try:
            stat = path.stat()
        except OSError:
            continue

        try:
            with Image.open(path) as img:
                width, height = img.size
                date_taken = _parse_exif_datetime(img)
        except (UnidentifiedImageError, OSError):
            continue
        except Exception:
            continue

        photos.append(
            PhotoFile(
                path=str(path),
                size_bytes=stat.st_size,
                mtime=stat.st_mtime,
                width=width,
                height=height,
                date_taken=date_taken,
            )
        )

    if skipped_heic and warn_heic:
        print(
            f"[warning] skipped {skipped_heic} .heic file(s); install with:\n"
            f"          pip install pillow-heif"
        )

    return photos
