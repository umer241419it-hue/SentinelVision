"""
SentinelVision - Data Integrity evidence builder.

Same evidence pattern as every other SentinelVision module (Stage 6 Step 5):
full per-check evidence -> canonical JSON (sorted keys, compact separators)
-> SHA-256 -> evidence_store/<hash>.json ; the hash goes in the finding.

One evidence document per flagged image, containing exactly what that image
was flagged for, the dataset/embedding identity, and the module's coverage
statement + limitations. Canonicalization is byte-identical to the Model
Integrity / Drift Monitor pattern.
"""

import hashlib
import json
import os
from typing import Any, Dict

from .integrity_checker import KNOWN_LIMITATIONS, COVERAGE_STATEMENT, MODULE_NAME, MODULE_VERSION


def canonical_json_bytes(evidence: Dict[str, Any]) -> bytes:
    """Exactly the Model Integrity canonicalization."""
    return json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")


def hash_evidence(evidence: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(evidence)).hexdigest()


def build_evidence(
    combined_record: Dict[str, Any],
    dataset_meta: Dict[str, Any],
    check_results: Dict[str, Any],
    timestamp: str,
) -> Dict[str, Any]:
    """Assemble one flagged image's evidence document."""
    evidence: Dict[str, Any] = {
        "module": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "schema": "sentinelvision.data-integrity-evidence/v1",
        "asset": {
            "image_id": combined_record["image_id"],
            "flags": combined_record["flags"],
            "n_flags": combined_record["n_flags"],
        },
        "details": combined_record.get("details", {}),
        "finding_fields": {
            "confidence": combined_record["confidence"],
            "severity": combined_record["severity"],
            "disposition": combined_record["disposition"],
            "reason": combined_record["reason"],
        },
        "dataset": {
            "image_count": dataset_meta.get("image_count"),
            "label_distribution": dataset_meta.get("label_distribution", {}),
            "extractor": dataset_meta.get("extractor", {}),
        },
        "check_context": _check_context(check_results, combined_record["image_id"]),
        "assessment": "FLAGGED_FOR_REVIEW",
        "limitations": list(KNOWN_LIMITATIONS),
        "coverage_statement": COVERAGE_STATEMENT,
        "run": {"timestamp": timestamp, "mode": "offline"},
    }
    return evidence


def _check_context(check_results: Dict[str, Any], image_id: str) -> Dict[str, Any]:
    """Minimal reproduction context: thresholds/params the checks used."""
    dup = check_results.get("duplicate") or {}
    ood = check_results.get("ood") or {}
    flip = check_results.get("label_flip") or {}
    return {
        "duplicate": {
            "threshold": dup.get("threshold"),
            "n_pairs_total": dup.get("n_pairs"),
        },
        "ood": {
            "threshold": ood.get("threshold"),
            "held_out_summary": (ood.get("held_out_summary") if "held_out_summary" in ood else None),
        },
        "label_flip": {
            "classifier": flip.get("classifier"),
            "n_splits": flip.get("n_splits"),
            "method": flip.get("method"),
        },
    }


def build_and_store_evidence(
    combined_record: Dict[str, Any],
    dataset_meta: Dict[str, Any],
    check_results: Dict[str, Any],
    evidence_store_dir: str,
    timestamp: str,
) -> Dict[str, Any]:
    """Build, hash, and persist one evidence file; return hash + path."""
    evidence = build_evidence(combined_record, dataset_meta, check_results, timestamp)
    canonical = canonical_json_bytes(evidence)
    evidence_hash = hashlib.sha256(canonical).hexdigest()
    os.makedirs(evidence_store_dir, exist_ok=True)
    path = os.path.join(evidence_store_dir, f"{evidence_hash}.json")
    with open(path, "wb") as f:
        f.write(canonical)
    return {"evidence": evidence, "evidence_hash": evidence_hash, "evidence_path": path}
