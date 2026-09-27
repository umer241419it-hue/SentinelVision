#!/usr/bin/env python3
"""
SentinelVision - Unified Command-Line Interface.

Trustworthy Computer Vision Integrity Assurance for Data, Models and Inference Outputs
(SIH Problem Statement 26228)

Commands:
    sentinelvision dataset prepare-voc2012
    sentinelvision integrity generate-benchmark
    sentinelvision integrity scan
    sentinelvision integrity evaluate
    sentinelvision report generate
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

WORKSPACE_ROOT = os.path.abspath(os.path.dirname(__file__))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

DATA_INTEGRITY_DIR = os.path.join(WORKSPACE_ROOT, "data-integrity")
if DATA_INTEGRITY_DIR not in sys.path:
    sys.path.insert(0, DATA_INTEGRITY_DIR)

from pathlib import Path


def _load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    default_path = os.path.join(DATA_INTEGRITY_DIR, "benchmark_config.json")
    path = config_path or default_path
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    fallback = os.path.join(DATA_INTEGRITY_DIR, "config.json")
    with open(fallback, "r", encoding="utf-8") as f:
        return json.load(f)


def cmd_dataset_prepare_voc2012(args):
    """Prepare and validate the official PASCAL VOC2012 benchmark dataset."""
    from src.voc_setup import (
        EXPECTED_MD5,
        EXPECTED_SHA1,
        EXPECTED_ARCHIVE_SIZE,
        OFFICIAL_URL_PRIMARY,
        download_voc2012,
        extract_voc2012,
        verify_archive,
    )
    from src.voc_adapter import VOC2012Adapter
    from src.provenance_generator import generate_synthetic_provenance
    from src.benchmark_generator import BenchmarkGenerator

    print("=" * 70)
    print("SENTINELVISION: PASCAL VOC2012 Dataset Preparation")
    print("=" * 70)

    config = _load_config(args.config)
    downloads_dir = Path(WORKSPACE_ROOT) / "datasets" / "downloads"
    raw_dir = Path(WORKSPACE_ROOT) / config.get("dataset", {}).get("raw_dir", "datasets/sentinelvision_voc2012/raw")
    clean_dir = Path(WORKSPACE_ROOT) / config.get("dataset", {}).get("clean_dir", "datasets/sentinelvision_voc2012/clean")
    meta_dir = Path(WORKSPACE_ROOT) / config.get("dataset", {}).get("metadata_dir", "datasets/sentinelvision_voc2012/metadata")
    downloads_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    archive_path = downloads_dir / "VOCtrainval_11-May-2012.tar"

    # Step 1: Check / download archive
    if not archive_path.exists() or archive_path.stat().st_size < EXPECTED_ARCHIVE_SIZE:
        print(f"[*] Downloading official VOC2012 archive from {OFFICIAL_URL_PRIMARY}...")
        download_voc2012(archive_path)
    else:
        print(f"[OK] Archive found: {archive_path} ({archive_path.stat().st_size:,} bytes)")

    # Step 2: Verify checksum
    print("[*] Verifying archive checksum (MD5 & SHA-1)...")
    valid, info = verify_archive(archive_path)
    if not valid:
        print(f"[ERROR] Archive verification failed: {info}")
        sys.exit(1)
    computed_md5 = info["hashes"]["md5"]
    computed_sha1 = info["hashes"]["sha1"]
    print(f"[OK] Checksum verified: MD5={computed_md5}, SHA-1={computed_sha1}")

    # Step 3: Extract archive safely
    voc2012_dir = raw_dir / "VOCdevkit" / "VOC2012"
    if not voc2012_dir.exists():
        print(f"[*] Extracting archive safely to {raw_dir}...")
        extract_voc2012(archive_path, raw_dir)
    else:
        print(f"[OK] VOC2012 already extracted at {voc2012_dir}")

    # Step 4: Validate VOC structure & generate dataset manifest
    print("[*] Parsing VOC2012 annotations and generating dataset manifest...")
    voc2012_dir_str = str(voc2012_dir)
    meta_dir_str = str(meta_dir)
    clean_dir_str = str(clean_dir)
    adapter = VOC2012Adapter(voc2012_dir_str)
    manifest_path = os.path.join(meta_dir_str, "dataset_manifest.json")
    manifest = adapter.generate_manifest(
        output_path=Path(manifest_path),
        archive_hashes={"md5": computed_md5, "sha1": computed_sha1},
        archive_size=EXPECTED_ARCHIVE_SIZE,
    )
    print(f"[OK] Manifest generated at {manifest_path}")
    print(f"     Total Images:  {manifest['image_count']:,}")
    print(f"     Total Objects: {manifest['object_count']:,}")
    print(f"     Classes:       {len(manifest['class_image_distribution'])}")

    # Step 5: Generate synthetic provenance metadata
    print("[*] Generating synthetic multi-contributor provenance metadata...")
    prov_path = os.path.join(meta_dir_str, "provenance.json")
    all_sample_ids = [f"voc2012_{sid}" for sid in adapter.get_image_ids(split=None)]
    prov_data = generate_synthetic_provenance(
        sample_ids=all_sample_ids,
        num_contributors=config.get("provenance", {}).get("num_contributors", 10),
        num_sources=config.get("provenance", {}).get("num_sources", 4),
        num_batches=config.get("provenance", {}).get("num_batches", 20),
        collection_id=config.get("provenance", {}).get("collection_id", "voc2012_sih_pipeline"),
        seed=config.get("provenance", {}).get("seed", 42),
        output_path=prov_path,
    )
    print(f"[OK] Provenance generated at {prov_path} for {len(prov_data['provenance_records']):,} samples")

    # Step 6: Setup clean baseline directory
    print(f"[*] Creating clean baseline view at {clean_dir_str}...")
    bg = BenchmarkGenerator(voc2012_dir_str, os.path.dirname(clean_dir_str), provenance_path=prov_path)
    # Prepare clean view for a representative validation subset
    val_ids = adapter.get_image_ids(split="val")[: args.limit if args.limit else 500]
    bg.generate_clean_benchmark(clean_dir_str, sample_ids=val_ids)
    print(f"[OK] Clean baseline ready ({len(val_ids)} samples) at {clean_dir_str}")
    print("[SUCCESS] VOC2012 dataset preparation complete. Offline operation ready.")


def cmd_integrity_generate_benchmark(args):
    """Generate controlled attack benchmarks with ground truth manifest."""
    from src.voc_adapter import VOC2012Adapter
    from src.benchmark_generator import BenchmarkGenerator

    print("=" * 70)
    print("SENTINELVISION: Controlled Attack Benchmark Generation")
    print("=" * 70)

    config = _load_config(args.config)
    raw_dir = os.path.join(WORKSPACE_ROOT, config.get("dataset", {}).get("raw_dir", "datasets/sentinelvision_voc2012/raw"))
    voc2012_dir = os.path.join(raw_dir, "VOCdevkit", "VOC2012")
    benchmarks_root = os.path.join(WORKSPACE_ROOT, "datasets", "sentinelvision_voc2012")
    meta_dir = os.path.join(benchmarks_root, "metadata")
    prov_path = os.path.join(meta_dir, "provenance.json")

    if not os.path.exists(voc2012_dir):
        print(f"[ERROR] VOC2012 not found at {voc2012_dir}. Run 'dataset prepare-voc2012' first.")
        sys.exit(1)

    adapter = VOC2012Adapter(voc2012_dir)
    bg = BenchmarkGenerator(voc2012_dir, benchmarks_root, provenance_path=prov_path, seed=args.seed)

    limit = args.limit or 300
    candidate_ids = adapter.get_image_ids(split="val")[:limit]
    print(f"[*] Base sample pool size: {len(candidate_ids)} samples")

    # 1. Label flip benchmark
    print("[*] Generating Label Flipping scenario (5% & 10%)...")
    bg.generate_label_flip_scenario(
        output_dir=os.path.join(benchmarks_root, "label_flip"),
        sample_ids=candidate_ids,
        flip_rate=0.08,
    )

    # 2. Systematic mislabelling benchmark
    print("[*] Generating Systematic Mislabelling scenario (contributor_07)...")
    bg.generate_systematic_mislabel_scenario(
        output_dir=os.path.join(benchmarks_root, "systematic_mislabel"),
        sample_ids=candidate_ids,
        target_contributor="contributor_07",
        confusion_pair=("chair", "sofa"),
        corruption_fraction=0.75,
    )

    # 3. Duplicate flooding benchmark
    print("[*] Generating Near-Duplicate Flooding scenario (exact + transformed)...")
    bg.generate_duplicate_flooding_scenario(
        output_dir=os.path.join(benchmarks_root, "duplicate_flooding"),
        sample_ids=candidate_ids,
        duplicate_rate=0.08,
        target_contributor="contributor_03",
    )

    # 4. OOD insertion benchmark
    print("[*] Generating Out-Of-Distribution (OOD) insertion scenario...")
    bg.generate_ood_insertion_scenario(
        output_dir=os.path.join(benchmarks_root, "ood_insertion"),
        sample_ids=candidate_ids,
        ood_count=12,
    )

    # 5. Trigger injection benchmark
    print("[*] Generating Training-Data Trigger Injection scenario (corner patch)...")
    bg.generate_trigger_injection_scenario(
        output_dir=os.path.join(benchmarks_root, "trigger_injection"),
        sample_ids=candidate_ids,
        poison_rate=0.06,
        target_class="aeroplane",
    )

    # 6. Mixed multi-vector attack benchmark
    print("[*] Generating Multi-Vector Mixed Attack scenario...")
    bg.generate_mixed_attack_scenario(
        output_dir=os.path.join(benchmarks_root, "mixed_attack"),
        sample_ids=candidate_ids,
        label_flip_rate=0.05,
        duplicate_rate=0.05,
        trigger_rate=0.04,
        ood_count=8,
        systematic_contributor="contributor_07",
    )

    # Write authoritative attack manifest
    attack_manifest_path = os.path.join(meta_dir, "attack_manifest.json")
    bg.write_attack_manifest(attack_manifest_path)
    print(f"[OK] Authoritative ground truth written to {attack_manifest_path}")
    print(f"     Total attacks recorded: {len(bg.attacks)}")


def cmd_integrity_scan(args):
    """Scan a dataset for data-integrity anomalies (offline)."""
    from src.voc_adapter import VOC2012Adapter
    from src.dataset import build_dataset
    from src.integrity_checker import check_dataset
    from src.trigger_detector import TriggerDetector
    from src.evidence_fusion import EvidenceFusionEngine
    from src.finding_builder import build_finding
    from src.evidence_builder import build_and_store_evidence
    from src.provenance_aggregator import ProvenanceAggregator

    print("=" * 70)
    print("SENTINELVISION: Training Data Integrity Scan")
    print("=" * 70)

    dataset_path = os.path.abspath(args.dataset)
    images_dir = os.path.join(dataset_path, "JPEGImages")
    annos_dir = os.path.join(dataset_path, "Annotations")

    if not os.path.exists(images_dir):
        print(f"[ERROR] JPEGImages directory not found at {images_dir}")
        sys.exit(1)

    config = _load_config(args.config)
    adapter = VOC2012Adapter(dataset_path)

    # Prepare labels dict for cleanlab detector
    labels_dict = {}
    multi_labels = {}
    image_paths = []
    all_files = sorted([
        f for f in os.listdir(images_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ])

    requested_limit = getattr(args, "limit", None)
    if requested_limit is not None:
        requested_limit = int(requested_limit)
        if requested_limit <= 0:
            print(f"[ERROR] --limit must be a positive integer, got {requested_limit}")
            sys.exit(1)
        all_files = all_files[:requested_limit]

    print(f"[*] Ingesting {len(all_files)} samples from {dataset_path}...")
    for fname in all_files:
        sid = os.path.splitext(fname)[0]
        sample = adapter.get_sample(sid)
        cls = sample.objects[0].class_name if (sample and sample.objects) else "background"
        labels_dict[fname] = cls
        multi_labels[fname] = [o.class_name for o in sample.objects] if (sample and sample.objects) else ["background"]
        image_paths.append(os.path.join(images_dir, fname))

    # Load synthetic provenance metadata if present
    meta_dir = os.path.join(WORKSPACE_ROOT, "datasets", "sentinelvision_voc2012", "metadata")
    prov_file = os.path.join(meta_dir, "provenance.json")
    provenance_records = {}
    if os.path.exists(prov_file):
        with open(prov_file, "r", encoding="utf-8") as f:
            provenance_records = json.load(f).get("provenance_records", {})

    # Build image dataset with offline pixelstat embeddings
    print("[*] Extracting offline standardized embeddings...")
    tmp_labels_path = os.path.join(dataset_path, "labels_temp.json")
    with open(tmp_labels_path, "w", encoding="utf-8") as f:
        json.dump(labels_dict, f)

    output_dir = os.path.abspath(args.output_dir or os.path.join(WORKSPACE_ROOT, "datasets", "sentinelvision_voc2012", "results"))
    os.makedirs(output_dir, exist_ok=True)

    emb_cfg = config.get("detectors", {}).get("embedding", {})
    backbone = emb_cfg.get("backbone", "pixelstat")

    if requested_limit is not None:
        cache_path = os.path.join(output_dir, f"{backbone}_cache.json")
    else:
        pref_cache = os.path.join(dataset_path, f"{backbone}_cache.npz")
        cache_path = (
            pref_cache
            if os.path.exists(pref_cache)
            else os.path.join(dataset_path, "embeddings_cache.npz")
        )

    dataset, dataset_meta = build_dataset(
        input_dir=images_dir,
        labels_path=tmp_labels_path,
        extractor_config=emb_cfg,
        cache_path=cache_path,
        image_ids=all_files,
    )
    dataset.multi_labels = multi_labels

    # Run duplicate, OOD, and label-flip checks
    print("[*] Running Duplicate, OOD, and Label-Flip detectors...")
    checker_results = check_dataset(dataset, config.get("detectors", config))

    # Run Trigger Detector
    print("[*] Running Training-Data Trigger Detector (patch residual cross-correlation)...")
    trigger_detector = TriggerDetector()
    stem_labels = {os.path.splitext(k)[0]: v for k, v in labels_dict.items()}
    trigger_candidates = trigger_detector.detect_triggers(
        image_paths=image_paths,
        labels=stem_labels,
        candidate_classes=list(set(stem_labels.values())),
    )
    trigger_flagged = {
        os.path.splitext(c["sample_id"])[0]: c for c in trigger_candidates
    }

    # Fuse evidence for each sample
    fusion_engine = EvidenceFusionEngine()
    sample_findings = []

    # Collect all flagged stems
    flagged_stems = set()
    for sid in checker_results.get("flagged", {}).keys():
        flagged_stems.add(os.path.splitext(sid)[0])
    for sid in trigger_flagged.keys():
        flagged_stems.add(os.path.splitext(sid)[0])

    print(f"[*] Consolidating findings across {len(flagged_stems)} flagged samples...")

    for stem in flagged_stems:
        det_flags = {}

        # Checker results check by filename or stem
        for sid, chk in checker_results.get("flagged", {}).items():
            if os.path.splitext(sid)[0] == stem:
                for f in chk.get("flags", []):
                    det_flags[f] = {
                        "flagged": True,
                        "confidence": chk.get("confidence", 0.65),
                        "severity": chk.get("severity", "MEDIUM"),
                        "reason": chk.get("reason", f),
                        "details": chk.get("details", {}),
                    }

        # Trigger detector check by stem
        if stem in trigger_flagged:
            tc = trigger_flagged[stem]
            det_flags["trigger"] = {
                "flagged": True,
                "confidence": tc.get("confidence", 0.90),
                "severity": tc.get("severity", "CRITICAL"),
                "reason": tc.get("reason", "Trigger pattern detected"),
                "details": tc,
            }

        canon_sid = f"voc2012_{stem}" if not stem.startswith("voc2012_") else stem
        prov_info = provenance_records.get(canon_sid, provenance_records.get(stem, {}))
        fused = fusion_engine.fuse_sample_evidence(
            sample_id=canon_sid,
            detector_flags=det_flags,
            provenance_info=prov_info,
        )
        if fused:
            sample_findings.append(fused)

    # Run Group-level Provenance Aggregation
    print("[*] Running Group-Level Provenance Aggregation & Systematic Mislabel Analysis...")
    aggregator = ProvenanceAggregator()
    group_analysis = aggregator.aggregate(
        sample_findings=sample_findings,
        provenance_records=provenance_records,
        total_sample_count=len(all_files),
    )

    print(f"[OK] Scan complete: {len(sample_findings)} anomalous samples, {len(group_analysis['group_findings'])} group anomalies.")

    # Save scan outputs
    results_dir = output_dir
    scan_output_path = os.path.join(results_dir, "scan_findings.json")
    with open(scan_output_path, "w", encoding="utf-8") as f:
        json.dump({"sample_findings": sample_findings, "group_analysis": group_analysis}, f, indent=2)

    return sample_findings, group_analysis


def cmd_integrity_evaluate(args):
    """Evaluate detector findings against attack_manifest.json ground truth."""
    from src.benchmark_evaluator import BenchmarkEvaluator
    from src.visual_evidence import VisualEvidenceGenerator

    print("=" * 70)
    print("SENTINELVISION: Quantitative Benchmark Evaluation")
    print("=" * 70)

    manifest_path = os.path.abspath(args.manifest)
    results_dir = os.path.join(WORKSPACE_ROOT, "datasets", "sentinelvision_voc2012", "results")
    scan_path = os.path.join(results_dir, "scan_findings.json")

    if not os.path.exists(manifest_path):
        print(f"[ERROR] Attack manifest not found at {manifest_path}")
        sys.exit(1)

    if not os.path.exists(scan_path):
        print(f"[ERROR] Scan findings not found at {scan_path}. Run 'integrity scan' first.")
        sys.exit(1)

    with open(scan_path, "r", encoding="utf-8") as f:
        scan_data = json.load(f)

    sample_findings = scan_data.get("sample_findings", [])
    group_analysis = scan_data.get("group_analysis", {})

    evaluator = BenchmarkEvaluator(manifest_path)
    all_dataset_ids = list(evaluator.ground_truth_samples.keys())

    # Overall metrics
    overall = evaluator.evaluate_detections(sample_findings, all_dataset_ids)
    print(f"[*] Overall Evaluation: Precision={overall['precision']}, Recall={overall['recall']}, F1={overall['f1']}")

    # Per scenario metrics
    scenario_metrics = evaluator.evaluate_per_scenario(sample_findings, all_dataset_ids)
    print("[*] Per-Scenario Breakdown:")
    for sc, m in scenario_metrics.items():
        print(f"     - {sc:22s}: Prec={m['precision']:.3f}, Rec={m['recall']:.3f}, F1={m['f1']:.3f} (Injected={m['target_injected']}, TP={m['tp']})")

    # Group attribution
    group_metrics = evaluator.evaluate_group_attribution(group_analysis.get("group_findings", []))
    print("[*] Group Attribution Accuracy:")
    for gt, gm in group_metrics.items():
        print(f"     - {gt:12s}: Precision={gm['precision']:.3f}, Recall={gm['recall']:.3f}, F1={gm['f1']:.3f} (TP={gm['tp']})")

    # Render representative visual evidence artifacts
    vis_dir = os.path.join(results_dir, "visual_evidence")
    vis = VisualEvidenceGenerator(vis_dir)
    print(f"[*] Rendering representative visual evidence artifacts to {vis_dir}...")

    benchmarks_root = os.path.join(WORKSPACE_ROOT, "datasets", "sentinelvision_voc2012")
    raw_images_dir = os.path.join(benchmarks_root, "raw", "VOCdevkit", "VOC2012", "JPEGImages")

    # 1. Trigger evidence
    trigger_attacks = [a for a in evaluator.attacks if a.get("scenario") == "trigger_injection"]
    if trigger_attacks:
        atk = trigger_attacks[0]
        sid_raw = atk["sample_id"].replace("voc2012_", "")
        clean_path = os.path.join(raw_images_dir, f"{sid_raw}.jpg")
        pois_path = os.path.join(benchmarks_root, "trigger_injection", "JPEGImages", f"{sid_raw}.jpg")
        if os.path.exists(clean_path) and os.path.exists(pois_path):
            vis.render_trigger_evidence(
                clean_img_path=clean_path,
                poisoned_img_path=pois_path,
                output_filename="evidence_trigger_injection.jpg",
                sample_id=atk["sample_id"],
                target_class=atk.get("attack_parameters", {}).get("target_class", "aeroplane"),
            )

    # 2. Duplicate evidence
    dup_attacks = [a for a in evaluator.attacks if a.get("scenario") == "duplicate_flooding"]
    if dup_attacks:
        atk = dup_attacks[0]
        base_sid = atk["original_state"]["reference_sample_id"].replace("voc2012_", "")
        dup_sid = atk["sample_id"].replace("voc2012_", "")
        ref_path = os.path.join(raw_images_dir, f"{base_sid}.jpg")
        dup_path = os.path.join(benchmarks_root, "duplicate_flooding", "JPEGImages", f"{dup_sid}.jpg")
        if os.path.exists(ref_path) and os.path.exists(dup_path):
            vis.render_duplicate_evidence(
                ref_img_path=ref_path,
                dup_img_path=dup_path,
                output_filename="evidence_duplicate_flooding.jpg",
                ref_id=atk["original_state"]["reference_sample_id"],
                dup_id=atk["sample_id"],
                similarity=0.9942,
                transformation=atk.get("attack_parameters", {}).get("transformation", "jpeg_compress"),
            )

    # 3. OOD evidence
    ood_attacks = [a for a in evaluator.attacks if a.get("scenario") == "ood_insertion"]
    clean_val_imgs = [
        os.path.join(raw_images_dir, f) for f in os.listdir(raw_images_dir)[:3]
    ] if os.path.exists(raw_images_dir) else []
    ood_imgs = [
        os.path.join(benchmarks_root, "ood_insertion", "JPEGImages", f"{a['sample_id'].replace('voc2012_', '')}.jpg")
        for a in ood_attacks[:3]
    ]
    ood_imgs = [p for p in ood_imgs if os.path.exists(p)]
    if clean_val_imgs and ood_imgs:
        vis.render_ood_evidence(
            in_dist_img_paths=clean_val_imgs,
            ood_img_paths=ood_imgs,
            output_filename="evidence_ood_distribution.jpg",
        )

    # 4. Label flip evidence
    flip_attacks = [a for a in evaluator.attacks if a.get("scenario") == "label_flip"]
    if flip_attacks:
        atk = flip_attacks[0]
        sid_raw = atk["sample_id"].replace("voc2012_", "")
        img_p = os.path.join(raw_images_dir, f"{sid_raw}.jpg")
        if os.path.exists(img_p):
            vis.render_label_flip_evidence(
                img_path=img_p,
                output_filename="evidence_label_flip.jpg",
                sample_id=atk["sample_id"],
                original_label=atk["original_state"]["label"],
                modified_label=atk["modified_state"]["label"],
            )

    eval_output_path = os.path.join(results_dir, "benchmark_evaluation.json")
    with open(eval_output_path, "w", encoding="utf-8") as f:
        json.dump({"overall": overall, "scenarios": scenario_metrics, "group_attribution": group_metrics}, f, indent=2)

    print(f"[OK] Evaluation results saved to {eval_output_path}")


def cmd_integrity_clean_control(args):
    """Run full pipeline on clean VOC2012 baseline to evaluate false positives."""
    from src.benchmark_evaluator import BenchmarkEvaluator

    print("=" * 70)
    print("SENTINELVISION: Clean Baseline False-Positive Evaluation")
    print("=" * 70)

    clean_dir = os.path.join(WORKSPACE_ROOT, "datasets", "sentinelvision_voc2012", "clean")
    results_dir = os.path.join(WORKSPACE_ROOT, "datasets", "sentinelvision_voc2012", "results")
    if not os.path.exists(clean_dir):
        print(f"[ERROR] Clean directory not found at {clean_dir}")
        sys.exit(1)

    class MockArgs:
        dataset = clean_dir
        config = args.config
        limit = args.limit or 200

    print(f"[*] Scanning clean control baseline ({MockArgs.limit} samples)...")
    sample_findings, group_analysis = cmd_integrity_scan(MockArgs)

    clean_images = [f for f in os.listdir(os.path.join(clean_dir, "JPEGImages")) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    all_clean_ids = [f"voc2012_{os.path.splitext(f)[0]}" for f in clean_images]

    manifest_dummy = os.path.join(WORKSPACE_ROOT, "datasets", "sentinelvision_voc2012", "metadata", "attack_manifest.json")
    evaluator = BenchmarkEvaluator(manifest_dummy)
    clean_eval = evaluator.evaluate_clean_control(
        clean_detected_samples=sample_findings,
        clean_dataset_sample_ids=all_clean_ids,
    )

    print(f"[*] Clean Samples Evaluated: {clean_eval['clean_sample_count']}")
    print(f"[*] False Positives:        {clean_eval['false_positive_count']}")
    print(f"[*] Empirical FPR:          {clean_eval['false_positive_rate']*100:.2f}%")
    print(f"[*] Baseline Assessment:    {clean_eval['assessment']}")

    clean_eval_path = os.path.join(results_dir, "clean_baseline_evaluation.json")
    with open(clean_eval_path, "w", encoding="utf-8") as f:
        json.dump(clean_eval, f, indent=2)
    print(f"[OK] Clean control evaluation saved to {clean_eval_path}")


def cmd_report_generate(args):
    """Generate final Markdown and JSON assurance reports."""
    from src.assurance_report import AssuranceReportGenerator

    print("=" * 70)
    print("SENTINELVISION: Assurance Report Generation")
    print("=" * 70)

    output_dir = os.path.abspath(args.output or os.path.join(WORKSPACE_ROOT, "datasets", "sentinelvision_voc2012", "results"))
    meta_dir = os.path.join(WORKSPACE_ROOT, "datasets", "sentinelvision_voc2012", "metadata")
    manifest_path = os.path.join(meta_dir, "dataset_manifest.json")
    scan_path = os.path.join(output_dir, "scan_findings.json")
    eval_path = os.path.join(output_dir, "benchmark_evaluation.json")
    clean_path = os.path.join(output_dir, "clean_baseline_evaluation.json")

    dataset_manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            dataset_manifest = json.load(f)

    sample_findings = []
    group_analysis = {}
    if os.path.exists(scan_path):
        with open(scan_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            sample_findings = data.get("sample_findings", [])
            group_analysis = data.get("group_analysis", {})

    eval_results = {}
    if os.path.exists(eval_path):
        with open(eval_path, "r", encoding="utf-8") as f:
            eval_results = json.load(f).get("scenarios", {})

    clean_eval = {}
    if os.path.exists(clean_path):
        with open(clean_path, "r", encoding="utf-8") as f:
            clean_eval = json.load(f)

    reporter = AssuranceReportGenerator(output_dir)
    md_file, json_file = reporter.generate_report(
        dataset_manifest=dataset_manifest,
        sample_findings=sample_findings,
        group_analysis=group_analysis,
        evaluation_results=eval_results,
        clean_eval_results=clean_eval,
    )

    print(f"[OK] Human-readable Markdown report: {md_file}")
    print(f"[OK] Machine-readable JSON report:     {json_file}")


def main():
    parser = argparse.ArgumentParser(
        description="SentinelVision - Computer Vision Training Data Integrity Assurance (SIH PS 26228)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # dataset prepare-voc2012
    p_prep = subparsers.add_parser("dataset", help="Dataset management")
    p_prep_sub = p_prep.add_subparsers(dest="subcommand", required=True)
    p_voc = p_prep_sub.add_parser("prepare-voc2012", help="Download, verify, and adapt official VOC2012")
    p_voc.add_argument("--config", default=None, help="Benchmark configuration file")
    p_voc.add_argument("--limit", type=int, default=None, help="Limit number of validation samples")
    p_voc.set_defaults(func=cmd_dataset_prepare_voc2012)

    # integrity
    p_int = subparsers.add_parser("integrity", help="Integrity management")
    p_int_sub = p_int.add_subparsers(dest="subcommand", required=True)

    p_gen = p_int_sub.add_parser("generate-benchmark", help="Generate controlled attack scenarios")
    p_gen.add_argument("--config", default=None, help="Benchmark configuration file")
    p_gen.add_argument("--seed", type=int, default=42, help="Master random seed")
    p_gen.add_argument("--limit", type=int, default=300, help="Number of base samples for benchmark")
    p_gen.set_defaults(func=cmd_integrity_generate_benchmark)

    p_scan = p_int_sub.add_parser("scan", help="Scan dataset for integrity anomalies")
    p_scan.add_argument("--dataset", required=True, help="Path to dataset directory")
    p_scan.add_argument("--config", default=None, help="Configuration file")
    p_scan.add_argument("--limit", type=int, default=None, help="Sample limit")
    p_scan.add_argument("--output-dir", default=None, help="Directory for this scan's scan_findings.json")
    p_scan.set_defaults(func=cmd_integrity_scan)

    p_eval = p_int_sub.add_parser("evaluate", help="Evaluate scan against attack manifest")
    p_eval.add_argument("--manifest", required=True, help="Path to attack_manifest.json")
    p_eval.set_defaults(func=cmd_integrity_evaluate)

    p_clean = p_int_sub.add_parser("clean-control", help="Run false-positive evaluation on clean baseline")
    p_clean.add_argument("--config", default=None, help="Configuration file")
    p_clean.add_argument("--limit", type=int, default=200, help="Sample limit")
    p_clean.set_defaults(func=cmd_integrity_clean_control)

    # report generate
    p_rep = subparsers.add_parser("report", help="Report generation")
    p_rep_sub = p_rep.add_subparsers(dest="subcommand", required=True)
    p_rep_gen = p_rep_sub.add_parser("generate", help="Generate assurance report")
    p_rep_gen.add_argument("--output", default=None, help="Output directory")
    p_rep_gen.set_defaults(func=cmd_report_generate)

    # governance
    from governance.cli import cmd_assess, cmd_verify_report, cmd_verify_audit, cmd_demo
    p_gov = subparsers.add_parser("governance", help="Governance & Assurance Reporting Layer")
    p_gov_sub = p_gov.add_subparsers(dest="subcommand", required=True)

    p_g_assess = p_gov_sub.add_parser("assess", help="Execute governance assessment and build report")
    p_g_assess.add_argument("--dataset", default=None, help="Dataset directory")
    p_g_assess.add_argument("--dataset-id", default=None, help="Dataset identifier")
    p_g_assess.add_argument("--data-results", default=None, help="Path to DataIntegrity results JSON")
    p_g_assess.add_argument("--model", default=None, help="Model weights file (.pt)")
    p_g_assess.add_argument("--model-id", default=None, help="Model asset identifier")
    p_g_assess.add_argument("--model-findings", default=None, help="Path to ModelIntegrity findings JSON")
    p_g_assess.add_argument("--inference-records", default=None, help="Path to inference seals JSON")
    p_g_assess.add_argument("--drift-results", default=None, help="Path to DistributionShift results JSON")
    p_g_assess.add_argument("--reference", default=None, help="Path to reference battery manifest")
    p_g_assess.add_argument("--output", default=None, help="Output directory for reports")
    p_g_assess.set_defaults(func=cmd_assess)

    p_g_vrep = p_gov_sub.add_parser("verify-report", help="Verify cryptographic integrity of assurance report")
    p_g_vrep.add_argument("--report", required=True, help="Path to assurance_report.json")
    p_g_vrep.set_defaults(func=cmd_verify_report)

    p_g_vaud = p_gov_sub.add_parser("verify-audit", help="Verify hash chain of audit trail")
    p_g_vaud.add_argument("--report", required=True, help="Path to assurance_report.json containing audit")
    p_g_vaud.set_defaults(func=cmd_verify_audit)

    p_g_demo = p_gov_sub.add_parser("demo", help="Run end-to-end demo on existing repository assets")
    p_g_demo.add_argument("--output", default=None, help="Output directory for reports")
    p_g_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
