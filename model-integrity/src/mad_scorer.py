#!/usr/bin/env python3
"""
SentinelVision - Stage 4 Step 3: Median Absolute Deviation (MAD) Statistical Layer
Formalized module for detecting backdoor triggers via one-sided mask anomaly analysis.
Following Section 10 file structure (model-integrity/src/mad_scorer.py).
"""

import os
import sys
import json
import argparse
from typing import List, Dict, Any, Tuple
from collections import defaultdict
import numpy as np

# Project configuration constants per Section 6 Steps 2 & 3
NORMAL_CONSISTENCY_CONSTANT = 1.4826  # Standard scale factor making MAD a consistent estimator of SD under normality
DEFAULT_ANOMALY_THRESHOLD = 2.0      # Operative threshold per Section 6 Step 3: anomaly_index > 2.0 flags suspicious class

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT_FILE = os.path.abspath(os.path.join(CURRENT_DIR, "..", "neural_cleanse_results.json"))
DEFAULT_OUTPUT_FILE = os.path.abspath(os.path.join(CURRENT_DIR, "..", "mad_results.json"))


def compute_one_sided_mad_anomaly_index(mask_norms: List[float]) -> Tuple[List[float], float, int]:
    """
    Computes the one-sided MAD anomaly index for a set of per-class mask L1 norms.

    Formula:
        anomaly_index(class_i) = max(0, median(mask_norms) - mask_norm(class_i)) / (MAD(mask_norms) * 1.4826)
        where MAD = median(|mask_norms - median(mask_norms)|)

    Design rationale per Section 6 Step 2:
        "Classes that require a much smaller mask than others are suspicious...
        a small, low-visibility trigger is a signature of an actual backdoor."
        Anomaly index MUST be strictly ONE-SIDED, not two-sided. Only classes whose
        mask is SMALLER than the group's typical size (below median) are suspicious.
        A class needing a LARGER mask than its peers is not a backdoor signal; it
        indicates the class is inherently harder to force via any trigger.
        The max(0, ...) clamp enforces this one-sidedness: classes with above-median
        masks receive anomaly_index = 0.0 rather than negative-turned-positive values.

    Edge case handling:
        If MAD == 0 (e.g. all classes have identical mask norms or no variance to measure
        against), division by zero is avoided and all classes receive anomaly_index = 0.0.
    """
    norms = np.asarray(mask_norms, dtype=np.float64)
    median_norm = float(np.median(norms))
    abs_deviations = np.abs(norms - median_norm)
    mad = float(np.median(abs_deviations))

    if mad == 0.0:
        # No variance across mask norms; cannot establish an outlier baseline
        anomaly_indices = [0.0] * len(norms)
        max_idx = 0.0
        flagged_class = 0
    else:
        scale = mad * NORMAL_CONSISTENCY_CONSTANT
        # One-sided clamping: only penalize masks smaller than median
        anomaly_indices = [
            float(max(0.0, median_norm - m) / scale)
            for m in norms
        ]
        max_idx = float(max(anomaly_indices))
        flagged_class = int(np.argmax(anomaly_indices))

    return anomaly_indices, max_idx, flagged_class


def score_models_from_neural_cleanse(
    input_path: str = DEFAULT_INPUT_FILE,
    threshold: float = DEFAULT_ANOMALY_THRESHOLD
) -> List[Dict[str, Any]]:
    """
    Loads Neural Cleanse baseline results (300-step), groups by model_id,
    and computes the MAD anomaly indices for each class.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Neural Cleanse baseline results file not found: {input_path}")

    with open(input_path, "r") as f:
        nc_records = json.load(f)

    # Group records by model_id
    models_dict = defaultdict(list)
    for record in nc_records:
        models_dict[record["model_id"]].append(record)

    scored_results = []

    for model_id, records in models_dict.items():
        # Ensure classes are ordered strictly ascending [0, 1, 2, ...]
        records.sort(key=lambda r: r["class"])
        mask_norms = [r["mask_l1_norm"] for r in records]

        anom_indices, max_anom, flagged_class = compute_one_sided_mad_anomaly_index(mask_norms)

        rounded_indices = [round(v, 4) for v in anom_indices]
        rounded_max_anom = round(max_anom, 4)
        is_flagged = bool(rounded_max_anom > threshold)

        scored_results.append({
            "model_id": model_id,
            "per_class_anomaly_index": rounded_indices,
            "max_anomaly_index": rounded_max_anom,
            "flagged_class": flagged_class,
            "flagged": is_flagged
        })

    # Sort descending by max_anomaly_index
    scored_results.sort(key=lambda r: r["max_anomaly_index"], reverse=True)

    return scored_results


def save_mad_results(results: List[Dict[str, Any]], output_path: str = DEFAULT_OUTPUT_FILE) -> None:
    """
    Saves the scored results to disk as formatted JSON.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="SentinelVision Stage 4 Step 3: MAD Statistical Layer")
    parser.add_argument("--input", default=DEFAULT_INPUT_FILE, help="Path to neural_cleanse_results.json")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="Path to output mad_results.json")
    parser.add_argument("--threshold", type=float, default=DEFAULT_ANOMALY_THRESHOLD, help="Anomaly index threshold (default: 2.0)")

    args = parser.parse_args()

    results = score_models_from_neural_cleanse(input_path=args.input, threshold=args.threshold)
    save_mad_results(results, output_path=args.output)

    # Print the full contents of mad_results.json, sorted by max_anomaly_index descending
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
