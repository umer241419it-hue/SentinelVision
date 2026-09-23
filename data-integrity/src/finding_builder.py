"""
SentinelVision - Data Integrity finding builder.

Produces the existing SentinelVision 8-field finding schema (Stage 6 Step 5):
assetID form "image-<unique-id>" (guide example), sanitized to a
ledger-key-safe, deterministic string. assetID is the Fabric ledger key, so
it must uniquely identify the flagged image. One finding per flagged asset,
combining every check that flagged it.
"""

import re
from typing import Any, Dict

from .integrity_checker import MODULE_NAME

FINDING_MODULE_NAME = "DataIntegrity"

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")
SEVERITIES = {"LOW", "MEDIUM", "HIGH"}
DISPOSITIONS = {"ACCEPT", "REVIEW", "QUARANTINE"}


def sanitize_component(value: str, max_len: int = 120) -> str:
    """Ledger-key-safe component: [A-Za-z0-9._-] only, length-capped."""
    cleaned = _SANITIZE_RE.sub("-", str(value)).strip("-.")
    return cleaned[:max_len] if cleaned else "unknown"


def build_asset_id(image_id: str) -> str:
    return sanitize_component(f"image-{image_id}")


def build_finding(
    combined_record: Dict[str, Any],
    evidence_hash: str,
    timestamp: str,
) -> Dict[str, Any]:
    """Build the 8-field finding for one flagged image."""
    finding = {
        "assetID": build_asset_id(combined_record["image_id"]),
        "moduleName": FINDING_MODULE_NAME,
        "reason": combined_record["reason"],
        "evidenceHash": evidence_hash,
        "confidence": f"{float(combined_record['confidence']):.2f}",
        "severity": combined_record["severity"],
        "disposition": combined_record["disposition"],
        "timestamp": timestamp,
    }
    validate_finding(finding)
    return finding


def validate_finding(finding: Dict[str, Any]) -> None:
    """Raise ValueError if the finding violates the 8-field schema rules.
    Mirrors the bridge's server-side validation so tests catch schema drift
    before the network does."""
    required = [
        "assetID", "moduleName", "reason", "evidenceHash",
        "confidence", "severity", "disposition", "timestamp",
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
        raise ValueError(
            f"Finding disposition '{finding['disposition']}' not in {sorted(DISPOSITIONS)}"
        )
    h = finding["evidenceHash"]
    if len(h) != 64 or any(ch not in "0123456789abcdef" for ch in h):
        raise ValueError("Finding evidenceHash must be 64 lowercase hex characters")


def validate_evidence_hash_binding(finding: Dict[str, Any], evidence_store_dir: str) -> str:
    """Verify the evidence file <hash>.json exists and re-hashing its bytes
    reproduces the finding's hash (tamper check used by the CLI/tests)."""
    import hashlib
    import os

    evidence_hash = finding["evidenceHash"]
    path = os.path.join(evidence_store_dir, f"{evidence_hash}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Evidence file not found for hash {evidence_hash}")
    with open(path, "rb") as f:
        data = f.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != evidence_hash:
        raise ValueError(
            f"Evidence file '{path}' hash mismatch: {actual} != {evidence_hash}"
        )
    return path
