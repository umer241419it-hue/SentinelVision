#!/usr/bin/env python3
"""
SentinelVision - Data Integrity runner (CLI).

Pipeline for one Data Integrity run:

    labeled images -> shared frozen embeddings (cached) -> duplicate/OOD/
    label-flip checks -> combined per-image verdicts -> evidence JSON ->
    SHA-256 -> findings (one per flagged image) -> [POST /findings] -> Fabric

Usage (from data-integrity/):
    python -m src.run_data_integrity --config config.json \
        --input ../data/integrity-test --labels ../data/integrity-test/label_key.json

    # submit findings through the existing bridge:
    python -m src.run_data_integrity --config config.json \
        --input ../data/integrity-test --labels ../data/integrity-test/label_key.json \
        --submit --bridge-url http://localhost:3000
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict

import numpy as np

from . import ensure_shared_importable  # noqa: F401  (path bootstrap)

from .bridge_client import submit_finding
from .dataset import build_dataset, load_answer_key
from .evidence_builder import build_and_store_evidence
from .finding_builder import build_finding, validate_evidence_hash_binding
from .integrity_checker import MODULE_NAME, MODULE_VERSION, check_dataset, summarize


def _log(msg: str) -> None:
    print(msg, flush=True)


def run(
    config: Dict[str, Any],
    input_dir: str,
    labels_path: str,
    answer_key_path: str = None,
    base_dir: str = None,
    bridge_url: str = None,
    submit: bool = False,
    timestamp_fixed: str = None,
    checks: str = "duplicate,ood,label_flip",
) -> Dict[str, Any]:
    """Run the full Data Integrity pipeline; returns the results dict."""
    base_dir = base_dir or os.path.dirname(os.path.abspath(__file__ + "/.."))
    timestamp = timestamp_fixed or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    checks_to_run = [c.strip() for c in checks.split(",") if c.strip()]

    _log("[OK] offline mode enabled (no network access at runtime)")
    if config.get("mode", "offline") != "offline":
        raise SystemExit("config.mode must be 'offline' for this module.")

    answer_key = load_answer_key(answer_key_path) if answer_key_path else None

    dataset, dataset_meta = build_dataset(
        input_dir=input_dir,
        labels_path=labels_path,
        extractor_config=config.get("embedding", {}),
        cache_path=os.path.join(base_dir, config.get("output", {}).get("embedding_cache", "cache/embeddings.npz")),
    )
    _log(
        f"[OK] dataset: {dataset_meta['image_count']} images "
        f"({dataset_meta['label_distribution']}) backbone={dataset.extractor_metadata['backbone']}"
    )

    result = check_dataset(
        dataset,
        config,
        checks_to_run=checks_to_run,
        answer_key=answer_key,
    )
    if result["check_errors"]:
        for check, err in result["check_errors"].items():
            _log(f"[WARN] check '{check}' failed: {err}")

    evidence_store = os.path.join(base_dir, config.get("output", {}).get("evidence_store", "evidence_store"))
    results_path = os.path.join(base_dir, config.get("output", {}).get("results", "results/integrity_results.json"))

    entries = []
    for image_id in sorted(result["flagged"].keys()):
        record = result["flagged"][image_id]
        stored = build_and_store_evidence(record, result["dataset"], result["check_results"], evidence_store, timestamp)
        finding = build_finding(record, stored["evidence_hash"], timestamp)
        evidence_path = validate_evidence_hash_binding(finding, evidence_store)

        entry = {
            "image_id": image_id,
            "flags": record["flags"],
            "severity": record["severity"],
            "disposition": record["disposition"],
            "confidence": record["confidence"],
            "reason": record["reason"],
            "evidence_hash": stored["evidence_hash"],
            "evidence_path": os.path.relpath(evidence_path, base_dir).replace(os.sep, "/"),
            "finding": finding,
        }
        if submit and bridge_url:
            entry["bridge"] = submit_finding(finding, bridge_url)
            _log(
                f"[BRIDGE] assetID={finding['assetID']} submitted={entry['bridge'].get('submitted')} "
                f"http={entry['bridge'].get('http_status')}"
            )
        entries.append(entry)
        _log(f"[FLAGGED] {image_id} flags={record['flags']} severity={record['severity']} "
             f"confidence={record['confidence']} evidence={stored['evidence_hash'][:16]}...")

    summary = summarize(result)
    summary["findings_submitted"] = sum(1 for e in entries if e.get("bridge", {}).get("submitted"))
    output = {
        "run": {
            "module": MODULE_NAME,
            "module_version": MODULE_VERSION,
            "run_timestamp": timestamp,
            "mode": "offline",
            "input_dir": input_dir,
            "labels_path": labels_path,
            "answer_key_path": answer_key_path,
            "checks_run": result["checks_run"],
        },
        "summary": summary,
        "results": entries,
        "flagged": result["flagged"],
        "coverage_statement": result["coverage_statement"],
        "known_limitations": result["known_limitations"],
    }
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    _log(f"[OK] results written: {results_path}")
    _log(f"[SUMMARY] {json.dumps(summary)}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="SentinelVision Data Integrity runner")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--input", required=True, help="Directory of labeled images")
    parser.add_argument("--labels", required=True, help="Labels sidecar JSON")
    parser.add_argument("--answer-key", default=None, help="Optional ground-truth answer key JSON")
    parser.add_argument("--checks", default="duplicate,ood,label_flip",
                        help="Comma-separated subset: duplicate,ood,label_flip")
    parser.add_argument("--submit", action="store_true", help="Submit findings to the bridge")
    parser.add_argument("--bridge-url", default=os.environ.get("BRIDGE_URL", "http://localhost:3000"))
    parser.add_argument("--timestamp-fixed", default=None, help="Fixed run timestamp for reproducible runs")
    args = parser.parse_args()

    config_path = os.path.abspath(args.config)
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    base = os.path.dirname(config_path)

    run(
        config=config,
        input_dir=os.path.abspath(args.input),
        labels_path=os.path.abspath(args.labels),
        answer_key_path=os.path.abspath(args.answer_key) if args.answer_key else None,
        base_dir=base,
        bridge_url=args.bridge_url,
        submit=args.submit,
        timestamp_fixed=args.timestamp_fixed,
        checks=args.checks,
    )


if __name__ == "__main__":
    main()
