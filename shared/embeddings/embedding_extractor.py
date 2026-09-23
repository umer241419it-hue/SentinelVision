#!/usr/bin/env python3
"""
SentinelVision - Shared Frozen Image Embedding Extractor
=========================================================

A single, reusable embedding pipeline shared by the Drift Monitoring module
and future modules (e.g. Data Integrity). There is exactly ONE embedding
implementation per backbone configuration so all modules compare the same
representation.

Design rules (task.md sections 5 + 18):
- The backbone is FROZEN: it is never trained or fine-tuned here.
- OFFLINE ONLY: this extractor never downloads weights at runtime. If local
  weights are missing it raises MissingWeightsError with an actionable message.
- Preprocessing is centralized here and recorded in metadata(), because
  changing preprocessing changes the embedding distribution.
- Deterministic: inference runs in eval mode; the same image plus the same
  configuration yields the same embedding within documented float tolerance.

Backbones:
- "resnet50"  : frozen torchvision ResNet-50 (avgpool, 2048-d), requires the
                optional `torch`/`torchvision` extras AND local weights at
                config.embedding.weights_path (or TORCH_HOME cache).
- "pixelstat" : dependency-free deterministic 864-d image-statistics
                descriptor (grayscale layout moments + RGB channel moments).
                Always available; used for offline development, tests and the
                bridge-connected demo when ResNet-50 weights are absent.

The backbone registry lets a future backbone (e.g. CLIP) be added without
rewriting the drift detector.
"""

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

import numpy as np

try:  # Pillow is a hard dependency for image loading.
    from PIL import Image, ImageStat

    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - environment issue, surfaced clearly
    PIL_AVAILABLE = False

try:  # torch is an OPTIONAL dependency (resnet50 backbone only).
    import torch
    import torchvision

    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover - optional extra
    TORCH_AVAILABLE = False

PREPROCESSING_VERSION = "preprocess-v1"

# Canonical preprocessing parameters (recorded verbatim in metadata).
RESNET50_PREPROCESSING = {
    "resize": [256, 256],
    "center_crop": [224, 224],
    "interpolation": "bilinear",
    "color": "RGB",
    "tensor_range": [0.0, 1.0],
    "normalize_mean": [0.485, 0.456, 0.406],
    "normalize_std": [0.229, 0.224, 0.225],
}

PIXELSTAT_PREPROCESSING = {
    "resize": [64, 64],
    "resize_method": "area_antialias",
    "color": "RGB",
    "tensor_range": [0.0, 1.0],
}

# 224x224 / (7x7 pooling) -> 32 spatial cells per channel-moment grid.
PIXELSTAT_GRID = 8
# 8x8 grid x {mean, std, P90} x 3 RGB channels + 9 global moments x 3 channels
# + 8x8 grayscale {mean, std} + 3 grayscale globals.
PIXELSTAT_DIM = (PIXELSTAT_GRID * PIXELSTAT_GRID * 3 * 3) + (3 * 9) + (PIXELSTAT_GRID * PIXELSTAT_GRID * 2) + 3  # 734


class EmbeddingError(RuntimeError):
    """Base class for embedding pipeline failures (fail closed)."""


class MissingWeightsError(EmbeddingError):
    """Raised when local frozen weights are required but unavailable.

    The extractor must NEVER fall back to a network download (air-gapped
    requirement, task.md section 18). Callers see this error and can point
    the operator at the configuration that needs fixing.
    """


def _require_pil() -> None:
    if not PIL_AVAILABLE:
        raise EmbeddingError(
            "Pillow is required for image loading. Install it with: pip install pillow"
        )


