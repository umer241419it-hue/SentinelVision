"""
SentinelVision - Governance & Assurance Reporting CLI.

Commands:
    cv-assurance assess            Run/aggregate integrity assessments and generate reports
    cv-assurance verify-report     Verify cryptographic signature, content hash, and audit chain
    cv-assurance verify-audit      Verify SHA-256 audit chain of an assessment
    cv-assurance demo              Execute end-to-end demo assessment on existing assets
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Optional

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in [WORKSPACE_ROOT, os.path.join(WORKSPACE_ROOT, "crypto-utils")]:
    if p not in sys.path:
        sys.path.insert(0, p)

from governance.engine import GovernanceEngine
from governance.report import AssuranceReportGenerator
from governance.verifier import AssuranceReportVerifier


def cmd_assess(args):
    """Run/aggregate assessments across assets and compile Assurance Report."""
    print("=" * 75)
    print("SENTINELVISION: Governance & Assurance Reporting Assessment")
    print("=" * 75)

    engine = GovernanceEngine()
    output_dir = Path(args.output or os.path.join(WORKSPACE_ROOT, "reports"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # 0. Contributor / Vendor
    if getattr(args, "contributor_id", None):
        engine.register_contributor(
            contributor_id=args.contributor_id,
            name=getattr(args, "contributor_name", None) or args.contributor_id,
        )

    # 1. Dataset / Data Integrity
    if args.data_results and os.path.exists(args.data_results):
        print(f"[*] Ingesting Training Data Integrity findings from: {args.data_results}")
        engine.ingest_data_integrity_results(args.data_results)
        engine.register_dataset_asset(
            dataset_id=args.dataset_id or "dataset-voc2012-eval",
            name="PASCAL VOC2012 Benchmark Subset",
            sample_count=120,
        )
    elif args.dataset and os.path.exists(args.dataset):
        print(f"[*] Dataset provided at: {args.dataset}")
        engine.register_dataset_asset(
            dataset_id=args.dataset_id or "dataset-custom",
            name=os.path.basename(args.dataset),
            sample_count=0,
        )
        engine.record_unassessed_capability(
            category="DATA_INTEGRITY",
            capability_name="Data Integrity Scan",
            reason="Raw dataset provided without precomputed results; full detector scan required.",
            required_access="Precomputed embeddings cache and labels",
        )
    else:
        engine.record_unassessed_capability(
            category="DATA_INTEGRITY",
            capability_name="Training Data Integrity",
            reason="No training dataset or data integrity scan results were provided for assessment.",
            required_access="Dataset images and annotations",
        )

    # 2. Model Integrity
    if args.model_findings and os.path.exists(args.model_findings):
        print(f"[*] Ingesting Model Integrity findings from: {args.model_findings}")
        engine.ingest_model_integrity_results(args.model_findings)
        engine.register_model_asset(
            model_id=args.model_id or "model-trojai-eval",
            architecture="ResNet50/DenseNet121",
            digest="cd88076498c5c79fce68bffef38102f3394ef5c9f6691dc2f0efc48bf51f3e0b",
            access_level="white-box",
        )
    elif args.model and os.path.exists(args.model):
        print(f"[*] Model weights provided at: {args.model}")
        engine.register_model_asset(
            model_id=args.model_id or "model-custom",
            architecture="PyTorch Model",
            digest="sha256:custom",
            weights_path=args.model,
            access_level="white-box",
        )
    else:
        engine.record_unassessed_capability(
            category="MODEL_INTEGRITY",
            capability_name="Model Trojan & Backdoor Inversion",
            reason="No model weights or model integrity scan findings were provided for assessment.",
            required_access="White-box model weights (.pt)",
        )

    # 3. Inference Provenance Seals
    if args.inference_records and os.path.exists(args.inference_records):
        print(f"[*] Ingesting and verifying Inference Provenance records from: {args.inference_records}")
        engine.ingest_and_verify_inference_seals(args.inference_records)
    else:
        engine.record_unassessed_capability(
            category="INFERENCE_PROVENANCE",
            capability_name="Inference Output Sealing & Provenance",
            reason="No sealed inference records were provided for verification.",
            required_access="Sealed inference JSON records",
        )

    # 4. Distribution Drift
    if args.drift_results and os.path.exists(args.drift_results):
        print(f"[*] Ingesting Distribution Drift results from: {args.drift_results}")
        engine.ingest_drift_results(args.drift_results)
    else:
        engine.record_unassessed_capability(
            category="DISTRIBUTION_SHIFT",
            capability_name="Distribution Shift & Drift Monitoring",
            reason="No reference battery or drift monitoring results were provided for assessment.",
            required_access="Reference battery embeddings and live window data",
        )

    # 5. Assemble & Generate Report
    print("[*] Assembling Canonical Assurance Report...")
    report = engine.assemble_report()
    generator = AssuranceReportGenerator(output_dir)
    json_path, md_path, html_path = generator.generate(report, sign_report=True)

    oa = report.overall_assessment
    print("\n" + "=" * 75)
    print(f"ASSESSMENT STATUS: {oa.overall_status}")
    print(f"RECOMMENDED DISPOSITION: {oa.disposition}")
    print(f"Summary: {oa.summary}")
    print("=" * 75)
    print(f"[OK] Machine-readable JSON: {json_path}")
    print(f"[OK] Analyst Markdown:      {md_path}")
    print(f"[OK] Interactive HTML:      {html_path}\n")

    return report


def cmd_verify_report(args):
    """Verify cryptographic authenticity of an assurance report."""
    print("=" * 75)
    print("SENTINELVISION: Assurance Report Verification")
    print("=" * 75)

    verifier = AssuranceReportVerifier()
    res = verifier.verify_report(args.report)

    print(f"Report Target:        {args.report}")
    print(f"Assessment ID:        {res.get('assessment_id')}")
    print(f"Verification Verdict: {res.get('verdict')}")
    print(f"Content Hash Valid:   {res.get('report_hash_valid')}")
    print(f"Signature Valid:      {res.get('signature_valid')}")
    print(f"Audit Chain Valid:    {res.get('audit_chain_valid')}")
    print(f"Chained Events:       {res.get('event_count')}")

    if res.get("issues"):
        print("\n[WARNING] Verification Issues:")
        for iss in res["issues"]:
            print(f"  - {iss}")

    if res["verdict"] == "VALID":
        print("\n[SUCCESS] Report is authentic and untampered.")
        sys.exit(0)
    else:
        print("\n[FAILED] Report verification failed.")
        sys.exit(1)


def cmd_verify_audit(args):
    """Verify sequential hash chain of an audit trail."""
    print("=" * 75)
    print("SENTINELVISION: Audit Chain Verification")
    print("=" * 75)

    with open(args.report, "r", encoding="utf-8") as f:
        data = json.load(f)

    events = data.get("audit", {}).get("events", []) if "audit" in data else data
    verifier = AssuranceReportVerifier()
    res = verifier.verify_audit_trail_only(events)

    print(f"Audit Source:      {args.report}")
    print(f"Events Verified:   {res.get('event_count')}")
    print(f"Chain Integrity:   {res.get('verdict')}")

    if res.get("error"):
        print(f"Error Diagnostic:  {res.get('error')}")
        sys.exit(1)
    else:
        print("[SUCCESS] Audit chain is cryptographically intact.")
        sys.exit(0)


def cmd_demo(args):
    """Execute end-to-end demonstration using existing sample assets."""
    print("=" * 75)
    print("SENTINELVISION: End-to-End Governance Demonstration Run")
    print("=" * 75)

    # Locate existing repository assets
    data_results = os.path.join(WORKSPACE_ROOT, "data-integrity", "results", "integrity_results.json")
    model_findings = os.path.join(WORKSPACE_ROOT, "model-integrity", "findings.json")
    drift_results = os.path.join(WORKSPACE_ROOT, "drift-monitor", "results", "drift_results.json")
    seal_coverage = os.path.join(WORKSPACE_ROOT, "inference-provenance", "seal_coverage_results.json")

    # Load inference sample records from inference evidence store
    inf_store = os.path.join(WORKSPACE_ROOT, "inference-provenance", "evidence_store")
    sample_seals = []
    if os.path.exists(inf_store):
        for fname in os.listdir(inf_store):
            if fname.endswith(".json"):
                with open(os.path.join(inf_store, fname), "r", encoding="utf-8") as f:
                    sample_seals.append(json.load(f))

    from canonical import canonical_json
    from sign import sign_fields

    # Generate a fresh validly signed seal to test valid verification
    valid_seal_fields = {
        "sealID": "seal-demo-valid-001",
        "modelAssetID": "model-id-00000028",
        "inputHash": "f0252f29c40ffb13c7b4b8985d4b2b960f10d0755680249beb3ac33ea711c237",
        "modelDigest": "cd88076498c5c79fce68bffef38102f3394ef5c9f6691dc2f0efc48bf51f3e0b",
        "config": {"channel_order": "BGR", "device": "cpu"},
        "nonce": "1f340a714f4a0231da4865cb9ece14c0",
        "timestamp": "2026-09-22T11:19:10Z",
        "outputSummary": {"confidence": 1.0, "predicted_class": 0, "probabilities": [1.0, 0.0, 0.0, 0.0, 0.0]},
        "signerModule": "InferenceProvenance",
    }
    c_hash = hashlib.sha256(canonical_json(valid_seal_fields).encode("utf-8")).hexdigest()
    sig = sign_fields("InferenceProvenance", valid_seal_fields)
    valid_seal = dict(valid_seal_fields)
    valid_seal["contentHash"] = c_hash
    valid_seal["signature"] = sig
    sample_seals.append(valid_seal)

    # Also synthesize 1 tampered record to prove quarantine and tamper detection
    tampered_seal = dict(valid_seal)
    tampered_seal["sealID"] = "seal-tampered-demo-001"
    tampered_seal["modelDigest"] = "0" * 64  # deliberate substitution
    sample_seals.append(tampered_seal)

    tmp_seals_path = os.path.join(WORKSPACE_ROOT, "datasets", "temp_demo_seals.json")
    os.makedirs(os.path.dirname(tmp_seals_path), exist_ok=True)
    with open(tmp_seals_path, "w", encoding="utf-8") as f:
        json.dump(sample_seals, f, indent=2)

    demo_args = argparse.Namespace(
        data_results=data_results if os.path.exists(data_results) else None,
        dataset=None,
        dataset_id="voc2012-self-poisoned-eval",
        model_findings=model_findings if os.path.exists(model_findings) else None,
        model=None,
        model_id="trojai-round4-battery",
        inference_records=tmp_seals_path,
        drift_results=drift_results if os.path.exists(drift_results) else None,
        reference=None,
        output=args.output or os.path.join(WORKSPACE_ROOT, "reports", "demo_assessment"),
    )

    report = cmd_assess(demo_args)

    # Clean up temp demo seals
    if os.path.exists(tmp_seals_path):
        os.remove(tmp_seals_path)

    print("[SUCCESS] End-to-end governance demonstration complete.")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cv-assurance",
        description="SentinelVision - Governance & Assurance Reporting CLI (SIH PS 26228)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # assess
    p_assess = subparsers.add_parser("assess", help="Execute governance assessment and build report")
    p_assess.add_argument("--dataset", default=None, help="Dataset directory")
    p_assess.add_argument("--dataset-id", default=None, help="Dataset identifier")
    p_assess.add_argument("--data-results", default=None, help="Path to DataIntegrity results JSON")
    p_assess.add_argument("--model", default=None, help="Model weights file (.pt)")
    p_assess.add_argument("--model-id", default=None, help="Model asset identifier")
    p_assess.add_argument("--model-findings", default=None, help="Path to ModelIntegrity findings JSON")
    p_assess.add_argument("--inference-records", default=None, help="Path to inference seals JSON")
    p_assess.add_argument("--drift-results", default=None, help="Path to DistributionShift results JSON")
    p_assess.add_argument("--reference", default=None, help="Path to reference battery manifest")
    p_assess.add_argument("--contributor-id", default=None, help="Contributor / Vendor identifier")
    p_assess.add_argument("--contributor-name", default=None, help="Contributor / Vendor human-readable name")
    p_assess.add_argument("--output", default=None, help="Output directory for reports")
    p_assess.set_defaults(func=cmd_assess)

    # verify-report
    p_vrep = subparsers.add_parser("verify-report", help="Verify cryptographic integrity of assurance report")
    p_vrep.add_argument("--report", required=True, help="Path to assurance_report.json")
    p_vrep.set_defaults(func=cmd_verify_report)

    # verify-audit
    p_vaud = subparsers.add_parser("verify-audit", help="Verify hash chain of audit trail")
    p_vaud.add_argument("--report", required=True, help="Path to assurance_report.json containing audit")
    p_vaud.set_defaults(func=cmd_verify_audit)

    # demo
    p_demo = subparsers.add_parser("demo", help="Run end-to-end demo on existing repository assets")
    p_demo.add_argument("--output", default=None, help="Output directory for reports")
    p_demo.set_defaults(func=cmd_demo)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
