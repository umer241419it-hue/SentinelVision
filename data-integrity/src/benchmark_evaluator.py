"""
SentinelVision - Quantitative Benchmark Evaluator.

Evaluates data-integrity detector performance against the authoritative
attack_manifest.json ground truth.

Computes mathematically sound, non-fabricated metrics:
- Sample-level: Precision, Recall, F1, TP, FP, FN, TN, FPR, FNR
- Scenario-level breakdown: Label flipping, Near-duplicate flooding,
  OOD insertion, Trigger injection, Systematic mislabelling
- Group-level attribution evaluation: Contributor, Source, and Batch identification accuracy
- Clean control false-positive evaluation on clean baseline
"""

import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple


class BenchmarkEvaluator:
    """
    Compares detector outputs against attack_manifest.json ground truth.
    """

    def __init__(self, attack_manifest_path: str):
        self.attack_manifest_path = os.path.abspath(attack_manifest_path)
        with open(self.attack_manifest_path, "r", encoding="utf-8") as f:
            self.manifest_data = json.load(f)

        self.attacks = self.manifest_data.get("attacks", [])
        # Map scenario -> set of attack sample_ids
        self.ground_truth_by_scenario: Dict[str, Set[str]] = {}
        # Map sample_id -> AttackRecord dict
        self.ground_truth_samples: Dict[str, Dict[str, Any]] = {}

        for atk in self.attacks:
            sid = atk["sample_id"]
            scen = atk["scenario"]
            if scen not in self.ground_truth_by_scenario:
                self.ground_truth_by_scenario[scen] = set()
            self.ground_truth_by_scenario[scen].add(sid)
            self.ground_truth_samples[sid] = atk

        self.all_attack_samples = set(self.ground_truth_samples.keys())

    @staticmethod
    def _compute_rates(tp: int, fp: int, fn: int, tn: int) -> Dict[str, float]:
        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        fpr = (fp / (fp + tn)) if (fp + tn) > 0 else 0.0
        fnr = (fn / (fn + tp)) if (fn + tp) > 0 else 0.0
        accuracy = ((tp + tn) / (tp + tn + fp + fn)) if (tp + tn + fp + fn) > 0 else 0.0

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "accuracy": round(accuracy, 4),
            "fpr": round(fpr, 4),
            "fnr": round(fnr, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
        }

    def evaluate_detections(
        self,
        detected_samples: List[Dict[str, Any]],
        all_dataset_sample_ids: List[str],
        scenario_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate overall sample-level detection against ground truth.

        Args:
            detected_samples: List of finding records from detectors or fusion engine.
            all_dataset_sample_ids: Complete set of sample IDs in the evaluated dataset.
            scenario_filter: Optional scenario to evaluate in isolation.
        """
        all_samples_set = set(all_dataset_sample_ids)

        # Extract detected sample IDs (normalize prefix if necessary)
        flagged_sids: Set[str] = set()
        for d in detected_samples:
            sid = d.get("sample_id") or d.get("assetID", "").replace("image-", "")
            if not sid.startswith("voc2012_") and f"voc2012_{sid}" in all_samples_set:
                sid = f"voc2012_{sid}"
            flagged_sids.add(sid)

        target_attacks: Set[str]
        if scenario_filter:
            target_attacks = self.ground_truth_by_scenario.get(scenario_filter, set())
        else:
            target_attacks = self.all_attack_samples

        tp_set = flagged_sids.intersection(target_attacks)
        fp_set = flagged_sids.difference(self.all_attack_samples)
        fn_set = target_attacks.difference(flagged_sids)
        tn_set = all_samples_set.difference(self.all_attack_samples).difference(flagged_sids)

        tp = len(tp_set)
        fp = len(fp_set)
        fn = len(fn_set)
        tn = len(tn_set)

        metrics = self._compute_rates(tp, fp, fn, tn)
        metrics["target_injected"] = len(target_attacks)
        metrics["total_detected"] = len(flagged_sids)

        return metrics

    def evaluate_per_scenario(
        self,
        detected_samples: List[Dict[str, Any]],
        all_dataset_sample_ids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Evaluate performance broken down by attack scenario.
        """
        scenarios = list(self.ground_truth_by_scenario.keys())
        results = {}
        for scen in scenarios:
            results[scen] = self.evaluate_detections(
                detected_samples=detected_samples,
                all_dataset_sample_ids=all_dataset_sample_ids,
                scenario_filter=scen,
            )
        return results

    def evaluate_group_attribution(
        self,
        group_findings: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Evaluate whether the group aggregator correctly identified compromised
        contributors, sources, and batches based on attack ground truth.
        """
        # Determine truly compromised groups from attack manifest
        compromised_groups: Dict[str, Set[str]] = {
            "contributor": set(),
            "source": set(),
            "batch": set(),
            "collection": set(),
        }

        for atk in self.attacks:
            if atk.get("contributor_id"):
                compromised_groups["contributor"].add(atk["contributor_id"])
            if atk.get("source_id"):
                compromised_groups["source"].add(atk["source_id"])
            if atk.get("batch_id"):
                compromised_groups["batch"].add(atk["batch_id"])
            if atk.get("collection_id"):
                compromised_groups["collection"].add(atk["collection_id"])

        # Compare against flagged group findings
        attribution_results: Dict[str, Any] = {}

        for gt in ("contributor", "source", "batch"):
            flagged_gids = set(
                gf["group_id"]
                for gf in group_findings
                if gf.get("group_type") == gt and gf.get("severity") in ("MEDIUM", "HIGH", "CRITICAL")
            )
            true_gids = compromised_groups.get(gt, set())

            tp = len(flagged_gids.intersection(true_gids))
            fp = len(flagged_gids.difference(true_gids))
            fn = len(true_gids.difference(flagged_gids))

            precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
            recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

            attribution_results[gt] = {
                "ground_truth_compromised": sorted(list(true_gids)),
                "detected_compromised": sorted(list(flagged_gids)),
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "tp": tp,
                "fp": fp,
                "fn": fn,
            }

        return attribution_results

    def evaluate_clean_control(
        self,
        clean_detected_samples: List[Dict[str, Any]],
        clean_dataset_sample_ids: List[str],
    ) -> Dict[str, Any]:
        """
        Evaluate false positives when running detectors against clean baseline VOC2012.
        """
        n_clean = len(clean_dataset_sample_ids)
        fp_count = len(clean_detected_samples)
        fpr = (fp_count / n_clean) if n_clean > 0 else 0.0

        # Break down false positives by detector flag
        det_fp_counts: Dict[str, int] = {}
        for d in clean_detected_samples:
            flags = d.get("flags") or [d.get("reason", "unknown")]
            if isinstance(flags, str):
                flags = [flags]
            for f in flags:
                det_fp_counts[f] = det_fp_counts.get(f, 0) + 1

        return {
            "clean_sample_count": n_clean,
            "false_positive_count": fp_count,
            "false_positive_rate": round(fpr, 4),
            "false_positives_by_detector": det_fp_counts,
            "assessment": "ACCEPTABLE" if fpr < 0.05 else "REQUIRES_THRESHOLD_TUNING",
        }
