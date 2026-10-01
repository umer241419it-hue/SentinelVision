#!/usr/bin/env python3
"""
SentinelVision - Phase 10: Drift Monitor Runner (CLI)
=====================================================

Full pipeline for one drift-monitoring run:

    live images -> embeddings -> rolling window -> MMD -> diagnostics
      -> evidence JSON -> SHA-256 -> finding JSON -> [POST /findings] -> Fabric

Usage:
    python -m src.run_drift_monitor --config config.json --input ./live-data

    # also submit findings through the existing Node bridge:
    python -m src.run_drift_monitor --config config.json \\
        --input ./live-data --submit --bridge-url http://localhost:3000

    # byte-identical reproducibility run (fixed evidence timestamp):
    python -m src.run_drift_monitor --config config.json \\
        --input ./live-data --timestamp-fixed 2026-01-01T00:00:00Z

Startup validation (task.md 18) prints [OK] lines or fails with actionable
messages before any processing. Runtime is fully offline: no downloads, no
cloud APIs, no telemetry.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from . import ensure_shared_importable  # noqa: F401  (path bootstrap)

from shared.embeddings.embedding_extractor import (
    EmbeddingError,
    MissingWeightsError,
    create_extractor,
    load_image,
)

from .drift_detector import MODULE_NAME, MODULE_VERSION, check_window
from .evidence_builder import COVERAGE_STATEMENT, build_and_store_evidence
from .finding_builder import build_finding, validate_evidence_hash_binding
from .reference_builder import BASE_DIR, load_reference
from .rolling_window import RollingWindow, feed_stream
from .threshold_calibrator import CalibrationUnavailableError, load_calibration

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def _log(msg: str) -> None:
    print(msg, flush=True)


def startup_validation(config: Dict[str, Any], base_dir: str) -> None:
    """Offline/startup checks with [OK] lines; raises with actionable errors."""
    _log("[OK] offline mode enabled (no network access at runtime)")
    if config.get("mode", "offline") != "offline":
        raise EmbeddingError("config.mode must be 'offline' for this module.")

    backbone = config.get("embedding", {}).get("backbone", "pixelstat")
    try:
        create_extractor(config.get("embedding", {}))
        if backbone == "resnet50":
            _log("[OK] local embedding weights found (backbone=resnet50)")
        else:
            _log(f"[OK] local embedding backbone ready (backbone={backbone}; no external weights required)")
    except MissingWeightsError as exc:
        _log("[FAIL] local embedding weights NOT found")
        raise SystemExit(f"startup validation failed: {exc}")

    reference_dir = os.path.join(base_dir, "reference", "reference_manifest.json")
    if not os.path.isfile(reference_dir):
        raise SystemExit(
            "startup validation failed: reference battery not found. Run: "
            "python -m src.reference_builder --config config.json"
        )
    _log("[OK] reference battery found")

    calibration_path = os.path.join(base_dir, "calibration", "threshold_manifest.json")
    if not os.path.isfile(calibration_path):
        raise SystemExit(
            "startup validation failed: calibration manifest not found. Run: "
            "python -m src.threshold_calibrator --config config.json"
        )
    _log("[OK] calibration manifest found")


def discover_live_images(input_dir: str) -> List[str]:
    """Deterministically list live image paths (sorted)."""
    if not os.path.isdir(input_dir):
        raise SystemExit(f"startup validation failed: live input directory not found: {input_dir}")
    paths: List[str] = []
    for root, _dirs, files in os.walk(input_dir):
        for name in sorted(files):
            p = os.path.join(root, name)
            if os.path.splitext(p)[1].lower() in IMAGE_EXTENSIONS:
                paths.append(p)
    return sorted(paths)


def extract_live_embeddings(
    input_dir: str, extractor, batch_size: int
):
    """Embed all live images in batches. Returns (embeddings, metadata).

    metadata per image: image_path (for diagnostics), image_id (filename),
    source_id (immediate parent folder name if any). Timestamps are not
    fabricated; they stay None when unknown so evidence never fakes data.
    """
    paths = discover_live_images(input_dir)
    if not paths:
        raise SystemExit(f"startup validation failed: no images under {input_dir}")
    embeddings: List[np.ndarray] = []
    metadata: List[Dict[str, Any]] = []
    for start in range(0, len(paths), batch_size):
        batch = paths[start:start + batch_size]
        images = [load_image(p) for p in batch]
        embeddings.append(extractor.extract_batch(images))
        for p in batch:
            parent = os.path.basename(os.path.dirname(p))
            metadata.append(
                {
                    "image_path": p,
                    "image_id": os.path.basename(p),
                    "source_id": parent if parent and parent != os.path.basename(input_dir) else None,
                    "timestamp": None,
                }
            )
    return np.concatenate(embeddings, axis=0), metadata


def submit_finding_to_bridge(finding: Dict[str, Any], bridge_url: str, timeout: int = 20) -> Dict[str, Any]:
    """POST the finding to the existing bridge, then GET it back to verify
    the Fabric commit. Uses stdlib urllib only (no extra dependencies)."""
    post_url = bridge_url.rstrip("/") + "/findings"
    data = json.dumps(finding).encode("utf-8")
    req = urllib.request.Request(
        post_url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"submitted": False, "http_status": exc.code, "error": exc.read().decode("utf-8", "replace")}
    except urllib.error.URLError as exc:
        return {"submitted": False, "http_status": None, "error": str(exc.reason)}

    verification = None
    try:
        get_url = (
            bridge_url.rstrip("/")
            + "/findings/"
            + urllib.parse.quote(finding["assetID"], safe="")
        )
        with urllib.request.urlopen(urllib.request.Request(get_url, method="GET"), timeout=timeout) as resp:
            verification = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        verification = {"verified": False, "error": str(getattr(exc, "reason", exc))}

    return {
        "submitted": status == 201,
        "http_status": status,
        "bridge_response": body,
        "ledger_verification": verification,
    }


def run(
    config: Dict[str, Any],
    input_dir: str,
    base_dir: str = BASE_DIR,
    bridge_url: Optional[str] = None,
    submit: bool = False,
    timestamp_fixed: Optional[str] = None,
    reference_manifest_path: Optional[str] = None,
    run_id: Optional[str] = None,
    results_path_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full drift monitoring pipeline; returns the results dict."""
    startup_validation(config, base_dir)

    reference = load_reference(base_dir)
    ref_manifest = reference["manifest"]

    # If an explicit reference manifest was requested, verify it is the one built.
    if reference_manifest_path:
        with open(reference_manifest_path, "r", encoding="utf-8") as f:
            requested = json.load(f)
        if requested.get("manifest_digest") != ref_manifest.get("manifest_digest"):
            raise SystemExit(
                "Requested reference manifest does not match the built reference "
                "(manifest_digest mismatch). Rebuild the reference battery or pass "
                "the correct manifest."
            )

    try:
        calibration = load_calibration(base_dir, ref_manifest.get("manifest_digest"))
    except CalibrationUnavailableError as exc:
        # Windows will be evaluated as INSUFFICIENT_EVIDENCE; never a guessed verdict.
        calibration = None
        _log(f"[WARN] {exc}")

    extractor = create_extractor(config.get("embedding", {}))
    emb_meta = extractor.metadata()

    win_cfg = config.get("window", {})
    window = RollingWindow(
        window_size=int(win_cfg.get("size", 100)),
        step_size=int(win_cfg.get("step", 25)),
        minimum_samples=int(win_cfg.get("minimum_samples", win_cfg.get("size", 100))),
    )

    batch_size = int(config.get("embedding", {}).get("batch_size", 32))
    live_emb, live_meta = extract_live_embeddings(input_dir, extractor, batch_size)
    _log(f"[OK] embedded {live_emb.shape[0]} live images (dim={live_emb.shape[1]})")

    timestamp = timestamp_fixed or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if run_id is None:
        ts_clean = timestamp.replace(":", "").replace("-", "")
        ref_digest = (ref_manifest.get("manifest_digest") or ref_manifest.get("source_digest") or "")[:8]
        effective_run_id = f"{ts_clean}-{ref_digest}" if ref_digest else ts_clean
    else:
        effective_run_id = run_id
    evidence_store = os.path.join(base_dir, config.get("output", {}).get("evidence_store", "evidence_store"))
    results_path = os.path.abspath(results_path_override or os.path.join(base_dir, config.get("output", {}).get("results", "results/drift_results.json")))

    results: List[Dict[str, Any]] = []
    for seq_idx, win in feed_stream(window, live_emb, live_meta):
        run_result = check_window(reference, win, seq_idx, config, base_dir, calibration)
        stored = build_and_store_evidence(run_result, evidence_store, timestamp, run_id=effective_run_id)
        finding = build_finding(run_result, stored["evidence_hash"], timestamp, run_id=effective_run_id)
        evidence_path = validate_evidence_hash_binding(finding, evidence_store)

        entry: Dict[str, Any] = {
            "window_id": run_result["live_window"]["window_id"],
            "sequence_index": seq_idx,
            "image_count": run_result["live_window"]["image_count"],
            "assessment": run_result["assessment"],
            "mmd": run_result.get("mmd"),
            "threshold": run_result.get("threshold"),
            "policy": run_result.get("policy"),
            "diagnostics": run_result.get("diagnostics"),
            "evidence_hash": stored["evidence_hash"],
            "evidence_path": os.path.relpath(evidence_path, base_dir).replace(os.sep, "/"),
            "finding": finding,
        }
        if submit and bridge_url:
            entry["bridge"] = submit_finding_to_bridge(finding, bridge_url)
            entry["bridge"]["assetID"] = finding["assetID"]

        results.append(entry)

        # Structured per-window log (task.md section 20).
        mmd_val = run_result.get("mmd") or {}
        thr = run_result.get("threshold") or {}
        _log(
            f"[WINDOW] id={entry['window_id']} images={entry['image_count']} "
            f"reference={ref_manifest.get('reference_id')} backbone={emb_meta['backbone']} "
            f"mmd={mmd_val.get('mmd')} threshold={thr.get('value')} "
            f"calibration={thr.get('calibration_id')} "
            f"assessment={entry['assessment']} severity={entry['policy']['severity']} "
            f"disposition={entry['policy']['disposition']} "
            f"confidence={entry['policy']['confidence']} "
            f"evidence={stored['evidence_hash'][:16]}..."
        )
        if entry.get("bridge"):
            b = entry["bridge"]
            _log(
                f"[BRIDGE] assetID={finding['assetID']} submitted={b.get('submitted')} "
                f"http={b.get('http_status')}"
            )

    summary = {
        "windows_checked": len(results),
        "assessments": {
            a: sum(1 for r in results if r["assessment"] == a)
            for a in sorted({r["assessment"] for r in results})
        },
        "findings_submitted": sum(1 for r in results if r.get("bridge", {}).get("submitted")),
    }

    run_metadata = {
        "module": MODULE_NAME,
        "module_version": MODULE_VERSION,
        "run_id": effective_run_id,
        "run_timestamp": timestamp,
        "mode": "offline",
        "reference_id": ref_manifest.get("reference_id"),
        "reference_manifest_digest": ref_manifest.get("manifest_digest"),
        "reference_source_digest": ref_manifest.get("source_digest"),
        "reference_embedding_digest": ref_manifest.get("embedding_digest"),
        "embedding_backbone": emb_meta["backbone"],
        "embedding_metadata": emb_meta,
        "embedding_dim": emb_meta["embedding_dim"],
        "window_size": window.window_size,
        "window_step": window.step_size,
        "window_minimum_samples": window.minimum_samples,
        "calibration_id": (calibration or {}).get("calibration_id"),
        "threshold_value": (calibration or {}).get("threshold"),
        "mmd_kernel": config.get("mmd", {}).get("kernel", "rbf"),
        "mmd_bandwidth": config.get("mmd", {}).get("bandwidth", "auto"),
        "mmd_permutations": config.get("mmd", {}).get("permutations", 0),
        "mmd_seed": config.get("mmd", {}).get("seed"),
        "live_input": os.path.abspath(input_dir),
        "live_image_count": int(live_emb.shape[0]),
        "coverage_statement": COVERAGE_STATEMENT,
    }

    output = {"run": run_metadata, "summary": summary, "results": results}
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    _log(f"[OK] results written: {results_path}")
    _log(f"[SUMMARY] {json.dumps(summary)}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="SentinelVision Drift Monitor")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--input", required=True, help="Directory of live images")
    parser.add_argument("--reference", default=None, help="Optional reference manifest path to verify against")
    parser.add_argument("--submit", action="store_true", help="Submit findings to the bridge (POST /findings)")
    parser.add_argument("--bridge-url", default=os.environ.get("BRIDGE_URL", "http://localhost:3000"))
    parser.add_argument("--timestamp-fixed", default=None, help="Fixed run timestamp for reproducibility runs")
    parser.add_argument("--run-id", default=None, help="Explicit run ID (defaults to UTC timestamp + reference digest)")
    parser.add_argument("--output", default=None, help="Per-run drift results JSON path")
    args = parser.parse_args()

    config_path = os.path.abspath(args.config)
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    base = os.path.dirname(config_path)

    run(
        config=config,
        input_dir=os.path.abspath(args.input),
        base_dir=base,
        bridge_url=args.bridge_url,
        submit=args.submit,
        timestamp_fixed=args.timestamp_fixed,
        reference_manifest_path=os.path.abspath(args.reference) if args.reference else None,
        run_id=args.run_id,
        results_path_override=os.path.abspath(args.output) if args.output else None,
    )


if __name__ == "__main__":
    main()
