#!/usr/bin/env python3
"""
SentinelVision - Stage 4 Step 6: Confidence / Severity / Disposition Scoring
Formalized module mapping MAD's verdict (corroborated by STRIP) to finding fields.
Following Section 10 file structure (model-integrity/src/scoring.py).

Protocol Constraints:
- Zero ground truth data leakage: never open ground_truth.csv or METADATA.csv.
- Never describe a model's status with more certainty than this pipeline's own output supports.
- Pure statistical combination rule:
  * MAD unflagged -> ACCEPT (LOW severity, confidence <= 0.5)
  * MAD flagged + STRIP agrees -> QUARANTINE (CRITICAL severity, confidence >= 0.85)
  * MAD flagged + STRIP disagrees -> REVIEW (MEDIUM severity, confidence discounted by 0.6)
"""

import os
import sys
import json
from typing import List, Dict, Any, Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))


def score_model(mad_entry: Dict[str, Any], strip_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes confidence, severity, disposition, and reason for a single model
    based on MAD anomaly index and STRIP entropy-suppression corroboration.
    """
    model_id = mad_entry["model_id"]
    max_anomaly_index = mad_entry["max_anomaly_index"]
    flagged = mad_entry["flagged"]
    mad_flagged_class = mad_entry.get("flagged_class")

    # Find STRIP's top class for this model (highest entropy_deficit)
    top_strip_entry = max(strip_entries, key=lambda x: x["entropy_deficit"])
    strip_top_class = top_strip_entry["class"]

    if not flagged:
        # Rule 1: MAD unflagged
        confidence = round(min(0.5, max_anomaly_index / 2.0), 2)
        severity = "LOW"
        disposition = "ACCEPT"
        reason = (
            f"No anomalous class detected by Neural Cleanse + MAD (max anomaly index "
            f"{max_anomaly_index:.2f}, below threshold)."
        )
        return {
            "model_id": model_id,
            "confidence": confidence,
            "severity": severity,
            "disposition": disposition,
            "reason": reason,
            "mad_flagged_class": None,
            "strip_top_class": strip_top_class,
            "strip_agrees": None,
        }

    # Rule 2: MAD flagged
    if strip_top_class == mad_flagged_class:
        # Rule 2a: MAD and STRIP agree
        base_confidence = min(1.0, max_anomaly_index / 5.0)
        confidence = round(max(base_confidence, 0.85), 2)
        severity = "CRITICAL"
        disposition = "QUARANTINE"
        reason = (
            f"Class {mad_flagged_class} flagged by Neural Cleanse + MAD (anomaly index "
            f"{max_anomaly_index:.2f}) and independently corroborated by STRIP's "
            f"entropy-suppression signal on the same class \u2014 QUARANTINE recommended "
            f"pending human review."
        )
        strip_agrees = True
    else:
        # Rule 2b: MAD and STRIP disagree
        base_confidence = min(1.0, max_anomaly_index / 5.0)
        confidence = round(base_confidence * 0.6, 2)
        severity = "MEDIUM"
        disposition = "REVIEW"
        reason = (
            f"Class {mad_flagged_class} flagged by Neural Cleanse + MAD (anomaly index "
            f"{max_anomaly_index:.2f}), but STRIP's independent signal points to a "
            f"different class (class {strip_top_class}) \u2014 flagged for human review "
            f"rather than automatic quarantine given the conflicting signals."
        )
        strip_agrees = False

    return {
        "model_id": model_id,
        "confidence": confidence,
        "severity": severity,
        "disposition": disposition,
        "reason": reason,
        "mad_flagged_class": mad_flagged_class,
        "strip_top_class": strip_top_class,
        "strip_agrees": strip_agrees,
    }


def main():
    manifest_path = os.path.join(BASE_DIR, "calibration_manifest.json")
    mad_path = os.path.join(BASE_DIR, "mad_results.json")
    strip_path = os.path.join(BASE_DIR, "strip_results.json")
    output_path = os.path.join(BASE_DIR, "scoring_results.json")

    with open(manifest_path, "r") as f:
        manifest = json.load(f)
    with open(mad_path, "r") as f:
        mad_data = json.load(f)
    with open(strip_path, "r") as f:
        strip_data = json.load(f)

    mad_by_model = {m["model_id"]: m for m in mad_data}
    strip_by_model: Dict[str, List[Dict[str, Any]]] = {}
    for s in strip_data:
        strip_by_model.setdefault(s["model_id"], []).append(s)

    results = []
    for entry in manifest:
        mid = entry["model_id"]
        mad_entry = mad_by_model[mid]
        strip_entries = strip_by_model[mid]
        score_entry = score_model(mad_entry, strip_entries)
        results.append(score_entry)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Scoring complete for {len(results)} models. Saved to {output_path}.\n")
    print(json.dumps(results, indent=2))

    # Disposition summary
    accept_count = sum(1 for r in results if r["disposition"] == "ACCEPT")
    review_count = sum(1 for r in results if r["disposition"] == "REVIEW")
    quarantine_count = sum(1 for r in results if r["disposition"] == "QUARANTINE")
    print(f"\nDisposition Summary: {accept_count} ACCEPT, {review_count} REVIEW, {quarantine_count} QUARANTINE")


if __name__ == "__main__":
    main()
