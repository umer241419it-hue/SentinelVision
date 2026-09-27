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
DUPLICATE_BATCH_SIZE = 256


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


try:
    import torch
    TORCH_CUDA_AVAILABLE = torch.cuda.is_available()
except ImportError:
    TORCH_CUDA_AVAILABLE = False


class DuplicateDetectionError(ValueError):
    """Raised for invalid duplicate-detection inputs (fail closed)."""


def pairwise_cosine_similarity(emb: np.ndarray, use_gpu: bool = True) -> np.ndarray:
    """Full pairwise cosine-similarity matrix on GPU (CUDA) when available, fallback to CPU."""
    emb = np.asarray(emb, dtype=np.float32)
    if emb.ndim != 2:
        raise DuplicateDetectionError(f"Embeddings must be 2-D, got {emb.shape}.")
    norms = np.linalg.norm(emb, axis=1)
    if np.any(norms <= 0.0):
        raise DuplicateDetectionError("Zero-norm embedding found; cannot compute cosine similarity.")
    unit = emb / norms[:, None]

    if use_gpu and TORCH_CUDA_AVAILABLE:
        try:
            t_unit = torch.as_tensor(unit, device="cuda", dtype=torch.float32)
            sim = torch.mm(t_unit, t_unit.t()).cpu().numpy()
            return sim.astype(np.float64)
        except Exception:
            pass  # Fall back to CPU gracefully if GPU OOM or error occurs

    return (unit @ unit.T).astype(np.float64)


def find_duplicates(
    emb: np.ndarray,
    image_ids: List[str],
    threshold: float = DUPLICATE_DEFAULT_THRESHOLD,
    standardization: Optional[Tuple[np.ndarray, np.ndarray]] = None,
    batch_size: int = DUPLICATE_BATCH_SIZE,
) -> Dict[str, Any]:
    """Flag near-duplicate pairs by standardized cosine similarity.

    standardization: optional (mu, sd) from standardization_stats(). When
    provided, similarities are computed on (emb - mu) / sd.
    Evaluates pairs in memory-bounded batches to prevent O(N^2) memory explosion.
    """
    if len(image_ids) != emb.shape[0]:
        raise DuplicateDetectionError(
            f"image_ids length {len(image_ids)} != embeddings rows {emb.shape[0]}."
        )
    if len(set(image_ids)) != len(image_ids):
        raise DuplicateDetectionError("image_ids must be unique.")
    if not (0.0 < threshold <= 1.0):
        raise DuplicateDetectionError(f"similarity_threshold must be in (0, 1], got {threshold}.")

    n = len(image_ids)
    if n < 2:
        return {
            "threshold": float(threshold),
            "scoring": "standardized_cosine" if standardization is not None else "raw_cosine",
            "pairs": [],
            "flagged_image_ids": [],
            "n_pairs": 0,
            "n_images": int(n),
        }

    if standardization is not None:
        mu, sd = standardization
        emb_proc = standardize(emb, mu, sd)
        norms = np.linalg.norm(emb_proc, axis=1)
        norms = np.where(norms < 1e-12, 1.0, norms)
        unit = (emb_proc / norms[:, None]).astype(np.float32)
        scoring = "standardized_cosine"
    else:
        emb_proc = np.asarray(emb, dtype=np.float32)
        if emb_proc.ndim != 2:
            raise DuplicateDetectionError(f"Embeddings must be 2-D, got {emb_proc.shape}.")
        norms = np.linalg.norm(emb_proc, axis=1)
        if np.any(norms <= 0.0):
            raise DuplicateDetectionError("Zero-norm embedding found; cannot compute cosine similarity.")
        unit = (emb_proc / norms[:, None]).astype(np.float32)
        scoring = "raw_cosine"

    raw_pairs: List[Tuple[int, int, float]] = []

    use_cuda = TORCH_CUDA_AVAILABLE
    if use_cuda:
        try:
            t_unit = torch.as_tensor(unit, device="cuda", dtype=torch.float32)
            t_unit_t = t_unit.t()
            thresh_t = float(threshold)

            for start in range(0, n, batch_size):
                end = min(start + batch_size, n)
                b_unit = t_unit[start:end]
                sim_b = torch.mm(b_unit, t_unit_t)

                hits = torch.nonzero(sim_b >= thresh_t, as_tuple=False)
                if hits.numel() > 0:
                    local_i = hits[:, 0]
                    global_j = hits[:, 1]
                    global_i = start + local_i
                    upper = global_i < global_j
                    if upper.any():
                        valid_i = global_i[upper].cpu().numpy()
                        valid_j = global_j[upper].cpu().numpy()
                        valid_scores = sim_b[local_i[upper], global_j[upper]].cpu().numpy()
                        for i_idx, j_idx, s in zip(valid_i, valid_j, valid_scores):
                            raw_pairs.append((int(i_idx), int(j_idx), float(s)))

                del sim_b

            del t_unit, t_unit_t
        except Exception:
            use_cuda = False
            raw_pairs.clear()
            if TORCH_CUDA_AVAILABLE:
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

    if not use_cuda:
        unit_t = unit.T
        thresh_f = float(threshold)
        for start in range(0, n, batch_size):
            end = min(start + batch_size, n)
            b_unit = unit[start:end]
            sim_b = b_unit @ unit_t

            local_i, global_j = np.nonzero(sim_b >= thresh_f)
            if len(local_i) > 0:
                global_i = start + local_i
                upper = global_i < global_j
                if np.any(upper):
                    valid_i = global_i[upper]
                    valid_j = global_j[upper]
                    valid_scores = sim_b[local_i[upper], valid_j]
                    for i_idx, j_idx, s in zip(valid_i, valid_j, valid_scores):
                        raw_pairs.append((int(i_idx), int(j_idx), float(s)))

            del sim_b

    pairs = [
        {
            "image_a": image_ids[i],
            "image_b": image_ids[j],
            "similarity": round(float(s), 6),
        }
        for i, j, s in raw_pairs
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
