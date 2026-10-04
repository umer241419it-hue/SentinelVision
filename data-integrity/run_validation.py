#!/usr/bin/env python3
"""
SentinelVision - Stage 6 validation runner (Data Integrity + Distribution-Shift).

Produces the raw, cross-checkable outputs the Stage 6 build order demands
(real numbers, not "it works"):

  1. Data Integrity:
     - per-image verdict table: image_id -> flagged/not -> which check(s)
       flagged it -> confidence -> ground truth from the answer key -> match?
     - detection rate / false-positive rate PER CHECK and overall
  2. Distribution-Shift dual-direction proof:
     - normal window  : raw MMD value + calibrated threshold -> must NOT alert
     - shifted window : raw MMD value + calibrated threshold -> MUST alert

Usage (from SentinelVision/):
    python data-integrity/run_validation.py \
        --integrity-dir data/integrity-test \
        --shifted-dir data/scenario2-lighting-shift

Scoring semantics (documented so a human can cross-check):
- an image whose corruption is X counts as a TRUE positive for check Y when
  Y flagged it and Y targets X (duplicate<->duplicate, ood<->ood,
  label_flip<->label_flip);
- the INSERTED duplicate copy is the duplicate corruption; its source image
  is only "corrupt" as a member of the pair (source_of_duplicate is set in
  the answer key), so a source flagged for duplicate ALSO counts as a true
  catch of that duplicate event;
- anything else that is flagged counts as a false positive for the check
  that flagged it;
- corruption events (not images) define the detection-rate denominator:
  10 duplicate events, 10 ood images, 10 label flips in the default set.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_INTEGRITY_ROOT = HERE
PROJECT_ROOT = os.path.dirname(HERE)
for _p in (DATA_INTEGRITY_ROOT, PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CHECK_TARGETS = {"duplicate": "duplicate", "ood": "ood", "label_flip": "label_flip"}


def _log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Part 1 - Data Integrity scoring against the answer key
# ---------------------------------------------------------------------------
def _flag_is_justified(check: str, truth: Dict[str, Any]) -> bool:
    """True when `check` flagging this image corresponds to a real corruption.

    - duplicate: the image IS the inserted copy, or is the source of one
      (both members of the pair genuinely are duplicates).
    - ood / label_flip: the image carries that exact corruption.
    """
    corruption = truth.get("corruption")
    if check == "duplicate":
        return corruption == "duplicate" or bool(truth.get("source_of_duplicate"))
    return corruption == CHECK_TARGETS[check]


def score_integrity(check_result: Dict[str, Any], answer_key: Dict[str, Any]) -> Dict[str, Any]:
    # answer_key is the per-image records dict (accept the raw or wrapped form).
    labels = answer_key.get("labels", answer_key) if isinstance(answer_key, dict) else {}
    flagged: Dict[str, Dict[str, Any]] = check_result.get("flagged", {})

    rows: List[Dict[str, Any]] = []
    per_check = {c: {"tp": 0, "fp": 0} for c in CHECK_TARGETS}
    duplicate_events_caught = set()
    flip_events_caught = set()
    ood_events_caught = set()

    for image_id in sorted(labels.keys()):
        rec = flagged.get(image_id)
        truth = labels[image_id]
        corruption = truth.get("corruption")
        flags = list(rec["flags"]) if rec else []

        justified = []
        for check in CHECK_TARGETS:
            if check not in flags:
                continue
            if _flag_is_justified(check, truth):
                per_check[check]["tp"] += 1
                justified.append(check)
                if check == "duplicate":
                    duplicate_events_caught.add(
                        truth.get("true_duplicate_of") or truth.get("duplicate_of") or image_id
                    )
                elif check == "label_flip":
                    flip_events_caught.add(image_id)
                elif check == "ood":
                    ood_events_caught.add(image_id)
            else:
                per_check[check]["fp"] += 1

        corrupted_member = corruption in ("duplicate", "ood", "label_flip")
        is_duplicate_source = bool(truth.get("source_of_duplicate"))
        if justified:
            verdict = "TP"
        elif flags:
            verdict = "FP"
        elif corrupted_member or is_duplicate_source:
            # Only planted-corruption images count as missed; duplicate
            # sources are counted at the event level, not as image FNs.
            verdict = "FN" if corrupted_member else "clean"
        else:
            verdict = "clean"

        rows.append(
            {
                "image_id": image_id,
                "given_label": truth.get("given_label"),
                "true_label": truth.get("true_label"),
                "corruption": corruption,
                "flagged": bool(rec),
                "flags": flags,
                "confidence": rec["confidence"] if rec else None,
                "severity": rec["severity"] if rec else None,
                "correct_catch": verdict == "TP",
                "verdict": verdict,
            }
        )

    # Detection-rate denominators are corruption EVENTS:
    # 10 duplicate pairs + 10 ood images + 10 label flips in the default set.
    duplicate_events = {
        t.get("true_duplicate_of") or t.get("duplicate_of")
        for t in labels.values()
        if t.get("corruption") == "duplicate" and (t.get("true_duplicate_of") or t.get("duplicate_of"))
    }
    events = {
        "duplicate": duplicate_events,
        "ood": {img for img, t in labels.items() if t.get("corruption") == "ood"},
        "label_flip": {img for img, t in labels.items() if t.get("corruption") == "label_flip"},
    }
    caught_events = {
        "duplicate": duplicate_events_caught,
        "ood": ood_events_caught,
        "label_flip": flip_events_caught,
    }

    per_check_out: Dict[str, Any] = {}
    for check in CHECK_TARGETS:
        stats = per_check[check]
        n_events = len(events[check])
        caught = sum(1 for e in events[check] if e in caught_events[check])
        detection_rate = caught / n_events if n_events else None
        # FPR denominator: images that are NOT this corruption type and not
        # duplicate sources (for the duplicate check).
        n_not_target = sum(
            1
            for img, t in labels.items()
            if t.get("corruption") != CHECK_TARGETS[check]
            and not (check == "duplicate" and t.get("source_of_duplicate"))
        )
        fpr = stats["fp"] / n_not_target if n_not_target else None
        per_check_out[check] = {
            "detection_rate": round(detection_rate, 4) if detection_rate is not None else None,
            "false_positive_rate": round(fpr, 4) if fpr is not None else None,
            "events_caught": caught,
            "n_events": n_events,
            **stats,
        }

    corrupted_ids = {
        img for img, t in labels.items() if t.get("corruption") in ("duplicate", "ood", "label_flip")
    }
    untouched = [
        img
        for img, t in labels.items()
        if t.get("corruption") not in ("duplicate", "ood", "label_flip")
        and not t.get("source_of_duplicate")
    ]
    false_positive_images = sum(1 for r in rows if r["verdict"] == "FP")
    missed = [r["image_id"] for r in rows if r["verdict"] == "FN"]

    total_events = sum(len(v) for v in events.values())
    caught_total = sum(len(events[c] & caught_events[c]) for c in events)
    overall_detection = caught_total / total_events if total_events else None
    overall_fpr = false_positive_images / len(untouched) if untouched else None

    return {
        "table": rows,
        "per_check": per_check_out,
        "overall": {
            "detection_rate": round(overall_detection, 4) if overall_detection is not None else None,
            "false_positive_rate": round(overall_fpr, 4) if overall_fpr is not None else None,
            "events_caught": caught_total,
            "total_events": total_events,
            "false_positives": false_positive_images,
            "missed_corruptions": missed,
            "n_corrupted": len(corrupted_ids),
            "n_images": len(labels),
            "n_flagged": sum(1 for r in rows if r["flagged"]),
        },
    }


def print_integrity_table(scoring: Dict[str, Any]) -> None:
    _log("")
    _log("=== DATA INTEGRITY: per-image verdict table (cross-check me) ===")
    header = f"{'image_id':<28} {'corruption':<12} {'flagged':<8} {'flags':<30} {'conf':<6} {'verdict'}"
    _log(header)
    _log("-" * len(header))
    for r in scoring["table"]:
        conf = f"{r['confidence']:.2f}" if r["confidence"] is not None else "-"
        _log(
            f"{r['image_id']:<28} {str(r['corruption']):<12} "
            f"{('YES' if r['flagged'] else 'no'):<8} "
            f"{(','.join(r['flags']) or '-'):<30} "
            f"{conf:<6} {r['verdict']}"
        )
    _log("")
    _log("=== DATA INTEGRITY: per-check performance ===")
    for check, s in scoring["per_check"].items():
        _log(
            f"{check:<12} detection_rate={s['detection_rate']}  "
            f"false_positive_rate={s['false_positive_rate']}  "
            f"(tp={s['tp']} fp={s['fp']} caught={s['events_caught']}/{s['n_events']} events)"
        )
    o = scoring["overall"]
    _log(
        f"{'OVERALL':<12} detection_rate={o['detection_rate']}  "
        f"false_positive_rate={o['false_positive_rate']}  "
        f"(events {o['events_caught']}/{o['total_events']} fp={o['false_positives']} "
        f"corrupted={o['n_corrupted']}/{o['n_images']} flagged={o['n_flagged']})"
    )
    if o["missed_corruptions"]:
        _log(f"missed corruptions: {o['missed_corruptions']}")


# ---------------------------------------------------------------------------
# Part 2 - Distribution-Shift dual-direction proof
# ---------------------------------------------------------------------------
def load_drift_package() -> str:
    """Expose drift-monitor/src as the alias package 'drift_src'.

    Both modules contain a package literally named `src`; loading the
    drift-monitor one under an alias avoids any sys.modules collision with
    data-integrity's `src` package while keeping drift-monitor's internal
    relative imports working unchanged.
    """
    import importlib
    import types

    drift_root = os.path.join(PROJECT_ROOT, "drift-monitor")
    alias = "drift_src"
    if alias in sys.modules:
        return drift_root
    pkg = types.ModuleType(alias)
    pkg.__path__ = [os.path.join(drift_root, "src")]
    sys.modules[alias] = pkg
    # Execute the real package __init__ so relative imports like
    # `from . import ensure_shared_importable` resolve inside the alias.
    init_path = os.path.join(drift_root, "src", "__init__.py")
    with open(init_path, "r", encoding="utf-8") as f:
        code = compile(f.read(), init_path, "exec")
    # The drift package __init__ reads __file__; provide it for the exec.
    pkg.__dict__["__file__"] = init_path
    exec(code, pkg.__dict__)
    if drift_root not in sys.path:
        sys.path.insert(0, drift_root)
    for mod in ("reference_builder", "threshold_calibrator", "mmd", "run_drift_monitor"):
        importlib.import_module(f"{alias}.{mod}")
    return drift_root


def prove_shift_directions(
    normal_dir: str, shifted_dir: str
) -> Dict[str, Any]:
    """Raw MMD for a normal and a shifted window, vs the calibrated threshold.

    Recomputes both directions live through the drift-monitor modules (same
    reference battery + calibration manifest the CLI runs use).
    """
    import numpy as np

    drift_root = load_drift_package()
    from drift_src.reference_builder import load_reference
    from drift_src.threshold_calibrator import CalibrationUnavailableError, load_calibration
    from drift_src.mmd import mmd
    from drift_src.run_drift_monitor import discover_live_images
    from shared.embeddings.embedding_extractor import create_extractor, load_image

    with open(os.path.join(drift_root, "config.json"), "r", encoding="utf-8") as f:
        drift_config = json.load(f)

    reference = load_reference(drift_root)
    ref_emb = reference["embeddings"]
    try:
        cal = load_calibration(drift_root, reference["manifest"].get("manifest_digest"))
    except CalibrationUnavailableError as exc:
        return {"error": f"calibration unavailable: {exc}"}

    extractor = create_extractor(drift_config.get("embedding", {}))
    batch = int(drift_config.get("embedding", {}).get("batch_size", 32))

    def embed_dir(d: str):
        paths = discover_live_images(d)
        chunks = []
        for start in range(0, len(paths), batch):
            chunk = paths[start:start + batch]
            chunks.append(extractor.extract_batch([load_image(p) for p in chunk]))
        return np.concatenate(chunks, axis=0), paths

    normal_emb, normal_paths = embed_dir(normal_dir)
    shifted_emb, shifted_paths = embed_dir(shifted_dir)

    mmd_cfg = dict(drift_config.get("mmd", {}))
    mmd_cfg["minimum_live_samples"] = 2

    normal_res = mmd(ref_emb, normal_emb, mmd_cfg)
    shifted_res = mmd(ref_emb, shifted_emb, mmd_cfg)
    threshold = float(cal["threshold"])

    normal_alert = normal_res.mmd > threshold
    shifted_alert = shifted_res.mmd > threshold

    return {
        "reference_id": reference["manifest"].get("reference_id"),
        "calibration_id": cal.get("calibration_id"),
        "threshold": threshold,
        "normal_window": {
            "dir": normal_dir,
            "n_images": len(normal_paths),
            "mmd": round(float(normal_res.mmd), 6),
            "alert": bool(normal_alert),
            "expected": "no alert",
            "correct": not normal_alert,
        },
        "shifted_window": {
            "dir": shifted_dir,
            "n_images": len(shifted_paths),
            "mmd": round(float(shifted_res.mmd), 6),
            "alert": bool(shifted_alert),
            "expected": "alert",
            "correct": shifted_alert,
        },
        "both_directions_correct": (not normal_alert) and shifted_alert,
    }


def print_shift_proof(proof: Dict[str, Any]) -> None:
    _log("")
    _log("=== DISTRIBUTION-SHIFT: dual-direction MMD proof ===")
    if "error" in proof:
        _log(f"[FAIL] {proof['error']}")
        return
    _log(
        f"reference={proof['reference_id']} calibration={proof['calibration_id']} "
        f"threshold={proof['threshold']:.6f}"
    )
    for side in ("normal_window", "shifted_window"):
        w = proof[side]
        _log(
            f"{side:<15} n={w['n_images']:<4} mmd={w['mmd']:<10} "
            f"alert={'YES' if w['alert'] else 'no':<4} expected={w['expected']:<9} "
            f"{'[OK]' if w['correct'] else '[FAIL]'}"
        )
    _log(
        "both directions correct: "
        + ("[OK] YES" if proof["both_directions_correct"] else "[FAIL] NO")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="SentinelVision Stage 6 validation")
    parser.add_argument("--integrity-config", default=os.path.join(DATA_INTEGRITY_ROOT, "config.json"))
    parser.add_argument("--integrity-dir", default=os.path.join(PROJECT_ROOT, "data", "integrity-test"))
    parser.add_argument("--labels", default=os.path.join(PROJECT_ROOT, "data", "integrity-test", "label_key.json"))
    parser.add_argument("--normal-dir", default=os.path.join(PROJECT_ROOT, "data", "scenario1-normal"))
    parser.add_argument("--shifted-dir", default=os.path.join(PROJECT_ROOT, "data", "scenario2-lighting-shift"))
    parser.add_argument("--checks", default="duplicate,ood,label_flip")
    parser.add_argument("--out", default=os.path.join(DATA_INTEGRITY_ROOT, "results", "validation_report.json"))
    args = parser.parse_args()

    with open(os.path.abspath(args.integrity_config), "r", encoding="utf-8") as f:
        integrity_config = json.load(f)

    # --- Part 1: Data Integrity ---
    from src.dataset import build_dataset, load_answer_key
    from src.integrity_checker import check_dataset

    # The labels sidecar doubles as the answer key here; load_answer_key
    # returns its full per-image records (corruption/true_label/...).
    with open(os.path.abspath(args.labels), "r", encoding="utf-8") as f:
        answer_key = json.load(f).get("labels")
    dataset, dataset_meta = build_dataset(
        input_dir=os.path.abspath(args.integrity_dir),
        labels_path=os.path.abspath(args.labels),
        extractor_config=integrity_config.get("embedding", {}),
        cache_path=os.path.join(
            DATA_INTEGRITY_ROOT,
            integrity_config.get("output", {}).get("embedding_cache", "cache/embeddings.json"),
        ),
    )
    _log(f"[OK] dataset: {dataset_meta['image_count']} images")
    check_result = check_dataset(
        dataset,
        integrity_config,
        checks_to_run=[c.strip() for c in args.checks.split(",") if c.strip()],
        answer_key=answer_key,
    )
    scoring = score_integrity(check_result, answer_key)
    print_integrity_table(scoring)

    # --- Part 2: Distribution-Shift dual-direction proof ---
    proof = prove_shift_directions(os.path.abspath(args.normal_dir), os.path.abspath(args.shifted_dir))
    print_shift_proof(proof)

    report = {
        "integrity": scoring,
        "shift_proof": proof,
        "coverage_statement": check_result.get("coverage_statement"),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(os.path.abspath(args.out), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    _log(f"[OK] validation report written: {args.out}")

    # Non-zero exit only on hard failures so CI can assert on this script.
    if "error" in proof or not proof.get("both_directions_correct"):
        sys.exit(2)


if __name__ == "__main__":
    main()
