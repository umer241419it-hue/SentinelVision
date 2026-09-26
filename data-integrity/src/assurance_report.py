"""
SentinelVision - Training Data Integrity Assurance Report Generator.

Compiles comprehensive human-readable Markdown and machine-readable JSON
assurance reports integrating:
- Dataset Overview (PASCAL VOC2012 baseline facts, splits, object statistics)
- Provenance Metadata Availability & Disclaimer (Synthetic benchmark provenance)
- Integrity Findings (Decoupled confidence & severity, evidence hashes, disposition)
- Group-Level Provenance Rollups (Contributor/Source/Batch systematic mislabelling & concentration)
- Quantitative Benchmark Evaluation (Precision, Recall, F1, FPR, FNR across all attack scenarios)
- Clean Baseline False-Positive Evaluation
- Concrete Limitations and SIH Requirement Coverage
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple


class AssuranceReportGenerator:
    """
    Generates structured Markdown and JSON assurance reports.
    """

    def __init__(self, output_dir: str):
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_report(
        self,
        dataset_manifest: Dict[str, Any],
        sample_findings: List[Dict[str, Any]],
        group_analysis: Dict[str, Any],
        evaluation_results: Optional[Dict[str, Any]] = None,
        clean_eval_results: Optional[Dict[str, Any]] = None,
        report_title: str = "SentinelVision Training Data Integrity Assurance Report",
    ) -> Tuple[str, str]:
        """
        Generate both Markdown and JSON reports.

        Returns:
            Tuple of (markdown_file_path, json_file_path).
        """
        report_data = {
            "title": report_title,
            "version": "1.0.0",
            "dataset_overview": dataset_manifest,
            "summary_metrics": {
                "total_samples": dataset_manifest.get("image_count", 0),
                "total_flagged_samples": len(sample_findings),
                "anomaly_rate": round(
                    len(sample_findings) / max(1, dataset_manifest.get("image_count", 1)), 4
                ),
                "group_findings_count": len(group_analysis.get("group_findings", [])),
            },
            "findings": sample_findings,
            "group_analysis": group_analysis,
            "benchmark_evaluation": evaluation_results or {},
            "clean_baseline_evaluation": clean_eval_results or {},
        }

        # 1. Write JSON report
        json_path = os.path.join(self.output_dir, "training_data_integrity_report.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)

        # 2. Build Markdown report
        md_lines = []
        md_lines.append(f"# {report_title}\n")
        md_lines.append("> **SIH Problem Statement 26228**: Trustworthy Computer Vision Integrity Assurance for Data, Models and Inference Outputs in Multi-Contributor Pipelines\n")

        # Section 1: Executive Summary
        md_lines.append("## 1. Executive Summary\n")
        md_lines.append(f"- **Evaluated Dataset**: {dataset_manifest.get('dataset_name', 'PASCAL VOC2012')} ({dataset_manifest.get('dataset_version', '2012')})")
        md_lines.append(f"- **Source Reference**: `{dataset_manifest.get('source_url', 'Official Oxford/VGG VOC2012')}`")
        md_lines.append(f"- **Total Dataset Samples**: {dataset_manifest.get('image_count', 0):,}")
        md_lines.append(f"- **Total Flagged Samples**: {len(sample_findings):,} ({report_data['summary_metrics']['anomaly_rate']*100:.2f}%)")
        md_lines.append(f"- **Systematic Group Findings**: {len(group_analysis.get('group_findings', []))}")
        md_lines.append("- **Operation Mode**: 100% Offline / Air-Gapped Reproducible Execution\n")

        # Section 2: Dataset Facts
        md_lines.append("## 2. Dataset Overview & Benchmark Lineage\n")
        md_lines.append("| Metric | Value |")
        md_lines.append("| :--- | :--- |")
        md_lines.append(f"| **Dataset ID** | `{dataset_manifest.get('dataset_id', 'VOC2012')}` |")
        md_lines.append(f"| **Archive Hash (MD5)** | `{dataset_manifest.get('archive_md5', '6cd6e144f989b92b3379bac3b3de84fd')}` |")
        md_lines.append(f"| **Archive Hash (SHA-1)** | `{dataset_manifest.get('archive_sha1', '4e443f8a2eca6b1dac8a6c57641b67dd40621a49')}` |")
        md_lines.append(f"| **Dataset Content Hash** | `{dataset_manifest.get('dataset_hash', 'N/A')[:24]}...` |")
        md_lines.append(f"| **Total Annotated Objects** | {dataset_manifest.get('object_count', 0):,} |")
        md_lines.append(f"| **Standard Classes** | {len(dataset_manifest.get('class_distribution', {}))} classes (aeroplane .. tvmonitor) |")

        split_dist = dataset_manifest.get("split_distribution", {})
        splits_str = ", ".join(f"{k}: {v}" for k, v in split_dist.items()) if split_dist else "Standard VOC train/val"
        md_lines.append(f"| **Split Distribution** | {splits_str} |")
        md_lines.append("")

        md_lines.append("> [!NOTE]")
        md_lines.append("> **Synthetic Provenance Disclaimer**: PASCAL VOC2012 does not provide multi-contributor pipeline metadata. Contributor, source, and batch IDs were deterministically synthesized by SentinelVision specifically for multi-contributor integrity evaluation, as required by SIH PS 26228.\n")

        # Section 3: Benchmark Performance Matrix
        if evaluation_results:
            md_lines.append("## 3. Quantitative Attack Benchmark Evaluation\n")
            md_lines.append("Ground truth evaluated strictly against `attack_manifest.json`:\n")
            md_lines.append("| Attack Scenario | Target Injected | Total Detected | True Positives (TP) | False Positives (FP) | Precision | Recall | F1 Score | FPR |")
            md_lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

            for scen, metrics in evaluation_results.items():
                if isinstance(metrics, dict) and "f1" in metrics:
                    md_lines.append(
                        f"| **{scen}** | {metrics.get('target_injected', metrics.get('tp', 0)+metrics.get('fn', 0))} | "
                        f"{metrics.get('total_detected', metrics.get('tp', 0)+metrics.get('fp', 0))} | "
                        f"{metrics.get('tp', 0)} | {metrics.get('fp', 0)} | "
                        f"{metrics.get('precision', 0.0):.4f} | {metrics.get('recall', 0.0):.4f} | "
                        f"{metrics.get('f1', 0.0):.4f} | {metrics.get('fpr', 0.0):.4f} |"
                    )
            md_lines.append("")

        # Section 4: Clean Baseline Control
        if clean_eval_results:
            md_lines.append("## 4. Clean Control Baseline (False-Positive Analysis)\n")
            md_lines.append(f"- **Clean Samples Evaluated**: {clean_eval_results.get('clean_sample_count', 0)}")
            md_lines.append(f"- **Clean False Positives**: {clean_eval_results.get('false_positive_count', 0)}")
            md_lines.append(f"- **Empirical False Positive Rate (FPR)**: `{clean_eval_results.get('false_positive_rate', 0.0)*100:.2f}%`")
            md_lines.append(f"- **Control Assessment**: `{clean_eval_results.get('assessment', 'ACCEPTABLE')}`\n")
            if clean_eval_results.get("false_positives_by_detector"):
                md_lines.append("Breakdown by detector on clean baseline:")
                for det, cnt in clean_eval_results["false_positives_by_detector"].items():
                    md_lines.append(f"- `{det}`: {cnt} flags")
                md_lines.append("")

        # Section 5: Group-Level Provenance & Systematic Mislabelling
        md_lines.append("## 5. Provenance & Systematic Mislabelling Analysis\n")
        group_findings = group_analysis.get("group_findings", [])
        if group_findings:
            md_lines.append("| Group Type | Group ID | Affected Samples | Fraction | Dominant Confusion | Confidence | Severity | Disposition |")
            md_lines.append("| :--- | :--- | :---: | :---: | :--- | :---: | :---: | :---: |")
            for gf in group_findings[:15]:
                md_lines.append(
                    f"| {gf['group_type']} | `{gf['group_id']}` | {gf['affected_samples']} / {gf['total_samples']} | "
                    f"{gf['affected_fraction']*100:.1f}% | {gf.get('dominant_confusion') or 'N/A'} | "
                    f"{gf['confidence']:.2f} | **{gf['severity']}** | `{gf['disposition']}` |"
                )
            md_lines.append("")
        else:
            md_lines.append("No anomalous groups detected at current thresholds.\n")

        limitations = group_analysis.get("limitations", [])
        if limitations:
            md_lines.append("> [!IMPORTANT]")
            md_lines.append("> **Provenance Limitations**:")
            for lim in limitations:
                md_lines.append(f"> - {lim}")
            md_lines.append("")

        # Section 6: Findings Sample
        md_lines.append("## 6. Sample-Level Integrity Findings (Top Priority)\n")
        if sample_findings:
            md_lines.append("| Finding ID / Asset | Anomaly Flags | Confidence | Severity | Disposition | Reason / Evidence |")
            md_lines.append("| :--- | :--- | :---: | :---: | :---: | :--- |")
            for f in sample_findings[:20]:
                sid = f.get("assetID") or f.get("sample_id", "unknown")
                flags_str = ", ".join(f.get("flags", [])) if isinstance(f.get("flags"), list) else f.get("reason", "N/A")
                reason = f.get("reason", "")
                if len(reason) > 75:
                    reason = reason[:72] + "..."
                md_lines.append(
                    f"| `{sid}` | {flags_str} | {float(f.get('confidence', 0)):.2f} | "
                    f"**{f.get('severity', 'LOW')}** | `{f.get('disposition', 'REVIEW')}` | {reason} |"
                )
            md_lines.append("")
        else:
            md_lines.append("No sample-level findings generated.\n")

        # Section 7: Technical Limitations
        md_lines.append("## 7. Known Technical Limitations\n")
        md_lines.append("1. **Trigger Generalization**: Patch detector assumes localized, spatially-consistent residual triggers with cross-sample template correlation. Distributed frequency-domain watermarks (e.g. Wanet or blending at <1% opacity) require model-inversion or spectral inspection.")
        md_lines.append("2. **Semantic Cosine Duplicate Scope**: Duplicate detection flags high cosine similarity in standardized feature space; subtle semantic transformations (heavy rotations > 90 degrees or heavy occlusion) may fall below threshold.")
        md_lines.append("3. **OOD Attribution vs Malice**: Mahalanobis distance flags statistical distribution shift, not intent. An OOD finding indicates anomalous input domain requiring human triage rather than confirmed sabotage.")
        md_lines.append("4. **Provenance Availability**: Group-level attribution strictly requires ingestion of pipeline metadata. If multi-contributor provenance is omitted, sample-level detection continues but group attribution is unavailable.")

        md_path = os.path.join(self.output_dir, "training_data_integrity_report.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        return md_path, json_path
