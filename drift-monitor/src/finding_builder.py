#!/usr/bin/env python3
"""
SentinelVision - Phase 9: Drift Finding Builder
===============================================

Produces the SentinelVision 9-field signed finding schema consumed by the
Node bridge (POST /findings) and the Fabric finding contract. Drift does not
invent a second reporting format; it reuses the ledger schema.

assetID form: "drift-<run_id>-<reference_id>-<window_id>" (or "drift-<reference_id>-<window_id>"
if run_id is None), sanitized to a ledger-key-safe, deterministic string. assetID is the Fabric
ledger key, so it must uniquely identify the reference + live window run.

The 8 original fields are signed using Ed25519 with the 'DistributionShift' module key,
and the resulting 128-hex-character signature is attached as the 9th field.
"""

import os
import re
import sys
from typing import Any, Dict, Optional

# Ensure crypto-utils is in sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CRYPTO_UTILS_DIR = os.path.join(WORKSPACE_ROOT, "crypto-utils")
if CRYPTO_UTILS_DIR not in sys.path:
    sys.path.insert(0, CRYPTO_UTILS_DIR)

from sign import sign_fields
from verify import verify_fields

from .drift_detector import MODULE_NAME

FINDING_MODULE_NAME = "DistributionShift-MMD"
SIGNER_MODULE_NAME = "DistributionShift"

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")
SEVERITIES = {"LOW", "MEDIUM", "HIGH"}
DISPOSITIONS = {"ACCEPT", "REVIEW"}


def sanitize_component(value: str, max_len: int = 64) -> str:
    """Ledger-key-safe component: [A-Za-z0-9._-] only, length-capped."""
    cleaned = _SANITIZE_RE.sub("-", str(value)).strip("-.")
    return cleaned[:max_len] if cleaned else "unknown"


def build_asset_id(reference_id: str, window_id: str, run_id: Optional[str] = None) -> str:
    if run_id:
        return sanitize_component(f"drift-{run_id}-{reference_id}-{window_id}", max_len=200)
    return sanitize_component(f"drift-{reference_id}-{window_id}", max_len=200)


def build_finding(
    run_result: Dict[str, Any],
    evidence_hash: str,
    timestamp: str,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the 9-field signed finding from a check_window result + evidence hash."""
    policy = run_result.get("policy", {})
    reference = run_result.get("reference", {})
    window = run_result.get("live_window", {})

    confidence = policy.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        confidence_str = f"{float(confidence):.2f}"
    else:
        confidence_str = str(confidence)

    severity = policy.get("severity")
    disposition = policy.get("disposition")

    finding = {
        "assetID": build_asset_id(
            reference.get("reference_id", "unknown"),
            window.get("window_id", "unknown"),
            run_id=run_id,
        ),
        "moduleName": FINDING_MODULE_NAME,
        "reason": policy.get("reason", ""),
        "evidenceHash": evidence_hash,
        "confidence": confidence_str,
        "severity": severity,
        "disposition": disposition,
        "timestamp": timestamp,
    }
    # Sign exactly the 8 original fields with module name 'DistributionShift'
    finding["signature"] = sign_fields(SIGNER_MODULE_NAME, finding)
    validate_finding(finding)
    return finding


def validate_finding(finding: Dict[str, Any]) -> None:
    """Raise ValueError if the finding violates the 9-field schema rules.
    Mirrors the bridge's server-side validation so tests catch schema drift
    before the network does."""
    required = [
        "assetID", "moduleName", "reason", "evidenceHash",
        "confidence", "severity", "disposition", "timestamp",
        "signature",
    ]
    for field in required:
        if finding.get(field) in (None, ""):
            raise ValueError(f"Finding missing or empty required field '{field}'")
    try:
        c = float(finding["confidence"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Finding confidence must be numeric") from exc
    if not (0.0 <= c <= 1.0):
        raise ValueError("Finding confidence must be within [0, 1]")
    if finding["severity"] not in SEVERITIES:
        raise ValueError(f"Finding severity '{finding['severity']}' not in {sorted(SEVERITIES)}")
    if finding["disposition"] not in DISPOSITIONS:
        raise ValueError(f"Finding disposition '{finding['disposition']}' not in {sorted(DISPOSITIONS)}")
    h = finding["evidenceHash"]
    if len(h) != 64 or any(ch not in "0123456789abcdef" for ch in h):
        raise ValueError("Finding evidenceHash must be 64 lowercase hex characters")
    sig = finding["signature"]
    if not isinstance(sig, str) or len(sig) != 128 or any(ch not in "0123456789abcdefABCDEF" for ch in sig):
        raise ValueError("Finding signature must be a 128-character hex string")


def validate_evidence_hash_binding(finding: Dict[str, Any], evidence_store_dir: str) -> str:
    """Verify the evidence file <hash>.json exists and re-hashing its bytes
    reproduces the hash in the finding (tamper check used by the CLI/tests)."""
    evidence_hash = finding["evidenceHash"]
    path = os.path.join(evidence_store_dir, f"{evidence_hash}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Evidence file not found for hash {evidence_hash}")
    import hashlib

    with open(path, "rb") as f:
        data = f.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != evidence_hash:
        raise ValueError(
            f"Evidence file '{path}' hash mismatch: file hash {actual} != finding hash {evidence_hash}"
        )
    return path
