#!/usr/bin/env python3
"""
SentinelVision - Phase 7: Drift Detector
========================================

Orchestrates one window check end-to-end:

    reference embeddings + live window embeddings
        -> MMD (with optional permutation test)
        -> calibrated threshold comparison
        -> operational diagnostics
        -> conservative assessment
        -> deterministic confidence / severity / disposition policy

Key rule (task.md 9.4): a high drift score means "the live distribution is
different from the reference distribution". It must NOT automatically become
"an attacker caused this". Nothing here emits attack attribution; unexplained
shifts go to REVIEW.
"""

import os
from typing import Any, Dict, List, Optional

import numpy as np

from . import ensure_shared_importable  # noqa: F401  (path bootstrap)

from .diagnostics import (
    ASSESSMENT_INSUFFICIENT,
    ASSESSMENT_NO_SHIFT,
    LEVEL_NA,
    build_assessment,
    compute_image_stats,
    compare_image_stats,
    compare_metadata,
)
from .mmd import MMDValidationError, mmd
from .rolling_window import RollingWindow
from .threshold_calibrator import CalibrationUnavailableError, load_calibration

MODULE_NAME = "DistributionShift"
MODULE_VERSION = "1.0.0"

SEVERITY_LOW = "LOW"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_HIGH = "HIGH"
DISPOSITION_ACCEPT = "ACCEPT"
DISPOSITION_REVIEW = "REVIEW"


