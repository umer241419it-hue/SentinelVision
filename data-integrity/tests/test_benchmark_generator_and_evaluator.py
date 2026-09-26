"""
Unit tests for Benchmark Generator, Attack Manifest, and Evaluator.
"""

import json
import os
import tempfile
import pytest

from src.benchmark_evaluator import BenchmarkEvaluator


def test_evaluator_metrics_calculation():
    # Synthetic attack manifest with 5 attacks: 3 label flips, 2 duplicates
    manifest_data = {
        "benchmark_version": "1.0.0",
        "master_seed": 42,
        "total_attacks": 5,
        "attacks": [
            {
                "attack_id": "atk_01",
                "scenario": "label_flip",
                "sample_id": "voc2012_001",
                "original_state": {},
                "modified_state": {},
                "contributor_id": "contributor_01",
                "source_id": "src_01",
                "batch_id": "batch_01",
                "collection_id": "coll_A",
                "attack_parameters": {},
                "random_seed": 42,
            },
            {
                "attack_id": "atk_02",
                "scenario": "label_flip",
                "sample_id": "voc2012_002",
                "original_state": {},
                "modified_state": {},
                "contributor_id": "contributor_01",
                "source_id": "src_01",
                "batch_id": "batch_01",
                "collection_id": "coll_A",
                "attack_parameters": {},
                "random_seed": 42,
            },
            {
                "attack_id": "atk_03",
                "scenario": "label_flip",
                "sample_id": "voc2012_003",
                "original_state": {},
                "modified_state": {},
                "contributor_id": "contributor_02",
                "source_id": "src_02",
                "batch_id": "batch_02",
                "collection_id": "coll_A",
                "attack_parameters": {},
                "random_seed": 42,
            },
            {
                "attack_id": "atk_04",
                "scenario": "duplicate_flooding",
                "sample_id": "voc2012_dup_01",
                "original_state": {},
                "modified_state": {},
                "contributor_id": "contributor_03",
                "source_id": "src_03",
                "batch_id": "batch_03",
                "collection_id": "coll_A",
                "attack_parameters": {},
                "random_seed": 42,
            },
            {
                "attack_id": "atk_05",
                "scenario": "duplicate_flooding",
                "sample_id": "voc2012_dup_02",
                "original_state": {},
                "modified_state": {},
                "contributor_id": "contributor_03",
                "source_id": "src_03",
                "batch_id": "batch_03",
                "collection_id": "coll_A",
                "attack_parameters": {},
                "random_seed": 42,
            },
        ],
    }

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(manifest_data, f)
        manifest_path = f.name

    try:
        evaluator = BenchmarkEvaluator(manifest_path)
        all_ids = ["voc2012_001", "voc2012_002", "voc2012_003", "voc2012_dup_01", "voc2012_dup_02", "voc2012_clean_01", "voc2012_clean_02"]

        # Detector caught voc2012_001, voc2012_002, voc2012_dup_01, but also falsely flagged voc2012_clean_01
        # Missed: voc2012_003, voc2012_dup_02
        # TP = 3, FP = 1, FN = 2, TN = 1
        detected = [
            {"sample_id": "voc2012_001"},
            {"sample_id": "voc2012_002"},
            {"sample_id": "voc2012_dup_01"},
            {"sample_id": "voc2012_clean_01"},
        ]

        metrics = evaluator.evaluate_detections(detected, all_ids)
        assert metrics["tp"] == 3
        assert metrics["fp"] == 1
        assert metrics["fn"] == 2
        assert metrics["tn"] == 1
        assert metrics["precision"] == 0.75  # 3 / 4
        assert metrics["recall"] == 0.60  # 3 / 5
        assert pytest.approx(metrics["f1"], 1e-3) == (2 * 0.75 * 0.60) / (0.75 + 0.60)

        # Evaluate group attribution
        group_findings = [
            {"group_type": "contributor", "group_id": "contributor_01", "severity": "HIGH"},
            {"group_type": "contributor", "group_id": "contributor_innocent", "severity": "HIGH"},
        ]
        attr = evaluator.evaluate_group_attribution(group_findings)
        assert attr["contributor"]["tp"] == 1
        assert attr["contributor"]["fp"] == 1
        assert attr["contributor"]["precision"] == 0.50

        # Evaluate clean control
        clean_only = [
            {"sample_id": "clean_01", "reason": "label_flip"},
        ]
        clean_eval = evaluator.evaluate_clean_control(clean_only, ["clean_01", "clean_02", "clean_03", "clean_04", "clean_05"])
        assert clean_eval["clean_sample_count"] == 5
        assert clean_eval["false_positive_count"] == 1
        assert clean_eval["false_positive_rate"] == 0.20
    finally:
        os.remove(manifest_path)
