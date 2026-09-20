#!/usr/bin/env python3
"""
SentinelVision - Stage 4 Step 7: Finding Schema + Evidence Store
Constructs full evidence JSON, computes cryptographic SHA-256 evidenceHash,
persists evidence to evidence_store/<evidenceHash>.json, and builds the
canonical 8-field finding JSON matching Stage 2 chaincode schema.

Following Section 10 file structure: model-integrity/src/finding_builder.py
"""

import os
import sys
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Any

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

COVERAGE_STATEMENT = (
    "Detection path: white-box (Neural Cleanse + MAD), corroborated by STRIP "
    "(mask-preserving overlay variant) when MAD flags a class. KNOWN LIMITATION: "
    "if Neural Cleanse + MAD fails to flag a genuinely poisoned model at all "
    "(a validated false-negative case exists in this pipeline's testing), STRIP "
    "corroboration does not independently catch it — STRIP only corroborates "
    "classes MAD has already flagged, it does not run as an independent whole-model "
    "detector. This pipeline has NOT been validated against BackdoorBench or "
    "non-patch-style triggers (blended, WaNet-style) — detection is currently "
    "validated only against patch-style (BadNets/StaticTarget-style) backdoors."
)


def load_json(filepath: str) -> Any:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def build_evidence(
    model_id: str,
    calibration_entry: Dict[str, Any],
    mad_entry: Dict[str, Any],
    strip_entries: List[Dict[str, Any]],
    scoring_entry: Dict[str, Any],
) -> Dict[str, Any]:
    calibration = {
        "tier": calibration_entry["calibration_tier"],
        "chosen_channel_order": calibration_entry["chosen_channel_order"],
        "calibration_accuracy": calibration_entry["calibration_accuracy"],
        "access_path": calibration_entry["access_path"],
    }

    neural_cleanse_mad = {
        "per_class_anomaly_index": mad_entry["per_class_anomaly_index"],
        "max_anomaly_index": mad_entry["max_anomaly_index"],
        "flagged": mad_entry["flagged"],
        "flagged_class": mad_entry.get("flagged_class"),
    }

    sorted_strip = sorted(strip_entries, key=lambda x: x["class"])
    per_class_entropy_deficit = [entry["entropy_deficit"] for entry in sorted_strip]
    top_strip_entry = max(sorted_strip, key=lambda x: x["entropy_deficit"])
    top_class = top_strip_entry["class"]

    strip = {
        "per_class_entropy_deficit": per_class_entropy_deficit,
        "top_class": top_class,
    }

    evidence = {
        "model_id": model_id,
        "calibration": calibration,
        "neural_cleanse_mad": neural_cleanse_mad,
        "strip": strip,
        "strip_agreement": scoring_entry.get("strip_agrees"),
        "coverage_statement": COVERAGE_STATEMENT,
    }
    return evidence


def build_finding(
    model_id: str,
    scoring_entry: Dict[str, Any],
    evidence_hash: str,
    timestamp: str,
) -> Dict[str, Any]:
    confidence_val = scoring_entry["confidence"]
    confidence_str = f"{confidence_val:.2f}" if isinstance(confidence_val, (int, float)) else str(confidence_val)

    finding = {
        "assetID": f"model-{model_id}",
        "moduleName": "ModelIntegrity-NeuralCleanse-MAD-STRIP",
        "reason": scoring_entry["reason"],
        "evidenceHash": evidence_hash,
        "confidence": confidence_str,
        "severity": scoring_entry["severity"],
        "disposition": scoring_entry["disposition"],
        "timestamp": timestamp,
    }
    return finding


def main():
    calibration_path = os.path.join(BASE_DIR, "calibration_manifest.json")
    mad_path = os.path.join(BASE_DIR, "mad_results.json")
    strip_path = os.path.join(BASE_DIR, "strip_results.json")
    scoring_path = os.path.join(BASE_DIR, "scoring_results.json")
    evidence_store_dir = os.path.join(BASE_DIR, "evidence_store")
    findings_path = os.path.join(BASE_DIR, "findings.json")

    os.makedirs(evidence_store_dir, exist_ok=True)

    calibration_manifest = load_json(calibration_path)
    mad_results = load_json(mad_path)
    strip_results = load_json(strip_path)
    scoring_results = load_json(scoring_path)

    cal_by_model = {item["model_id"]: item for item in calibration_manifest}
    mad_by_model = {item["model_id"]: item for item in mad_results}
    scoring_by_model = {item["model_id"]: item for item in scoring_results}

    strip_by_model = {}
    for item in strip_results:
        strip_by_model.setdefault(item["model_id"], []).append(item)

    model_ids = [item["model_id"] for item in calibration_manifest]
    current_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_findings = []
    written_evidence_files = []

    for model_id in model_ids:
        evidence = build_evidence(
            model_id=model_id,
            calibration_entry=cal_by_model[model_id],
            mad_entry=mad_by_model[model_id],
            strip_entries=strip_by_model[model_id],
            scoring_entry=scoring_by_model[model_id],
        )

        canonical_bytes = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
        evidence_hash = hashlib.sha256(canonical_bytes).hexdigest()

        evidence_file_path = os.path.join(evidence_store_dir, f"{evidence_hash}.json")
        with open(evidence_file_path, "wb") as f:
            f.write(canonical_bytes)
        written_evidence_files.append(evidence_file_path)

        finding = build_finding(
            model_id=model_id,
            scoring_entry=scoring_by_model[model_id],
            evidence_hash=evidence_hash,
            timestamp=current_timestamp,
        )
        all_findings.append(finding)

    with open(findings_path, "w", encoding="utf-8") as f:
        json.dump(all_findings, f, indent=2)

    print(f"Successfully processed {len(model_ids)} models.")
    print(f"Evidence files written: {len(written_evidence_files)} to {evidence_store_dir}")
    print(f"Findings written: {findings_path}")


if __name__ == "__main__":
    main()