def sha256_file(path: str) -> str:
    """Streaming SHA-256 of a file (used for local weight-file digests)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class TorchResNet50Extractor:
    """Frozen torchvision ResNet-50 pooling-layer extractor (2048-d).

    Requires local weights; never downloads. Weights are resolved from:
      1. config.embedding.weights_path (file on disk), or
      2. the local TORCH_HOME hub cache (torchvision cache layout).
    """

    name = "resnet50"
    embedding_dim = 2048

    def __init__(self, config: Dict[str, Any]):
        if not TORCH_AVAILABLE:
            raise EmbeddingError(
                "Backbone 'resnet50' requires the optional torch/torchvision extras. "
                "Install them locally (pip install torch torchvision) or use the "
                "'pixelstat' backbone for offline development without model weights."
            )
        self._config = dict(config)
        self._device_name = self._resolve_device(config.get("device", "auto"))
        self._weights_path = self._resolve_local_weights(config.get("weights_path"))
        self._weights_sha256 = sha256_file(self._weights_path)

        # torch.load_state_dict from a local state_dict file.
        try:
            self._model = torchvision.models.resnet50(weights=None)
        except TypeError:  # older torchvision
            self._model = torchvision.models.resnet50(pretrained=False)
        state = torch.load(
            self._weights_path, map_location="cpu", weights_only=True
        )
        self._model.load_state_dict(state)
        # Drop the classification head; keep the frozen pooling representation.
        self._model.fc = torch.nn.Identity()
        self._model.eval()  # FROZEN + eval mode: no training, deterministic.
        for p in self._model.parameters():
            p.requires_grad_(False)
        if self._device_name != "cpu":
            self._model = self._model.to(self._device_name)

    @staticmethod
    def _resolve_device(requested: str) -> str:
        if not TORCH_AVAILABLE:  # pragma: no cover
            return "cpu"
        if requested == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if requested.startswith("cuda") and not torch.cuda.is_available():
            raise EmbeddingError(
                f"device='{requested}' requested but CUDA is not available."
            )
        return requested

    @staticmethod
    def _resolve_local_weights(explicit_path: Optional[str]) -> str:
        candidates: List[str] = []
        if explicit_path:
            candidates.append(explicit_path)
        torch_home = os.environ.get("TORCH_HOME", os.path.expanduser("~/.cache/torch"))
        cache_name = "resnet50-0676ba61.pth"  # torchvision ResNet50_Weights.IMAGENET1K_V1
        candidates.append(
            os.path.join(torch_home, "hub", "checkpoints", cache_name)
        )
        candidates.append(os.path.join(torch_home, "checkpoints", cache_name))
        for cand in candidates:
            if cand and os.path.isfile(cand):
                return os.path.abspath(cand)
        raise MissingWeightsError(
            "Local ResNet-50 weights not found. This module is OFFLINE: it will "
            "not download weights at runtime. Provide them via "
            "config.embedding.weights_path (a ResNet-50 ImageNet-V1 state_dict "
            f"file) or place '{cache_name}' in the torch cache. Checked: "
            + ", ".join(c for c in candidates if c)
        )

    def extract_batch(self, images: List[Any]) -> np.ndarray:
        if not images:
            raise EmbeddingError("extract_batch called with an empty image list.")
        import torch as _torch

        tensors = []
        for img in images:
            tensors.append(self._preprocess(img))
        batch = _torch.stack(tensors).to(self._device_name)
        with _torch.no_grad():
            out = self._model(batch)
        emb = out.detach().cpu().numpy().astype(np.float64)
        if emb.ndim != 2 or emb.shape[1] != self.embedding_dim:
            raise EmbeddingError(
                f"Unexpected backbone output shape {emb.shape}; expected (*, {self.embedding_dim})."
            )
        return emb

    def _preprocess(self, image: Any):
        import torch as _torch
        import torchvision.transforms as T

        img = self._coerce_pil(image)
        cfg = RESNET50_PREPROCESSING
        transform = T.Compose(
            [
                T.Resize(tuple(cfg["resize"]), interpolation=T.InterpolationMode.BILINEAR, antialias=True),
                T.CenterCrop(tuple(cfg["center_crop"])),
                T.ToTensor(),
                T.Normalize(mean=cfg["normalize_mean"], std=cfg["normalize_std"]),
            ]
        )
        return transform(img)

    @staticmethod
    def _coerce_pil(image: Any):
        _require_pil()
        if isinstance(image, Image.Image):
            return image.convert("RGB")
        # numpy array (H, W, 3) uint8/float
        arr = np.asarray(image)
        if arr.ndim != 3 or arr.shape[2] != 3:
            raise EmbeddingError(f"Unsupported image array shape: {arr.shape}")
        if arr.dtype != np.uint8:
            arr = np.clip(arr, 0, 255).astype(np.uint8)
        return Image.fromarray(arr, mode="RGB")

    def metadata(self) -> Dict[str, Any]:
        return {
            "backbone": self.name,
            "embedding_dim": self.embedding_dim,
            "preprocessing_version": PREPROCESSING_VERSION,
            "preprocessing": dict(RESNET50_PREPROCESSING),
            "device": self._device_name,
            "weights_path": self._weights_path,
            "weights_sha256": self._weights_sha256,
            "frozen": True,
            "mode": "eval",
        }


class PixelStatExtractor:
    """Deterministic 734-d image-statistics descriptor (no model weights).

    Layout (fixed for a given preprocessing version):
      - 8x8 grid x {mean, std, P90} per RGB channel      -> 576 dims
      - per-channel global moments (mean, std, P90, P10, skewness, kurtosis,
        RMS gradient, P90 gradient, max)                 -> 27 dims
      - grayscale layout moments: 8x8 mean + 8x8 std     -> 128 dims
      - grayscale global (P10, RMS contrast, edge density) -> 3 dims
    Total: 734 dims (matches the class's computed embedding_dim).

    Fully deterministic, dependency-free (numpy + Pillow) and offline, which
    makes it the development/test backbone when ResNet-50 weights are absent.
    """

    name = "pixelstat"
    embedding_dim = PIXELSTAT_DIM  # single source of truth for the descriptor layout

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = dict(config or {})

    def extract_batch(self, images: List[Any]) -> np.ndarray:
        _require_pil()
        if not images:
            raise EmbeddingError("extract_batch called with an empty image list.")
        out = np.zeros((len(images), self.embedding_dim), dtype=np.float64)
        for i, image in enumerate(images):
            out[i, :] = self._embed_one(image)
        return out

    # -- interface ---------------------------------------------------------
    def extract(self, image: Any) -> np.ndarray:
        return self.extract_batch([image])[0]

    def metadata(self) -> Dict[str, Any]:
        return {
            "backbone": self.name,
            "embedding_dim": self.embedding_dim,
            "preprocessing_version": PREPROCESSING_VERSION,
            "preprocessing": dict(PIXELSTAT_PREPROCESSING),
            "grid": PIXELSTAT_GRID,
            "frozen": True,
            "mode": "deterministic_statistical",
        }

    # -- internals ---------------------------------------------------------
    def _embed_one(self, image: Any) -> np.ndarray:
        img = self._coerce_pil(image)
        cfg = PIXELSTAT_PREPROCESSING
        size = tuple(cfg["resize"])
        img = img.resize(size, Image.BOX)  # deterministic area-style resample
        arr = np.asarray(img, dtype=np.float64) / 255.0  # (H, W, 3) in [0, 1]
        if arr.ndim != 3 or arr.shape[2] != 3:
            raise EmbeddingError(f"Unsupported image array shape: {arr.shape}")

        g = PIXELSTAT_GRID
        h, w = arr.shape[0], arr.shape[1]
        ch, cw = h // g, w // g

        feats: List[float] = []
        # Per-channel 8x8 grid: mean, std, 90th percentile.
        for c in range(3):
            plane = arr[:, :, c]
            for i in range(g):
                for j in range(g):
                    cell = plane[i * ch:(i + 1) * ch, j * cw:(j + 1) * cw]
                    feats.append(float(cell.mean()))
                    feats.append(float(cell.std()))
                    feats.append(float(np.percentile(cell, 90)))
        # Per-channel global moments.
        for c in range(3):
            plane = arr[:, :, c]
            p10, p90 = np.percentile(plane, [10, 90])
            centered = plane - plane.mean()
            std = plane.std()
            skew = float((centered ** 3).mean() / (std ** 3 + 1e-12))
            kurt = float((centered ** 4).mean() / (std ** 4 + 1e-12))
            gy, gx = np.gradient(plane)
            grad_mag = np.sqrt(gx * gx + gy * gy)
            feats.extend(
                [
                    float(plane.mean()),
                    float(std),
                    float(p90),
                    float(p10),
                    skew,
                    kurt,
                    float(grad_mag.mean()),
                    float(np.percentile(grad_mag, 90)),
                    float(plane.max()),
                ]
            )
        # Grayscale layout: 8x8 mean + 8x8 std.
        gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
        for i in range(g):
            for j in range(g):
                cell = gray[i * ch:(i + 1) * ch, j * cw:(j + 1) * cw]
                feats.append(float(cell.mean()))
        for i in range(g):
            for j in range(g):
                cell = gray[i * ch:(i + 1) * ch, j * cw:(j + 1) * cw]
                feats.append(float(cell.std()))
        # Grayscale global extras: P10, RMS contrast, edge density.
        p10 = float(np.percentile(gray, 10))
        rms_contrast = float(gray.std())
        gy, gx = np.gradient(gray)
        edges = (np.sqrt(gx * gx + gy * gy) > 0.08)
        feats.extend([p10, rms_contrast, float(edges.mean())])

        vec = np.asarray(feats, dtype=np.float64)
        if vec.shape[0] != self.embedding_dim or not np.all(np.isfinite(vec)):
            raise EmbeddingError("pixelstat embedding failed finiteness/dimension check.")
        return vec

    @staticmethod
    def _coerce_pil(image: Any):
        if isinstance(image, Image.Image):
            return image.convert("RGB")
        arr = np.asarray(image)
        if arr.ndim != 3 or arr.shape[2] != 3:
            raise EmbeddingError(f"Unsupported image array shape: {arr.shape}")
        if arr.dtype != np.uint8:
            arr = np.clip(arr, 0, 255).astype(np.uint8)
        return Image.fromarray(arr, mode="RGB")


_REGISTRY = {
    "resnet50": TorchResNet50Extractor,
    "pixelstat": PixelStatExtractor,
}


def register_backbone(name: str, extractor_cls) -> None:
    """Register a custom backbone (e.g. CLIP later) without touching modules."""
    _REGISTRY[name] = extractor_cls


def create_extractor(config: Dict[str, Any]):
    """Build an extractor from an `embedding` config dict (backbone etc.)."""
    backbone = (config or {}).get("backbone", "pixelstat")
    cls = _REGISTRY.get(backbone)
    if cls is None:
        raise EmbeddingError(
            f"Unknown backbone '{backbone}'. Available: {sorted(_REGISTRY)}"
        )
    return cls(config or {})


def load_image(path: str):
    """Load an image file as a deterministic RGB PIL image (fail closed)."""
    _require_pil()
    if not os.path.isfile(path):
        raise EmbeddingError(f"Image file not found: {path}")
    try:
        with Image.open(path) as im:
            return im.convert("RGB")
    except Exception as exc:
        raise EmbeddingError(f"Failed to load image '{path}': {exc}") from exc


def metadata_json(extractor) -> str:
    """Stable JSON serialization of extractor metadata (for digests)."""
    return json.dumps(extractor.metadata(), sort_keys=True, separators=(",", ":"))
