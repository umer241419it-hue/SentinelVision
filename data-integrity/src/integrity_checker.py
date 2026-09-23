"""
SentinelVision - Data Integrity check orchestrator.

Runs the three Data Integrity checks on one labeled dataset and merges the
per-check flags into ONE combined record per flagged image, because the
ledger receives one finding per flagged asset - not one per check type
(Stage 6 Step 5: "If an image is flagged by more than one check, combine the
reasons into one finding rather than submitting duplicates").

Pipeline: shared frozen embeddings -> per-dimension STANDARDIZATION (mu, sd
computed once over the dataset) -> duplicate (standardized cosine) / OOD
(min class-conditional Mahalanobis) / label-flip (cleanlab confident learning
on out-of-sample k-NN probabilities) checks -> merged verdicts.

Combined record policy (deterministic, documented, unit-tested):
- flags     = which checks flagged the image
- confidence = 0.60 + 0.15 per additional independent flag, capped 0.95
- severity  = worst severity among policy[<check>] entries; escalated to
              policy.multiple_checks.severity when >= 2 checks agree
- disposition = REVIEW whenever anything is flagged (human-in-the-loop;
              no automatic quarantine - Stage 6 Constraint 5)
- reason    = one human-readable clause per flag, joined
"""

from typing import Any, Dict, List, Optional

import numpy as np

from . import ensure_shared_importable  # noqa: F401  (path bootstrap)

from .dataset import ImageDataset
from .duplicate_detector import (
    DuplicateDetectionError,
    find_duplicates,
    standardization_stats,
)
from .label_flip_detector import (
    CleanlabUnavailableError,
    LabelFlipError,
    find_label_flips,
)
from .ood_detector import (
    OODDetectionError,
    calibrate_threshold,
    fit_reference,
    score_embeddings,
)

MODULE_NAME = "DataIntegrity"
MODULE_VERSION = "1.1.0"

SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
SEVERITIES = ("LOW", "MEDIUM", "HIGH")
DISPOSITIONS = ("ACCEPT", "REVIEW")

COVERAGE_STATEMENT = (
    "Data Integrity Coverage: the implemented checks operate on frozen "
    "shared embeddings (standardized per dimension) and (1) flag "
    "near-duplicate images by pairwise cosine similarity, (2) flag "
    "statistically out-of-distribution images by class-conditional trimmed "
    "Mahalanobis distance with held-out robust calibration, and (3) flag "
    "likely mislabeled samples by cleanlab confident learning on "
    "out-of-sample predicted probabilities. On the self-poisoned validation "
    "set (100 clean + 10 label flips + 10 byte-identical duplicates + 10 OOD "
    "noise images) the module catches the great majority of planted "
    "corruptions with a low false-positive rate - see "
    "data-integrity/results/validation_report.json for the measured rates. "
    "It does NOT detect subtle semantic near-duplicates below the similarity "
    "threshold, small-magnitude OOD samples below the calibrated threshold, "
    "or label errors indistinguishable from clean data in embedding space; "
    "confident learning accuracy depends on the auxiliary classifier, which "
    "was not extensively tuned. One finding per flagged asset is produced "
    "for human review; no automatic quarantine is performed."
)

KNOWN_LIMITATIONS = [
    "Cosine duplicate detection catches embedding-level near-duplicates only; "
    "two visually different photographs of the same scene will not be flagged.",
    "The Mahalanobis reference is fit on the provided dataset with trimming; "
    "if the dataset itself is heavily poisoned, sensitivity degrades.",
    "Label-flip detection depends on the auxiliary classifier quality; classes "
    "with very few samples produce weak out-of-sample estimates.",
    "No check establishes intent or identifies an attacker; findings are "
    "evidence for human review only.",
]


def _worst(severities: List[str]) -> str:
    return max(severities, key=lambda s: SEVERITY_RANK.get(s, -1)) if severities else "LOW"