def map_to_finding_policy(
    assessment: str,
    mmd_value: float,
    threshold: float,
    p_value: Optional[float],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Deterministic drift -> (confidence, severity, disposition) mapping.

    Policy (task.md 11), documented and unit-tested:
      NO_SIGNIFICANT_SHIFT   -> LOW    / ACCEPT / confidence grows with margin
      OPERATIONAL_SHIFT_LIKELY -> MEDIUM / REVIEW / 0.75 base
      UNEXPLAINED_SHIFT      -> HIGH   / REVIEW / 0.80 base
      INSUFFICIENT_EVIDENCE  -> LOW (configurable) / REVIEW / capped 0.20

    A permutation p-value < 0.05 corroborates significance (+0.10 confidence,
    capped at 0.95); a missing p-value discounts OPERATIONAL/UNEXPLAINED
    confidence by 0.10 because the shift was never significance-tested.
    Confidence never exceeds 0.95: drift statistics cannot be certain.
    """
    config = config or {}
    insufficient_severity = config.get("policy", {}).get("insufficient_severity", SEVERITY_LOW)

    def clamp(x: float) -> float:
        return round(max(0.0, min(0.95, float(x))), 2)

    if assessment == ASSESSMENT_NO_SHIFT:
        if threshold > 0:
            margin = max(0.0, min(1.0, (threshold - mmd_value) / threshold))
        else:
            margin = 0.0
        confidence = clamp(0.60 + 0.30 * margin)
        if p_value is not None and p_value < 0.05:
            # MMD below threshold but permutation test flags it: stay ACCEPT
            # (threshold governs the verdict) but lower the confidence.
            confidence = clamp(min(confidence, 0.55))
        return {
            "confidence": confidence,
            "severity": SEVERITY_LOW,
            "disposition": DISPOSITION_ACCEPT,
            "reason": (
                f"MMD {mmd_value:.6f} is within the calibrated reference-null "
                f"threshold {threshold:.6f}; no significant distribution shift."
            ),
        }

    if assessment == "OPERATIONAL_SHIFT_LIKELY":
        confidence = 0.75 if p_value is not None else 0.65
        if p_value is not None and p_value < 0.05:
            confidence += 0.10
        return {
            "confidence": clamp(confidence),
            "severity": SEVERITY_MEDIUM,
            "disposition": DISPOSITION_REVIEW,
            "reason": (
                f"MMD {mmd_value:.6f} exceeds the calibrated threshold "
                f"{threshold:.6f}, and measurable operational diagnostics "
                "(brightness/color/contrast/source) changed with it; "
                "operational or environmental shift is plausible. REVIEW."
            ),
        }

    if assessment == "UNEXPLAINED_SHIFT":
        confidence = 0.80 if p_value is not None else 0.70
        if p_value is not None and p_value < 0.05:
            confidence += 0.10
        return {
            "confidence": clamp(confidence),
            "severity": SEVERITY_HIGH,
            "disposition": DISPOSITION_REVIEW,
            "reason": (
                f"MMD {mmd_value:.6f} exceeds the calibrated threshold "
                f"{threshold:.6f} and no measured operational diagnostic "
                "explains the change; unexplained distribution shift - surface "
                "for human review. Drift evidence alone does not establish "
                "cause or intent."
            ),
        }

    # INSUFFICIENT_EVIDENCE (and any unknown assessment) fails closed.
    return {
        "confidence": 0.20,
        "severity": insufficient_severity,
        "disposition": DISPOSITION_REVIEW,
        "reason": (
            "Insufficient evidence for a drift verdict (missing calibration, "
            "incompatible inputs or no measurable data); confidence is "
            "explicitly limited and the window is surfaced for REVIEW."
        ),
    }


def _reference_image_paths(reference: Dict[str, Any], base_dir: str) -> List[str]:
    manifest = reference.get("manifest", {})
    source = manifest.get("source")
    paths = manifest.get("image_paths") or []
    if not source or not paths:
        return []
    src_dir = os.path.join(base_dir, source)
    return [os.path.join(src_dir, p) for p in paths]


def check_window(
    reference: Dict[str, Any],
    window: RollingWindow,
    sequence_index: int,
    config: Dict[str, Any],
    base_dir: str,
    calibration: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the full drift check for one completed live window.

    Never raises for 'operational' reasons: any failure mode (missing
    calibration, dimension mismatch, insufficient samples) is converted into
    an INSUFFICIENT_EVIDENCE result so downstream consumers get a consistent
    schema. Only genuine programming errors propagate.
    """
    ref_manifest = reference.get("manifest", {})
    ref_emb = np.asarray(reference.get("embeddings"), dtype=np.float64)
    win_desc = window.describe(sequence_index, ref_manifest.get("reference_id", "unknown"))
    win_emb = window.embeddings()

    base: Dict[str, Any] = {
        "module": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "reference": {
            "reference_id": ref_manifest.get("reference_id"),
            "source_digest": ref_manifest.get("source_digest"),
            "embedding_digest": ref_manifest.get("embedding_digest"),
            "manifest_digest": ref_manifest.get("manifest_digest"),
            "backbone": ref_manifest.get("backbone"),
            "embedding_dim": ref_manifest.get("embedding_dim"),
            "preprocessing": ref_manifest.get("preprocessing", {}),
        },
        "live_window": win_desc,
    }

    def insufficient(reason: str) -> Dict[str, Any]:
        policy = map_to_finding_policy(ASSESSMENT_INSUFFICIENT, 0.0, 0.0, None, config)
        return {
            **base,
            "mmd": None,
            "threshold": None,
            "diagnostics": {"levels": {}, "details": {}, "note": reason},
            "assessment": ASSESSMENT_INSUFFICIENT,
            "policy": policy,
        }

    # Calibration must exist and match this exact reference (fail closed).
    try:
        cal = calibration or load_calibration(base_dir, ref_manifest.get("manifest_digest"))
    except CalibrationUnavailableError as exc:
        return insufficient(str(exc))

    mmd_cfg = dict(config.get("mmd", {}))
    mmd_cfg["minimum_live_samples"] = window.minimum_samples

    try:
        result = mmd(ref_emb, win_emb, mmd_cfg)
    except MMDValidationError as exc:
        return insufficient(f"MMD validation failed: {exc}")

    significant = bool(result.mmd > float(cal["threshold"]))

    # Operational diagnostics run only when images are available; otherwise
    # every diagnostic is NOT_AVAILABLE and never crashes the detector.
    image_diag: Dict[str, Any] = {"levels": {}, "details": {}}
    meta_diag: Dict[str, Any] = {}
    if config.get("diagnostics", {}).get("enabled", True):
        ref_paths = _reference_image_paths(reference, base_dir)
        live_paths = [m.get("image_path") for m in window._metadata if m.get("image_path")]
        if ref_paths and live_paths:
            ref_stats = compute_image_stats(ref_paths)
            live_stats = compute_image_stats(live_paths)
            image_diag = compare_image_stats(ref_stats, live_stats)
            ref_meta = ref_manifest.get("metadata", {})
            meta_diag = compare_metadata(ref_meta, window._metadata)
        else:
            image_diag = {
                "levels": {},
                "details": {},
                "note": "images not available for this window; diagnostics skipped",
            }

    assessment_obj = build_assessment(significant, image_diag, meta_diag or None)
    assessment = assessment_obj["assessment"]

    policy = map_to_finding_policy(
        assessment, result.mmd, float(cal["threshold"]), result.p_value, config
    )

    return {
        **base,
        "mmd": result.to_dict(),
        "threshold": {
            "calibration_id": cal.get("calibration_id"),
            "value": float(cal["threshold"]),
            "method": cal.get("method"),
            "quantile": cal.get("quantile"),
            "reference_manifest_digest": cal.get("reference_manifest_digest"),
        },
        "diagnostics": {
            "image_diagnostics": image_diag,
            "metadata_diagnostics": meta_diag or None,
            "assessment_explanation": assessment_obj["explanation"],
        },
        "assessment": assessment,
        "policy": policy,
    }
