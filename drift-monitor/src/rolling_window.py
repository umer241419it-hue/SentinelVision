#!/usr/bin/env python3
"""
SentinelVision - Phase 3: Rolling Live Window
=============================================

Drift is never declared from a single unusual image. Live embeddings are
collected into a configurable rolling window:

    window_size = N   (images per comparison window)
    step_size   = S   (images advanced after each comparison)

Lifecycle:
    image 1..N  -> window not full: collect (no verdict)
    window full -> compare against reference -> slide by S -> repeat

Determinism: window IDs are deterministic given the input stream
(digest of the window's embedding bytes) and its sequence index; the same
input stream always produces the same windows.

Old embeddings rotate out according to the configuration; the buffer never
grows beyond window_size once full.
"""

import hashlib
from typing import Any, Dict, List, Optional

import numpy as np

from .reference_builder import canonical_json_bytes, sha256_bytes


class RollingWindowError(RuntimeError):
    """Raised for invalid rolling-window configuration or usage."""


class RollingWindow:
    """Fixed-size FIFO window over live embeddings."""

    def __init__(self, window_size: int, step_size: int, minimum_samples: Optional[int] = None):
        if int(window_size) <= 1:
            raise RollingWindowError("window.size must be > 1 (drift is never declared from one image).")
        if int(step_size) <= 0:
            raise RollingWindowError("window.step must be >= 1.")
        if minimum_samples is not None and int(minimum_samples) > int(window_size):
            raise RollingWindowError("window.minimum_samples cannot exceed window.size.")
        self.window_size = int(window_size)
        self.step_size = int(step_size)
        self.minimum_samples = int(minimum_samples) if minimum_samples is not None else self.window_size
        self._buffer: List[np.ndarray] = []
        self._metadata: List[Dict[str, Any]] = []
        self._seen = 0

    # -- ingestion ---------------------------------------------------------
    def add(self, embedding: np.ndarray, metadata: Optional[Dict[str, Any]] = None) -> None:
        emb = np.asarray(embedding, dtype=np.float64)
        if emb.ndim != 1:
            raise RollingWindowError(f"Embedding must be 1-D, got shape {emb.shape}.")
        self._buffer.append(emb)
        self._metadata.append(dict(metadata or {}))
        self._seen += 1
        # Rotate old embeddings out instead of growing indefinitely.
        while len(self._buffer) > self.window_size:
            self._buffer.pop(0)
            self._metadata.pop(0)

    def add_batch(
        self, embeddings: np.ndarray, metadata: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        embs = np.asarray(embeddings, dtype=np.float64)
        if embs.ndim != 2:
            raise RollingWindowError(f"Embedding batch must be 2-D, got shape {embs.shape}.")
        metas = metadata if metadata is not None else [{}] * embs.shape[0]
        if len(metas) != embs.shape[0]:
            raise RollingWindowError("metadata length must match embeddings length.")
        for i in range(embs.shape[0]):
            self.add(embs[i], metas[i])

    # -- state -------------------------------------------------------------
    def is_full(self) -> bool:
        return len(self._buffer) >= self.window_size

    def is_comparable(self) -> bool:
        """A window may only produce a verdict once it meets minimum_samples."""
        return len(self._buffer) >= self.minimum_samples

    def snapshot(self) -> "RollingWindow":
        """Immutable copy of the window at this instant. feed_stream yields
        snapshots so callers can inspect a window after the live one slides."""
        clone = RollingWindow(self.window_size, self.step_size, self.minimum_samples)
        clone._buffer = list(self._buffer)
        clone._metadata = [dict(m) for m in self._metadata]
        clone._seen = self._seen
        return clone

    def __len__(self) -> int:
        return len(self._buffer)

    def embeddings(self) -> np.ndarray:
        if not self._buffer:
            return np.zeros((0, 0), dtype=np.float64)
        return np.stack(self._buffer, axis=0)

    def slide(self) -> None:
        """Advance the window by step_size images (drops the oldest)."""
        drop = min(self.step_size, len(self._buffer))
        if drop:
            self._buffer = self._buffer[drop:]
            self._metadata = self._metadata[drop:]

    # -- window identity ----------------------------------------------------
    def window_id(self, sequence_index: int) -> str:
        """Deterministic ID: sequence index + digest of the window contents."""
        emb = self.embeddings()
        content_digest = sha256_bytes(emb.tobytes()) if emb.size else sha256_bytes(b"empty")
        return f"window-{sequence_index:06d}-{content_digest[:12]}"

    def describe(self, sequence_index: int, reference_id: str) -> Dict[str, Any]:
        """Window metadata block for evidence (task.md section 7.3)."""
        emb = self.embeddings()
        timestamps = [
            m.get("timestamp") for m in self._metadata if m.get("timestamp")
        ]
        sources = sorted(
            {str(m.get("source_id")) for m in self._metadata if m.get("source_id")}
        )
        image_ids = [m.get("image_id") for m in self._metadata if m.get("image_id")]
        return {
            "window_id": self.window_id(sequence_index),
            "sequence_index": int(sequence_index),
            "image_count": int(emb.shape[0]),
            "first_timestamp": timestamps[0] if timestamps else None,
            "last_timestamp": timestamps[-1] if timestamps else None,
            "source_ids": sources or None,
            "image_ids": image_ids if image_ids else None,
            "embedding_digest": sha256_bytes(emb.tobytes()) if emb.size else None,
            "embedding_dim": int(emb.shape[1]) if emb.ndim == 2 and emb.shape[1] else 0,
            "reference_id": reference_id,
        }


def feed_stream(
    window: RollingWindow,
    embeddings: np.ndarray,
    metadata: Optional[List[Dict[str, Any]]] = None,
):
    """Feed embeddings one at a time; yield (sequence_index, window) each time
    the window becomes comparable. The caller decides what 'comparable' means
    via window.minimum_samples; incomplete windows never yield here."""
    embs = np.asarray(embeddings, dtype=np.float64)
    if embs.ndim != 2:
        raise RollingWindowError(f"Stream must be 2-D, got shape {embs.shape}.")
    metas = metadata if metadata is not None else [{}] * embs.shape[0]
    sequence_index = 0
    for i in range(embs.shape[0]):
        window.add(embs[i], metas[i])
        if window.is_comparable():
            # Yield an immutable snapshot: the live window slides on.
            yield sequence_index, window.snapshot()
            window.slide()
            sequence_index += 1