def check_dataset(
    dataset: ImageDataset,
    config: Dict[str, Any],
    checks_to_run: Optional[List[str]] = None,
    ood_reference: Optional[Dict[str, Any]] = None,
    ood_threshold_info: Optional[Dict[str, Any]] = None,
    answer_key: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the selected checks and merge into per-image combined records.

    ood_reference/ood_threshold_info may be supplied pre-fit by the caller
    (e.g. fit on a trusted clean subset); otherwise both are derived from
    this dataset's own embeddings (per-class trimmed fits + held-out
    calibration).
    """
    checks = list(checks_to_run or ["duplicate", "ood", "label_flip"])
    policy = config.get("policy", {})

    emb_raw = dataset.embeddings()
    n = emb_raw.shape[0]

    # One standardization for all checks (recorded for reproducibility).
    mu, sd = standardization_stats(emb_raw)
    emb = (emb_raw - mu) / sd

    dup_res = ood_res = flip_res = None
    errors: Dict[str, str] = {}

    # -- check 2a: duplicates (standardized cosine) ---------------------------
    if "duplicate" in checks:
        try:
            dup_res = find_duplicates(
                emb,
                dataset.image_ids,
                threshold=float(config.get("duplicate", {}).get("similarity_threshold", 0.99)),
            )
        except DuplicateDetectionError as exc:
            errors["duplicate"] = str(exc)

    # -- check 2b: OOD (class-conditional Mahalanobis) -------------------------
    if "ood" in checks:
        try:
            ood_cfg = config.get("ood", {})
            labels = [dataset.labels[i] for i in dataset.image_ids]
            ref = ood_reference or fit_reference(
                emb, labels, trim_fraction=float(ood_cfg.get("trim_fraction", 0.10))
            )
            thr = ood_threshold_info or calibrate_threshold(
                emb,
                labels,
                trim_fraction=float(ood_cfg.get("trim_fraction", 0.10)),
                n_splits=int(ood_cfg.get("calibration_splits", 5)),
                seed=int(ood_cfg.get("seed", 42)),
                mad_k=float(ood_cfg.get("mad_k", 5.0)),
            )
            ood_res = score_embeddings(emb, ref, thr)
        except OODDetectionError as exc:
            errors["ood"] = str(exc)

    # -- check 2c: label flips (cleanlab on standardized embeddings) -----------
    if "label_flip" in checks:
        try:
            flip_cfg = config.get("label_flip", {})
            flip_res = find_label_flips(
                emb,
                [dataset.labels[i] for i in dataset.image_ids],
                classifier=str(flip_cfg.get("classifier", "knn")),
                n_splits=int(flip_cfg.get("n_splits", 5)),
                seed=int(flip_cfg.get("seed", 42)),
                n_neighbors=int(flip_cfg.get("n_neighbors", 5)),
                image_ids=dataset.image_ids,
            )
        except (LabelFlipError, CleanlabUnavailableError) as exc:
            errors["label_flip"] = str(exc)

    # -- merge into combined per-image records ----------------------------------
    combined: Dict[str, Dict[str, Any]] = {}
    dup_pairs_by_image: Dict[str, List[Dict[str, Any]]] = {}
    if dup_res:
        for p in dup_res["pairs"]:
            dup_pairs_by_image.setdefault(p["image_a"], []).append(p)
            dup_pairs_by_image.setdefault(p["image_b"], []).append(p)
    ood_flagged = set(ood_res["flagged_indices"]) if ood_res else set()
    flip_rows = {r["image_id"]: r for r in flip_res["per_image"]} if flip_res else {}

    for idx, image_id in enumerate(dataset.image_ids):
        flags: List[str] = []
        reasons: List[str] = []
        severities: List[str] = []
        details: Dict[str, Any] = {}

        if dup_res and image_id in dup_pairs_by_image:
            my_pairs = dup_pairs_by_image[image_id]
            best = max(my_pairs, key=lambda p: p["similarity"])
            other = best["image_b"] if best["image_a"] == image_id else best["image_a"]
            flags.append("duplicate")
            severities.append(policy.get("duplicate", {}).get("severity", "MEDIUM"))
            reasons.append(
                f"near-duplicate of {other} (standardized cosine {best['similarity']:.3f} "
                f">= threshold {dup_res['threshold']:.2f})"
            )
            details["duplicate"] = {"pairs": my_pairs, "threshold": dup_res["threshold"]}

        if ood_res and idx in ood_flagged:
            d = ood_res["distances"][idx]
            flags.append("ood")
            severities.append(policy.get("ood", {}).get("severity", "HIGH"))
            reasons.append(
                f"statistical outlier (min class-conditional Mahalanobis distance "
                f"{d:.2f} > threshold {ood_res['threshold']:.2f})"
            )
            details["ood"] = {"distance": round(d, 6), "threshold": ood_res["threshold"]}

        if flip_res and image_id in flip_rows:
            row = flip_rows[image_id]
            flags.append("label_flip")
            severities.append(policy.get("label_flip", {}).get("severity", "MEDIUM"))
            reasons.append(
                f"likely mislabeled: given '{row['given_label']}', model predicts "
                f"'{row['predicted_label']}' (confidence {row['confidence_label_wrong']:.2f}, "
                f"out-of-sample)"
            )
            details["label_flip"] = row

        if not flags:
            continue

        if len(flags) >= 2:
            sev = _worst([policy.get("multiple_checks", {}).get("severity", "HIGH")] + severities)
        else:
            sev = _worst(severities)
        conf = round(min(0.95, 0.60 + 0.15 * (len(flags) - 1)), 2)

        rec: Dict[str, Any] = {
            "image_id": image_id,
            "flags": flags,
            "n_flags": len(flags),
            "reason": "; ".join(reasons),
            "confidence": conf,
            "severity": sev,
            "disposition": policy.get("multiple_checks", {}).get("disposition", "REVIEW"),
            "details": details,
        }
        if answer_key is not None:
            truth = answer_key.get(image_id)
            if truth is not None:
                rec["answer_key"] = {
                    "corruption": truth.get("corruption"),
                    "true_label": truth.get("true_label"),
                    "true_duplicate_of": truth.get("true_duplicate_of"),
                }
        combined[image_id] = rec

    standardization = {
        "method": "per_dimension_zscore",
        "computed_over": "checked_dataset",
        "mu": [float(v) for v in mu],
        "sd": [float(v) for v in sd],
    }

    return {
        "module": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "dataset": {
            "image_count": n,
            "image_ids": list(dataset.image_ids),
            "label_distribution": {
                str(v): sum(1 for x in dataset.labels.values() if x == v)
                for v in sorted(set(dataset.labels.values()))
            },
            "extractor": dataset.extractor_metadata,
        },
        "standardization": standardization,
        "checks_run": [c for c in ("duplicate", "ood", "label_flip") if c in checks],
        "check_results": {
            "duplicate": dup_res,
            "ood": ood_res,
            "label_flip": flip_res,
        },
        "check_errors": errors,
        "flagged": combined,
        "n_flagged": len(combined),
        "coverage_statement": COVERAGE_STATEMENT,
        "known_limitations": list(KNOWN_LIMITATIONS),
    }


def summarize(check_result: Dict[str, Any]) -> Dict[str, Any]:
    """Compact run summary for the results file and logs."""
    flagged = check_result.get("flagged", {})
    by_flag = {
        c: sum(1 for r in flagged.values() if c in r["flags"])
        for c in ("duplicate", "ood", "label_flip")
    }
    return {
        "module": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "checks_run": check_result.get("checks_run", []),
        "check_errors": check_result.get("check_errors", {}),
        "images_checked": check_result.get("dataset", {}).get("image_count"),
        "images_flagged": check_result.get("n_flagged"),
        "flagged_by_check": by_flag,
        "severity_distribution": {
            s: sum(1 for r in flagged.values() if r["severity"] == s) for s in SEVERITIES
        },
    }
