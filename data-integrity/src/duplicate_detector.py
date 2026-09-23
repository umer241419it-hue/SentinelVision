"""
SentinelVision - Step 2a: duplicate detection via cosine similarity.

Threshold semantics (Stage 6 guide: start at 0.98, tune from test results):

Raw cosine on layout-dominated embeddings is degenerate - every image shares
the same coarse scene layout, so raw similarities concentrate near 0.9999 and
a 0.98 threshold flags everything. The detector therefore scores cosine on
STANDARDIZED embeddings (per-dimension z-score over the provided dataset,
computed by the caller and passed in as mu/sd). This preserves the exact
duplicate signal (identical vectors stay at 1.0) while spreading distinct
images apart: on the self-poisoned test set this separates byte-copies
(similarity 1.000) from the most-similar non-duplicate pair (0.980) with a
clean margin around the 0.99 operating threshold.

Standardization statistics must come from the dataset being checked (or a
trusted clean reference) - they are recorded in the result and the evidence.
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

DUPLICATE_DEFAULT_THRESHOLD = 0.99


def standardization_stats(emb: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Per-dimension mean/std for standardization (never divides by ~0)."""
    emb = np.asarray(emb, dtype=np.float64)
    if emb.ndim != 2 or emb.shape[0] < 2:
        raise DuplicateDetectionError(
            f"Standardization needs a 2-D array with >= 2 rows (got {emb.shape})."
        )
    mu = emb.mean(axis=0)
    sd = emb.std(axis=0)
    sd = np.where(sd < 1e-12, 1.0, sd)
    return mu, sd


def standardize(emb: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    return (np.asarray(emb, dtype=np.float64) - mu) / sd


class DuplicateDetectionError(ValueError):
    """Raised for invalid duplicate-detection inputs (fail closed)."""


def pairwise_cosine_similarity(emb: np.ndarray) -> np.ndarray:
    """Full pairwise cosine-similarity matrix (rejects zero-norm rows)."""
    emb = np.asarray(emb, dtype=np.float64)
    if emb.ndim != 2:
        raise DuplicateDetectionError(f"Embeddings must be 2-D, got {emb.shape}.")
    norms = np.linalg.norm(emb, axis=1)
    if np.any(norms <= 0.0):
        raise DuplicateDetectionError("Zero-norm embedding found; cannot compute cosine similarity.")
    unit = emb / norms[:, None]
    return unit @ unit.T


def find_duplicates(
    emb: np.ndarray,
    image_ids: List[str],
    threshold: float = DUPLICATE_DEFAULT_THRESHOLD,
    standardization: Optional[Tuple[np.ndarray, np.ndarray]] = None,
) -> Dict[str, Any]:
    """Flag near-duplicate pairs by standardized cosine similarity.

    standardization: optional (mu, sd) from standardization_stats(). When
    provided, similarities are computed on (emb - mu) / sd.
    """
    if len(image_ids) != emb.shape[0]:
        raise DuplicateDetectionError(
            f"image_ids length {len(image_ids)} != embeddings rows {emb.shape[0]}."
        )
    if len(set(image_ids)) != len(image_ids):
        raise DuplicateDetectionError("image_ids must be unique.")
    if not (0.0 < threshold <= 1.0):
        raise DuplicateDetectionError(f"similarity_threshold must be in (0, 1], got {threshold}.")

    if standardization is not None:
        mu, sd = standardization
        emb = standardize(emb, mu, sd)
        norms = np.linalg.norm(emb, axis=1)
        norms = np.where(norms < 1e-12, 1.0, norms)
        unit = emb / norms[:, None]
        sim = unit @ unit.T
        scoring = "standardized_cosine"
    else:
        sim = pairwise_cosine_similarity(emb)
        scoring = "raw_cosine"

    n = sim.shape[0]
    iu, ju = np.triu_indices(n, k=1)
    scores = sim[iu, ju]
    hit = scores >= threshold

    pairs = [
        {
            "image_a": image_ids[int(i)],
            "image_b": image_ids[int(j)],
            "similarity": round(float(s), 6),
        }
        for i, j, s in zip(iu[hit], ju[hit], scores[hit])
    ]
    pairs.sort(key=lambda p: (-p["similarity"], p["image_a"], p["image_b"]))

    flagged = sorted({p["image_a"] for p in pairs} | {p["image_b"] for p in pairs})
    return {
        "threshold": float(threshold),
        "scoring": scoring,
        "pairs": pairs,
        "flagged_image_ids": flagged,
        "n_pairs": len(pairs),
        "n_images": int(n),
    }


# -- shared transform helpers used by the checker and other checks -----------
def compute_standardization(emb: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Convenience wrapper returning (mu, sd) for the given embeddings."""
    return standardization_stats(emb)


def zscore(emb: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    """Standardize embeddings with the provided statistics."""
    return standardize(emb, mu, sd)
