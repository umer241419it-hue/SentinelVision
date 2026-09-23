#!/usr/bin/env python3
"""
SentinelVision - Phase 4: Maximum Mean Discrepancy (MMD)
========================================================

Core distribution-shift detector. Computes the empirical MMD between
reference-battery embeddings and a rolling window of live embeddings using
an RBF (Gaussian) kernel:

    MMD^2 = mean(k(x,x')) over ref pairs
          + mean(k(y,y')) over live pairs
          - 2 * mean(k(x,y)) over cross pairs

Numerical stability (task.md 8.4): every input is validated (empty arrays,
dimension mismatch, NaN/Inf, insufficient live samples); failures raise
MMDValidationError so callers fail CLOSED instead of emitting a misleading
score.

Kernel bandwidth: never an undocumented magic number. Either an explicit
float from config, or a deterministic data-driven heuristic
("auto" = median heuristic on the pooled sample, "reference_median" =
median pairwise distance of the reference alone). The selected value and
its provenance are always reported in the result and end up in the evidence.

Optional significance test: MMD-based permutation test with a fixed seed;
the permutation procedure never calls unseeded global RNG state.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np


class MMDValidationError(ValueError):
    """Raised when MMD inputs are invalid; callers must fail closed."""


@dataclass
class MMDResult:
    mmd: float
    kernel: str
    kernel_parameters: Dict[str, Any]
    reference_count: int
    live_count: int
    bandwidth: float
    bandwidth_source: str
    p_value: Optional[float] = None
    permutation_count: int = 0
    seed: Optional[int] = None
    null_distribution: Optional[Dict[str, Any]] = field(default=None)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mmd": float(self.mmd),
            "kernel": self.kernel,
            "kernel_parameters": self.kernel_parameters,
            "reference_count": int(self.reference_count),
            "live_count": int(self.live_count),
            "bandwidth": float(self.bandwidth),
            "bandwidth_source": self.bandwidth_source,
            "p_value": None if self.p_value is None else float(self.p_value),
            "permutation_count": int(self.permutation_count),
            "seed": self.seed,
            "null_distribution": self.null_distribution,
        }


def _validate_inputs(ref: np.ndarray, live: np.ndarray, minimum_samples: int) -> None:
    if ref.ndim != 2 or live.ndim != 2:
        raise MMDValidationError(
            f"Embeddings must be 2-D arrays (got ref {ref.shape}, live {live.shape})."
        )
    if ref.shape[1] != live.shape[1]:
        raise MMDValidationError(
            f"Dimension mismatch: reference dim {ref.shape[1]} != live dim {live.shape[1]}."
        )
    if ref.shape[0] < 2:
        raise MMDValidationError("Need at least 2 reference embeddings.")
    if live.shape[0] < max(2, minimum_samples):
        raise MMDValidationError(
            f"Insufficient live samples: got {live.shape[0]}, need >= {max(2, minimum_samples)}."
        )
    for name, arr in (("reference", ref), ("live", live)):
        if arr.size and (not np.all(np.isfinite(arr))):
            raise MMDValidationError(
                f"{name} embeddings contain NaN/Inf values; refusing to score."
            )


def _pairwise_sq_dists(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Squared Euclidean distances, vectorized, numerically safe."""
    a_sq = np.sum(a * a, axis=1, keepdims=True)
    b_sq = np.sum(b * b, axis=1).reshape(1, -1)
    d2 = a_sq + b_sq - 2.0 * (a @ b.T)
    # Clip tiny negatives from float cancellation; MMD is non-negative.
    return np.maximum(d2, 0.0)


def _rbf_gram(d2: np.ndarray, bandwidth: float) -> np.ndarray:
    """exp(-||x-y||^2 / (2 * bandwidth^2)) computed stably from squared dists."""
    denom = 2.0 * float(bandwidth) ** 2
    if not np.isfinite(denom) or denom <= 0.0:
        raise MMDValidationError(f"Invalid kernel bandwidth: {bandwidth}")
    z = d2 / denom
    # exp(-z), capped to avoid redundant underflow computation on huge z.
    return np.exp(-np.minimum(z, 700.0))


def select_bandwidth(
    ref: np.ndarray, live: Optional[np.ndarray], mode: str, explicit: Optional[float] = None
) -> Any:
    """Deterministic bandwidth selection (median heuristic).

    Returns (sigma, provenance_string) where sigma is the RBF kernel
    bandwidth in exp(-||x-y||^2 / (2 * sigma^2)).

    'auto'          -> sigma = sqrt(median pairwise squared distance) over the
                       pooled reference+live sample (documented, deterministic
                       heuristic; capped to a 512-point subsample with a fixed
                       seed for reproducibility).
    'reference_median' -> same, computed on the reference alone.
    'explicit'      -> numeric config value used verbatim.
    """
    if mode not in ("auto", "reference_median", "explicit"):
        raise MMDValidationError(f"Unknown bandwidth mode: {mode}")
    if mode == "explicit":
        if explicit is None or not np.isfinite(float(explicit)) or float(explicit) <= 0:
            raise MMDValidationError(
                f"mmd.bandwidth must be a positive number when mode is 'explicit' (got {explicit})."
            )
        return float(explicit), "config:explicit"
    if mode == "reference_median":
        pooled = ref
        provenance = "heuristic:reference_median"
    else:
        pooled = np.vstack([ref, live]) if live is not None else ref
        provenance = "heuristic:pooled_median"
    if pooled.shape[0] > 512:  # cap the pairwise computation deterministically
        rng = np.random.default_rng(0)
        idx = rng.choice(pooled.shape[0], size=512, replace=False)
        pooled = pooled[idx]
    d2 = _pairwise_sq_dists(pooled, pooled)
    iu = np.triu_indices(d2.shape[0], k=1)
    med = float(np.median(d2[iu]))
    if not np.isfinite(med) or med <= 0.0:
        # Degenerate pooled sample (e.g. identical points): fall back to 1.0
        # and record it, rather than emitting a zero bandwidth.
        return 1.0, provenance + ":degenerate_fallback"
    # Median heuristic: sigma = sqrt(median squared distance).
    return float(np.sqrt(med)), provenance


