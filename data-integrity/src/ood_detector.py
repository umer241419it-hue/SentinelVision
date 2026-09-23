"""
SentinelVision - Data Integrity Step 2b: OOD detection (Mahalanobis distance).

Design (measured against the self-poisoned test set - see run_validation.py):

- The detector operates on STANDARDIZED embeddings (per-dimension z-score
  computed by the caller over the provided dataset). Raw layout-dominated
  descriptors make even global-Mahalanobis distances uninformative; the
  z-score removes the shared scene layout so distances measure how far an
  image deviates from what the dataset normally produces.

- The reference is CLASS-CONDITIONAL: one trimmed Gaussian (LedoitWolf
  shrinkage covariance) per given-label class. A single pooled Gaussian is
  blind to outliers whenever the clean data itself is multimodal (e.g. a
  day/night pipeline), because the between-class spread swamps the
  within-class scatter. The OOD score of an image is the MINIMUM
  Mahalanobis distance over the per-class models - the distance to the
  closest plausible class.

- Class fits are TRIMMED (default 10%): a plain mean/covariance lets the
  very outliers being hunted drag their own class model toward themselves.

- The threshold is calibrated on HELD-OUT distances with a ROBUST location+
  scale rule: median + mad_k * 1.4826 * MAD (default k=5). Two reasons:
  (1) in-sample distances understate what fresh data produces; (2) a raw
  quantile of the calibration pool is itself contaminated when the pool
  contains planted outliers - MAD has a 50% breakdown point, so up to 50%
  contamination cannot arbitrarily inflate the threshold.

D_M(x) = sqrt((x - mu_c)^T Sigma_c^+ (x - mu_c)),  score(x) = min_c D_M(x)

Fail closed: singular/insufficient class fits, NaN/Inf embeddings, and
degenerate calibrations raise OODDetectionError instead of emitting
meaningless scores.
"""

from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.covariance import LedoitWolf
from sklearn.model_selection import StratifiedKFold

OOD_DEFAULT_TRIM = 0.10
OOD_DEFAULT_MAD_K = 5.0
OOD_DEFAULT_SPLITS = 5
OOD_MIN_CLASS_SAMPLES = 8


class OODDetectionError(ValueError):
    """Raised for invalid OOD-detection inputs (fail closed)."""


class OODNotCalibratedError(RuntimeError):
    """Raised when score_embeddings is called before calibrate_threshold."""


def _validate_finite(emb: np.ndarray) -> None:
    if not np.all(np.isfinite(emb)):
        raise OODDetectionError("Embeddings contain NaN/Inf; refusing to fit OOD reference.")


def _trimmed_subset(X: np.ndarray, trim_fraction: float) -> np.ndarray:
    """Rows of X closest to the coordinate median (stable ordering)."""
    if trim_fraction <= 0:
        return X
    d0 = np.linalg.norm(X - np.median(X, axis=0), axis=1)
    keep = max(OOD_MIN_CLASS_SAMPLES, int(np.ceil(X.shape[0] * (1.0 - trim_fraction))))
    keep = min(keep, X.shape[0])
    return X[np.argsort(d0, kind="stable")[:keep]]


def _fit_one(X: np.ndarray, trim_fraction: float) -> Dict[str, Any]:
    core = _trimmed_subset(X, trim_fraction)
    if core.shape[0] < OOD_MIN_CLASS_SAMPLES:
        raise OODDetectionError(
            f"OOD class fit needs >= {OOD_MIN_CLASS_SAMPLES} samples (got {core.shape[0]})."
        )
    lw = LedoitWolf().fit(core)
    return {
        "mean": lw.location_,
        "precision": lw.precision_,
        "n_fit": int(core.shape[0]),
    }


def fit_reference(
    emb: np.ndarray,
    labels: List[str],
    trim_fraction: float = OOD_DEFAULT_TRIM,
) -> Dict[str, Any]:
    """Fit one trimmed Gaussian per class (given labels).

    Falls back to a single pooled model when every class is too small
    (< OOD_MIN_CLASS_SAMPLES samples); the pooled fit still requires the
    whole dataset to be large enough.
    """
    emb = np.asarray(emb, dtype=np.float64)
    if emb.ndim != 2 or emb.shape[0] < 2 * OOD_MIN_CLASS_SAMPLES:
        raise OODDetectionError(
            f"OOD reference needs >= {2 * OOD_MIN_CLASS_SAMPLES} embeddings (got {emb.shape})."
        )
    if not (0.0 <= trim_fraction < 0.5):
        raise OODDetectionError(f"trim_fraction must be in [0, 0.5), got {trim_fraction}.")
    _validate_finite(emb)
    label_arr = np.asarray(labels)
    if label_arr.shape[0] != emb.shape[0]:
        raise OODDetectionError("labels length must match embeddings rows.")

    classes, counts = np.unique(label_arr, return_counts=True)
    if counts.min() >= OOD_MIN_CLASS_SAMPLES:
        mode = "per_class"
        models = {
            str(c): _fit_one(emb[label_arr == c], trim_fraction) for c in classes
        }
    else:
        mode = "pooled_fallback"  # classes too small for per-class fits
        models = {"__pooled__": _fit_one(emb, trim_fraction)}

    return {
        "mode": mode,
        "classes": [str(c) for c in classes],
        "class_models": models,
        "n_reference": int(emb.shape[0]),
        "trim_fraction": float(trim_fraction),
    }


