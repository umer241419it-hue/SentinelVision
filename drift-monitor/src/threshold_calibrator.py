#!/usr/bin/env python3
"""
SentinelVision - Phase 5: Threshold Calibration (reference-vs-reference null)
=============================================================================

No arbitrary magic numbers: the operational drift threshold is derived from
the reference battery itself.

Procedure (task.md 9.1):
    Reference battery
      |- random subset A
      |- random subset B  (disjoint)
           -> MMD(A, B)
    repeat `sample_count` times with a fixed seed
           -> null distribution of MMD under "both groups are normal"
    threshold = quantile(null distribution, quantile)

The result is persisted as a versioned calibration manifest keyed to the
exact reference identity (reference manifest digest). A drift run against a
different reference must refuse to use it (fail closed -> INSUFFICIENT_EVIDENCE
rather than a guessed verdict).

The calibration ID is deterministic: it is derived from a SHA-256 of the
calibration inputs (reference manifest digest + parameters), so re-running
with the same inputs reproduces the same identity, and changing the reference
data changes the identity.

Usage:
    python -m src.threshold_calibrator --config config.json
"""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np

from . import ensure_shared_importable  # noqa: F401  (path bootstrap)

from .mmd import MMDValidationError, mmd
from .reference_builder import BASE_DIR, load_reference


class CalibrationUnavailableError(RuntimeError):
    """Raised when no valid calibration exists for the current reference."""


def _calibration_identity(inputs: Dict[str, Any]) -> str:
    payload = json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "threshold-" + hashlib.sha256(payload).hexdigest()[:12]


def calibrate(
    reference: Dict[str, Any],
    config: Dict[str, Any],
    base_dir: str = BASE_DIR,
    write_manifest: bool = True,
) -> Dict[str, Any]:
    """Run reference-vs-reference null calibration; return the manifest dict."""
    cal_cfg = config.get("calibration", {})
    mmd_cfg = dict(config.get("mmd", {}))
    mmd_cfg["permutations"] = 0  # calibration uses raw MMD only; fast + deterministic

    manifest = reference["manifest"]
    emb = np.asarray(reference["embeddings"], dtype=np.float64)

    seed = int(cal_cfg.get("seed", 42))
    sample_count = int(cal_cfg.get("sample_count", 200))
    quantile = float(cal_cfg.get("quantile", 0.99))
    ref_count = emb.shape[0]
    split_size = int(cal_cfg.get("split_size", 0)) or min(60, max(2, ref_count // 2))
    if split_size * 2 > ref_count:
        raise MMDValidationError(
            f"calibration.split_size {split_size} is too large for a reference battery "
            f"of {ref_count} images (needs two disjoint subsets)."
        )
    if sample_count < 1:
        raise MMDValidationError("calibration.sample_count must be >= 1.")
    if not (0.0 < quantile < 1.0):
        raise MMDValidationError("calibration.quantile must be in (0, 1).")

    rng = np.random.default_rng(seed)
    null_values = np.zeros(sample_count, dtype=np.float64)
    for i in range(sample_count):
        perm = rng.permutation(ref_count)
        a = emb[perm[:split_size]]
        b = emb[perm[split_size:2 * split_size]]
        result = mmd(a, b, mmd_cfg)
        null_values[i] = result.mmd

    threshold = float(np.quantile(null_values, quantile))
    inputs = {
        "reference_manifest_digest": manifest["manifest_digest"],
        "method": "reference_null",
        "quantile": quantile,
        "seed": seed,
        "sample_count": sample_count,
        "split_size": split_size,
        "bandwidth": mmd_cfg.get("bandwidth", "auto"),
        "kernel": mmd_cfg.get("kernel", "rbf"),
    }
    calibration_manifest = {
        "calibration_id": _calibration_identity(inputs),
        "method": "reference_null",
        "reference_id": manifest["reference_id"],
        "reference_manifest_digest": manifest["manifest_digest"],
        "backbone": manifest["backbone"],
        "embedding_dim": manifest["embedding_dim"],
        "threshold": threshold,
        "quantile": quantile,
        "seed": seed,
        "sample_count": sample_count,
        "split_size": split_size,
        "bandwidth": inputs["bandwidth"],
        "kernel": inputs["kernel"],
        "null_summary": {
            "mean": float(null_values.mean()),
            "std": float(null_values.std()),
            "min": float(null_values.min()),
            "p95": float(np.percentile(null_values, 95)),
            "p99": float(np.percentile(null_values, 99)),
            "max": float(null_values.max()),
        },
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": (
            "Threshold = quantile of MMD values observed between two disjoint "
            "random subsets of the reference battery itself. It captures normal "
            "reference variation; it is not a universal constant."
        ),
    }

    if write_manifest:
        cal_dir = os.path.join(base_dir, "calibration")
        os.makedirs(cal_dir, exist_ok=True)
        path = os.path.join(cal_dir, "threshold_manifest.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(calibration_manifest, f, indent=2)
        print(
            f"[OK] calibration written: {path} "
            f"(id={calibration_manifest['calibration_id']}, threshold={threshold:.6f})"
        )
    return calibration_manifest


def load_calibration(
    base_dir: str = BASE_DIR,
    reference_manifest_digest: Optional[str] = None,
) -> Dict[str, Any]:
    """Load calibration/threshold_manifest.json, validating it matches the
    reference in use. Raises CalibrationUnavailableError (fail closed) when
    missing or mismatched."""
    path = os.path.join(base_dir, "calibration", "threshold_manifest.json")
    if not os.path.isfile(path):
        raise CalibrationUnavailableError(
            "No threshold calibration found. Run: python -m src.threshold_calibrator --config config.json"
        )
    with open(path, "r", encoding="utf-8") as f:
        cal = json.load(f)
    if reference_manifest_digest and cal.get("reference_manifest_digest") != reference_manifest_digest:
        raise CalibrationUnavailableError(
            "Existing calibration was generated for a different reference battery "
            f"(manifest digest mismatch: calibration={cal.get('reference_manifest_digest')}, "
            f"current={reference_manifest_digest}). Re-run the calibrator against the "
            "current reference; refusing to reuse an incompatible threshold."
        )
    for field in ("calibration_id", "threshold", "method"):
        if field not in cal:
            raise CalibrationUnavailableError(f"Calibration manifest missing field '{field}'.")
    return cal


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate drift threshold from reference null")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    args = parser.parse_args()

    config_path = os.path.abspath(args.config)
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    base = os.path.dirname(config_path)
    reference = load_reference(base)
    calibrate(reference, config, base_dir=base)


if __name__ == "__main__":
    main()