def mmd_from_d2(d2_rr: np.ndarray, d2_ll: np.ndarray, d2_rl: np.ndarray, bandwidth: float) -> float:
    """Empirical MMD^2 (V-statistic) from precomputed squared distances.

    Uses the biased (V-statistic) estimator: mean k(x,x') + mean k(y,y')
    - 2 mean k(x,y) including diagonal terms. It is non-negative by
    construction, which matters operationally: an unbiased estimator can go
    negative for small live windows vs a large reference and read as "more
    identical than identical". The bias is a smooth function of sample size
    and cancels in threshold comparisons because calibration uses subsets of
    the same sizes.
    """
    k_rr = _rbf_gram(d2_rr, bandwidth)
    k_ll = _rbf_gram(d2_ll, bandwidth)
    k_rl = _rbf_gram(d2_rl, bandwidth)
    term_rr = float(k_rr.mean())
    term_ll = float(k_ll.mean())
    term_rl = float(k_rl.mean())
    val = term_rr + term_ll - 2.0 * term_rl
    return float(max(val, 0.0))


def mmd(
    reference_embeddings: np.ndarray,
    live_embeddings: np.ndarray,
    config: Optional[Dict[str, Any]] = None,
) -> MMDResult:
    """Compute MMD between reference and live embeddings.

    config keys: kernel ('rbf'), bandwidth ('auto' | 'reference_median' |
    number), permutations (int), seed (int), minimum_live_samples (int).
    """
    config = dict(config or {})
    kernel = config.get("kernel", "rbf")
    if kernel != "rbf":
        raise MMDValidationError(f"Unsupported kernel: {kernel} (only 'rbf' is implemented).")

    ref = np.asarray(reference_embeddings, dtype=np.float64)
    live = np.asarray(live_embeddings, dtype=np.float64)
    minimum_live = int(config.get("minimum_live_samples", 2))
    _validate_inputs(ref, live, minimum_live)

    bw_cfg = config.get("bandwidth", "auto")
    if isinstance(bw_cfg, (int, float)) and not isinstance(bw_cfg, bool):
        # A numeric config bandwidth is an explicit, documented choice.
        bw_val, bw_source = select_bandwidth(ref, live, "explicit", float(bw_cfg))
    else:
        bw_val, bw_source = select_bandwidth(ref, live, bw_cfg, config.get("bandwidth_value"))

    d2_rr = _pairwise_sq_dists(ref, ref)
    d2_ll = _pairwise_sq_dists(live, live)
    d2_rl = _pairwise_sq_dists(ref, live)

    value = mmd_from_d2(d2_rr, d2_ll, d2_rl, bw_val)

    result = MMDResult(
        mmd=value,
        kernel=kernel,
        kernel_parameters={"bandwidth": float(bw_val), "bandwidth_source": bw_source},
        reference_count=int(ref.shape[0]),
        live_count=int(live.shape[0]),
        bandwidth=float(bw_val),
        bandwidth_source=bw_source,
    )

    permutations = int(config.get("permutations", 0) or 0)
    if permutations > 0:
        if "seed" not in config:
            raise MMDValidationError(
                "mmd.permutations > 0 requires an explicit mmd.seed for reproducibility."
            )
        run_permutation_test(ref, live, result, permutations, int(config["seed"]),
                             bandwidth_mode=str(bw_cfg), bandwidth_value=config.get("bandwidth_value"))
    return result


def _permuted_mmd(
    pooled: np.ndarray, n: int, m: int, bandwidth: float, rng: np.random.Generator
) -> float:
    idx = rng.permutation(pooled.shape[0])
    a = pooled[idx[:n]]
    b = pooled[idx[n:n + m]]
    d2_aa = _pairwise_sq_dists(a, a)
    d2_bb = _pairwise_sq_dists(b, b)
    d2_ab = _pairwise_sq_dists(a, b)
    return mmd_from_d2(d2_aa, d2_bb, d2_ab, bandwidth)


def run_permutation_test(
    ref: np.ndarray,
    live: np.ndarray,
    result: MMDResult,
    permutations: int,
    seed: int,
    bandwidth_mode: str = "auto",
    bandwidth_value: Optional[float] = None,
) -> MMDResult:
    """Reference-style null permutation test; fills p_value + null summary.

    The null hypothesis is 'live is drawn from the same distribution as the
    reference'. A LOW p-value means the observed MMD is unusual under that
    hypothesis. It is evidence of distribution shift, NEVER proof of malicious
    activity (task.md 8.5).
    """
    ref = np.asarray(ref, dtype=np.float64)
    live = np.asarray(live, dtype=np.float64)
    pooled = np.vstack([ref, live])
    n, m = ref.shape[0], live.shape[0]
    rng = np.random.default_rng(seed)
    null = np.zeros(permutations, dtype=np.float64)
    for i in range(permutations):
        null[i] = _permuted_mmd(pooled, n, m, result.bandwidth, rng)
    p = float(np.mean(null >= result.mmd))
    result.p_value = p
    result.permutation_count = int(permutations)
    result.seed = int(seed)
    result.null_distribution = {
        "mean": float(null.mean()),
        "std": float(null.std()),
        "p95": float(np.percentile(null, 95)),
        "p99": float(np.percentile(null, 99)),
        "max": float(null.max()),
    }
    result.kernel_parameters["null_distribution_summary"] = result.null_distribution
    return result