def _min_distances(emb: np.ndarray, reference: Dict[str, Any]) -> np.ndarray:
    """Minimum over class models of the Mahalanobis distance."""
    out = np.empty(emb.shape[0], dtype=np.float64)
    models = reference["class_models"]
    for r in range(emb.shape[0]):
        x = emb[r]
        best = np.inf
        for m in models.values():
            d = x - m["mean"]
            v = np.sqrt(max(float(d @ m["precision"] @ d), 0.0))
            if v < best:
                best = v
        if not np.isfinite(best):
            raise OODDetectionError("Mahalanobis distance computation produced NaN/Inf.")
        out[r] = best
    return out


def mahalanobis_distances(emb: np.ndarray, reference: Dict[str, Any]) -> np.ndarray:
    """OOD score (min class-conditional Mahalanobis distance) for each row."""
    emb = np.asarray(emb, dtype=np.float64)
    _validate_finite(emb)
    if emb.ndim != 2:
        raise OODDetectionError(f"Embeddings must be 2-D, got {emb.shape}.")
    return _min_distances(emb, reference)


def calibrate_threshold(
    emb: np.ndarray,
    labels: List[str],
    trim_fraction: float = OOD_DEFAULT_TRIM,
    n_splits: int = OOD_DEFAULT_SPLITS,
    seed: int = 42,
    mad_k: float = OOD_DEFAULT_MAD_K,
) -> Dict[str, Any]:
    """Held-out, contamination-robust null calibration.

    Stratified k-fold over the given labels: each fold is scored against
    class models fit on the other folds, yielding out-of-sample distances
    for genuinely in-distribution-style data. The threshold is

        median(held-out) + mad_k * 1.4826 * MAD(held-out)

    which tolerates up to ~50% contaminated calibration samples (the planted
    OOD images themselves are in this pool - that is exactly why a raw
    quantile is not used).
    """
    emb = np.asarray(emb, dtype=np.float64)
    _validate_finite(emb)
    n = emb.shape[0]
    if n < 4 * OOD_MIN_CLASS_SAMPLES:
        raise OODDetectionError(
            f"OOD calibration needs >= {4 * OOD_MIN_CLASS_SAMPLES} embeddings (got {n})."
        )
    label_arr = np.asarray(labels)
    if label_arr.shape[0] != n:
        raise OODDetectionError("labels length must match embeddings rows.")
    classes, counts = np.unique(label_arr, return_counts=True)
    if counts.min() < 2:
        raise OODDetectionError("Each class needs >= 2 samples for stratified calibration.")
    if mad_k <= 0:
        raise OODDetectionError(f"mad_k must be positive, got {mad_k}.")

    n_splits = max(2, min(int(n_splits), int(counts.min())))
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    held_parts: List[np.ndarray] = []
    for train_idx, test_idx in skf.split(emb, label_arr):
        ref = fit_reference(emb[train_idx], label_arr[train_idx], trim_fraction=trim_fraction)
        held_parts.append(_min_distances(emb[test_idx], ref))
    held = np.concatenate(held_parts)

    med = float(np.median(held))
    mad = float(np.median(np.abs(held - med)))
    threshold = med + float(mad_k) * 1.4826 * mad
    if not np.isfinite(threshold) or threshold <= 0:
        raise OODDetectionError(
            f"OOD calibration produced a degenerate threshold ({threshold}); "
            "check the embedding configuration."
        )
    return {
        "threshold": float(threshold),
        "method": "held_out_median_mad",
        "mad_k": float(mad_k),
        "calibration_median": med,
        "calibration_mad": mad,
        "trim_fraction": float(trim_fraction),
        "n_splits": int(n_splits),
        "seed": int(seed),
        "held_out_count": int(held.shape[0]),
        "held_out_summary": {
            "median": med,
            "mad": mad,
            "mean": float(held.mean()),
            "std": float(held.std()),
            "max": float(held.max()),
        },
    }


def score_embeddings(
    emb: np.ndarray, reference: Dict[str, Any], threshold_info: Dict[str, Any]
) -> Dict[str, Any]:
    """Score every embedding against the calibrated class-conditional
    reference; flag distances above the threshold."""
    distances = mahalanobis_distances(emb, reference)
    threshold = float(threshold_info["threshold"])
    ood = distances > threshold
    flagged_ids = [int(i) for i in np.where(ood)[0]]
    return {
        "distances": [float(d) for d in distances],
        "threshold": threshold,
        "threshold_method": threshold_info.get("method"),
        "flagged_indices": flagged_ids,
        "n_flagged": len(flagged_ids),
        "n_images": int(emb.shape[0]),
        "reference_mode": reference.get("mode"),
    }
