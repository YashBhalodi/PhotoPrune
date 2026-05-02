"""Vision-model embeddings (CLIP / MobileNet) with disk-cached vectors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from PIL import Image
from tqdm import tqdm

from .models import PhotoFile

_CACHE_VECTORS = "embeddings_cache.npy"
_CACHE_MANIFEST = "embeddings_manifest.json"


class _Embedder:
    """Subclasses encode a PIL image into a normalized float32 vector."""

    name: str = ""
    dim: int = 0

    def encode(self, img: Image.Image) -> np.ndarray:
        raise NotImplementedError


class _ClipEmbedder(_Embedder):
    name = "clip-vit-b32"
    dim = 512

    def __init__(self) -> None:
        import open_clip

        self.device = "cpu"
        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="openai"
        )
        model.eval()
        self.model = model.to(self.device)
        self.preprocess = preprocess

    @torch.inference_mode()
    def encode(self, img: Image.Image) -> np.ndarray:
        tensor = self.preprocess(img.convert("RGB")).unsqueeze(0).to(self.device)
        feats = self.model.encode_image(tensor)
        feats = feats / feats.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        return feats.cpu().numpy().astype(np.float32).reshape(-1)


class _MobileNetEmbedder(_Embedder):
    name = "mobilenet-v2"
    dim = 1280

    def __init__(self) -> None:
        from torchvision import models, transforms

        self.device = "cpu"
        weights = models.MobileNet_V2_Weights.DEFAULT
        net = models.mobilenet_v2(weights=weights)
        net.eval()
        # Strip classifier; pool features to (B, 1280).
        self.features = net.features.to(self.device)
        self.pool = torch.nn.AdaptiveAvgPool2d(1)
        self.preprocess = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ])

    @torch.inference_mode()
    def encode(self, img: Image.Image) -> np.ndarray:
        tensor = self.preprocess(img.convert("RGB")).unsqueeze(0).to(self.device)
        x = self.features(tensor)
        x = self.pool(x).flatten(1)
        x = x / x.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        return x.cpu().numpy().astype(np.float32).reshape(-1)


def _load_embedder(model: str) -> _Embedder:
    if model == "clip":
        return _ClipEmbedder()
    if model == "mobilenet":
        return _MobileNetEmbedder()
    raise ValueError(f"Unknown model: {model!r} (expected 'clip' or 'mobilenet')")


def _load_cache(
    output_dir: Path, model_name: str
) -> Tuple[Dict[str, dict], Optional[np.ndarray]]:
    manifest_path = output_dir / _CACHE_MANIFEST
    vectors_path = output_dir / _CACHE_VECTORS
    if not manifest_path.exists() or not vectors_path.exists():
        return {}, None
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception:
        return {}, None
    if manifest.get("model") != model_name:
        return {}, None
    entries = manifest.get("entries", {})
    try:
        vectors = np.load(vectors_path)
    except Exception:
        return {}, None
    return entries, vectors


def embed_photos(
    photos: List[PhotoFile],
    output_dir: Path,
    model: str,
    *,
    use_cache: bool = True,
    show_progress: bool = True,
) -> np.ndarray:
    """Compute embeddings for every photo, caching vectors on disk.

    Mutates each photo's `embedding_index` to its row in the returned matrix.
    Returns a (N, D) float32 array, L2-normalized.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    embedder = _load_embedder(model)
    cached_entries: Dict[str, dict] = {}
    cached_vectors: Optional[np.ndarray] = None
    if use_cache:
        cached_entries, cached_vectors = _load_cache(output_dir, embedder.name)

    new_vectors: List[np.ndarray] = []
    rows: List[np.ndarray] = []
    new_manifest: Dict[str, dict] = {}

    iterator = tqdm(photos, desc=f"embed[{model}]", unit="img") if show_progress else photos

    for photo in iterator:
        cached = cached_entries.get(photo.path)
        reuse = (
            cached is not None
            and cached.get("mtime") == photo.mtime
            and cached.get("size") == photo.size_bytes
            and cached_vectors is not None
            and cached.get("row") is not None
            and 0 <= cached["row"] < len(cached_vectors)
        )
        if reuse:
            vec = cached_vectors[cached["row"]]
        else:
            try:
                with Image.open(photo.path) as img:
                    vec = embedder.encode(img)
            except Exception:
                # Skip unreadable images; they get no embedding.
                photo.embedding_index = None
                continue

        photo.embedding_index = len(rows)
        rows.append(vec)
        new_manifest[photo.path] = {
            "row": photo.embedding_index,
            "mtime": photo.mtime,
            "size": photo.size_bytes,
        }
        if not reuse:
            new_vectors.append(vec)

    if not rows:
        return np.zeros((0, embedder.dim), dtype=np.float32)

    matrix = np.stack(rows).astype(np.float32)

    # Persist updated cache (full snapshot — keeps row indices consistent).
    np.save(output_dir / _CACHE_VECTORS, matrix)
    (output_dir / _CACHE_MANIFEST).write_text(
        json.dumps(
            {"model": embedder.name, "dim": int(matrix.shape[1]), "entries": new_manifest},
            indent=2,
        )
    )
    return matrix
