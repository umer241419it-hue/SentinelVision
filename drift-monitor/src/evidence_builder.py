#!/usr/bin/env python3
"""
SentinelVision - Phase 8: Drift Evidence Builder
================================================

Builds the structured drift evidence object, canonicalizes it with the exact
Model Integrity pattern (sorted keys + compact separators, UTF-8), computes
SHA-256, and stores the canonical bytes as
    <drift-monitor>/evidence_store/<evidenceHash>.json

The evidence is self-describing: it records the reference identity, the live
window identity, the MMD computation (kernel, bandwidth, p-value, seed), the
threshold calibration identity, diagnostics, the conservative assessment, the
coverage statement and known limitations. Anyone holding the evidence file
can reproduce/interpret the finding without re-running the pipeline.
"""

import hashlib
import json
import os
from typing import Any, Dict, Optional

from .drift_detector import MODULE_NAME, MODULE_VERSION

COVERAGE_STATEMENT = (
    "Distribution-Shift Monitor Coverage: the implemented detector compares "
    "reference-battery and live-window image embeddings using MMD and "
    "calibrated reference-derived thresholds. It can identify statistically "
    "significant changes in the observed image distribution and report "
    "measurable operational factors that may explain the change. A "
    "distribution shift alone does not prove malicious manipulation or "
    "identify an attacker. Results with unexplained shift are therefore "
    "surfaced for human review rather than automatically treated as "
    "confirmed attacks. Performance and thresholds are valid only for the "
    "declared reference battery, embedding configuration, window "
    "configuration, and tested operating conditions."
)

KNOWN_LIMITATIONS = [
    "Distribution shift does not by itself establish malicious manipulation.",
    "MMD is computed on frozen embeddings; it measures representation-level "
    "distribution change, not semantic content change.",
    "The calibrated threshold is valid only for the reference battery and "
    "embedding configuration recorded in this evidence; changing either "
    "invalidates it.",
    "Operational diagnostics are simple aggregate image statistics plus "
    "declared metadata; they can be coincident with an adversarial shift and "
    "their agreement with MMD is evidence for review prioritization, not "
    "proof of an operational cause.",
    "Insufficient live samples produce INSUFFICIENT_EVIDENCE, not a verdict.",
]


def canonical_json_bytes(evidence: Dict[str, Any]) -> bytes:
    """Exactly the Model Integrity canonicalization."""
    return json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")


def hash_evidence(evidence: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(evidence)).hexdigest()


def build_evidence(run_result: Dict[str, Any], run_id: Optional[str] = None) -> Dict[str, Any]:
    """Assemble the evidence dict from one drift_detector.check_window result."""
    policy = run_result.get("policy", {})
    diagnostics = run_result.get("diagnostics", {})
    mmd_block = run_result.get("mmd") or {}
    threshold = run_result.get("threshold") or {}

    evidence: Dict[str, Any] = {
        "module": run_result.get("module", MODULE_NAME),
        "module_version": run_result.get("module_version", MODULE_VERSION),
        "schema": "sentinelvision.drift-evidence/v1",
        "reference": run_result.get("reference", {}),
        "live_window": run_result.get("live_window", {}),
        "mmd": {
            "value": mmd_block.get("mmd"),
            "kernel": mmd_block.get("kernel"),
            "kernel_parameters": mmd_block.get("kernel_parameters", {}),
            "p_value": mmd_block.get("p_value"),
            "permutation_count": mmd_block.get("permutation_count", 0),
            "seed": mmd_block.get("seed"),
            "reference_count": mmd_block.get("reference_count"),
            "live_count": mmd_block.get("live_count"),
        },
        "threshold": {
            "calibration_id": threshold.get("calibration_id"),
            "value": threshold.get("value"),
            "method": threshold.get("method"),
            "quantile": threshold.get("quantile"),
            "estimator": threshold.get("estimator"),
            "sigma": threshold.get("sigma"),
            "n": threshold.get("n"),
            "m": threshold.get("m"),
            "null_summary": threshold.get("null_summary"),
        },
        "diagnostics": {
            "image_diagnostics": diagnostics.get("image_diagnostics", {}),
            "metadata_diagnostics": diagnostics.get("metadata_diagnostics"),
            "assessment_explanation": diagnostics.get("assessment_explanation", {}),
        },
        "assessment": run_result.get("assessment"),
        "finding_fields": {
            "confidence": policy.get("confidence"),
            "severity": policy.get("severity"),
            "disposition": policy.get("disposition"),
            "reason": policy.get("reason"),
        },
        "limitations": list(KNOWN_LIMITATIONS),
        "coverage_statement": COVERAGE_STATEMENT,
    }
    if run_id:
        evidence.setdefault("run", {})["run_id"] = run_id
    return evidence


def build_and_store_evidence(
    run_result: Dict[str, Any],
    evidence_store_dir: str,
    timestamp: str,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build evidence, inject the run timestamp and run_id, hash, persist, and return
    {'evidence', 'evidence_hash', 'evidence_path'}.

    The timestamp and run_id ARE included in hash identity (like Model Integrity, which
    hashes the evidence it stores). The run_drift_monitor CLI supports
    --timestamp-fixed and --run-id for byte-identical reproducibility runs.
    """
    evidence = build_evidence(run_result, run_id=run_id)
    run_dict: Dict[str, Any] = {
        "timestamp": timestamp,
        "mode": "offline",
    }
    if run_id:
        run_dict["run_id"] = run_id
    evidence["run"] = run_dict

    canonical = canonical_json_bytes(evidence)
    evidence_hash = hashlib.sha256(canonical).hexdigest()
    os.makedirs(evidence_store_dir, exist_ok=True)
    path = os.path.join(evidence_store_dir, f"{evidence_hash}.json")
    with open(path, "wb") as f:
        f.write(canonical)
    return {"evidence": evidence, "evidence_hash": evidence_hash, "evidence_path": path}
