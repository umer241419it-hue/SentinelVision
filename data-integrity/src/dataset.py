"""
SentinelVision - Data Integrity dataset loader + embedding cache.

Loads the labeled image set (image files + given labels + optional
ground-truth answer key), embeds every image with the SHARED frozen extractor
(shared/embeddings/embedding_extractor.py), and caches embeddings to disk
keyed by image id and validated against file sha256, so detectors never
recompute embeddings across runs (Stage 6 Step 1: "Cache embeddings, don't
recompute").

Cache rules (fail closed, never silently stale):
- a cached entry is used only if its sha256 matches the file's CURRENT bytes
  and the cached embedding_dim matches the configured extractor;
- the cache is discarded wholesale if the backbone changed.
"""

import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from . import ensure_shared_importable  # noqa: F401  (path bootstrap)

from shared.embeddings.embedding_extractor import (
    EmbeddingError,
    create_extractor,
    load_image,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


class DatasetError(RuntimeError):
    """Raised when the dataset/labels cannot be loaded (fail closed)."""


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_images(input_dir: str) -> List[str]:
    """Deterministically list image files directly under input_dir (sorted)."""
    if not os.path.isdir(input_dir):
        raise DatasetError(f"Image directory not found: {input_dir}")
    found = [
        name
        for name in sorted(os.listdir(input_dir))
        if os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS
        and os.path.isfile(os.path.join(input_dir, name))
    ]
    if not found:
        raise DatasetError(f"No images found under {input_dir}")
    return found


def load_labels(path: Optional[str], image_ids: List[str]) -> Dict[str, str]:
    """Load the labels sidecar and validate coverage (fail closed).

    Accepted shapes: {"img.png": "day", ...}, {"labels": {...}}, and the
    answer-key format {"labels": {image_id: {"given_label": ...}}}. Every
    image must have exactly one label and no unknown ids are allowed - an
    unpaired label would silently corrupt confident learning.
    """
    if not path:
        raise DatasetError(
            "labels_path is required: confident learning needs the given labels."
        )
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise DatasetError(f"Labels file '{path}' must be a JSON object.")
    labels_raw = raw.get("labels", raw)
    if not isinstance(labels_raw, dict):
        raise DatasetError(f"Labels file '{path}' has no labels object.")

    normalized: Dict[str, str] = {}
    for k, v in labels_raw.items():
        if isinstance(v, dict):
            if "given_label" not in v:
                raise DatasetError(f"Label entry for '{k}' missing 'given_label'.")
            normalized[k] = str(v["given_label"])
        elif isinstance(v, str):
            normalized[k] = v
        else:
            raise DatasetError(f"Label entry for '{k}' must be a string or object.")

    missing = [i for i in image_ids if i not in normalized]
    if missing:
        raise DatasetError(
            f"Labels file missing entries for {len(missing)} images, e.g. {missing[:3]}"
        )
    unknown = [k for k in normalized if k not in set(image_ids)]
    if unknown:
        raise DatasetError(
            f"Labels file contains {len(unknown)} unknown image ids, e.g. {unknown[:3]}"
        )
    return normalized


def load_answer_key(path: Optional[str]) -> Optional[Dict[str, Any]]:
    """Load the optional ground-truth answer key (validation only)."""
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return raw.get("labels", raw)


class ImageDataset:
    """Labeled image dataset with cached shared-pipeline embeddings."""

    def __init__(
        self,
        input_dir: str,
        labels: Dict[str, str],
        extractor_config: Dict[str, Any],
        cache_path: Optional[str] = None,
    ):
        self.input_dir = input_dir
        self.image_ids: List[str] = list(labels.keys())
        self.labels: Dict[str, str] = dict(labels)
        self.extractor = create_extractor(extractor_config)
        self.extractor_metadata = self.extractor.metadata()
        self.cache_path = cache_path
        self._cache: Dict[str, Any] = self._load_cache()

    # -- paths ---------------------------------------------------------------
    def path_of(self, image_id: str) -> str:
        return os.path.join(self.input_dir, image_id)

    def file_hash(self, image_id: str) -> str:
        return sha256_file(self.path_of(image_id))

    # -- embedding access -----------------------------------------------------
    def embeddings(self, force_recompute: bool = False) -> np.ndarray:
        """Return (n_images, dim) embeddings from cache/extractor.

        Cached entries are used only when their sha256 matches the current
        file bytes and the dimension matches the configured extractor.
        Newly embedded images are written back to the cache.
        """
        if force_recompute:
            self._cache = {}
        embs: List[Optional[np.ndarray]] = [None] * len(self.image_ids)
        to_embed: List[int] = []
        for idx, image_id in enumerate(self.image_ids):
            digest = self.file_hash(image_id)
            cached = self._cache.get(image_id)
            if (
                cached is not None
                and cached.get("sha256") == digest
                and cached.get("embedding_dim") == self.extractor_metadata["embedding_dim"]
            ):
                embs[idx] = np.asarray(cached["embedding"], dtype=np.float64)
            else:
                to_embed.append(idx)

        if to_embed:
            batch_size = 32
            for start in range(0, len(to_embed), batch_size):
                chunk = to_embed[start:start + batch_size]
                images = [load_image(self.path_of(self.image_ids[i])) for i in chunk]
                batch = self.extractor.extract_batch(images)
                for i, vec in zip(chunk, batch):
                    vec = np.asarray(vec, dtype=np.float64)
                    embs[i] = vec
                    self._cache[self.image_ids[i]] = {
                        "sha256": self.file_hash(self.image_ids[i]),
                        "embedding": [float(v) for v in vec],
                        "embedding_dim": int(vec.shape[0]),
                    }
            self._save_cache()
        return np.stack(embs, axis=0)

    # -- cache -----------------------------------------------------------------
    def _load_cache(self) -> Dict[str, Any]:
        if not self.cache_path or not os.path.isfile(self.cache_path):
            return {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
        if raw.get("backbone") != self.extractor_metadata["backbone"]:
            return {}  # different representation: stale cache, ignore it
        return dict(raw.get("images", {}))

    def _save_cache(self) -> None:
        if not self.cache_path:
            return
        if self.cache_path:
            os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
        payload = {
            "backbone": self.extractor_metadata["backbone"],
            "embedding_dim": self.extractor_metadata["embedding_dim"],
            "images": self._cache,
        }
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)


def build_dataset(
    input_dir: str,
    labels_path: str,
    extractor_config: Dict[str, Any],
    cache_path: Optional[str] = None,
) -> Tuple[ImageDataset, Dict[str, Any]]:
    """Discover images, validate labels, and return (dataset, metadata)."""
    image_ids = discover_images(input_dir)
    labels = load_labels(labels_path, image_ids)
    dataset = ImageDataset(input_dir, labels, extractor_config, cache_path)
    return dataset, {
        "input_dir": input_dir,
        "image_count": len(image_ids),
        "label_distribution": {
            str(v): sum(1 for x in labels.values() if x == v)
            for v in sorted(set(labels.values()))
        },
        "extractor": dataset.extractor_metadata,
    }
