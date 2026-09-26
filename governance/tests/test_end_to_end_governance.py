"""
End-to-End integration test for complete multi-module Governance & Assurance workflow.
"""

import json
import os
from pathlib import Path
from governance.engine import GovernanceEngine
from governance.report import AssuranceReportGenerator
from governance.schema import GovernanceDisposition, OverallStatus
from governance.verifier import AssuranceReportVerifier

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_end_to_end_governance_workflow(tmp_path, sample_valid_seal):
    # 1. Initialize Engine
    engine = GovernanceEngine(environment="offline/air-gapped")

    # 2. Register Assets
    engine.register_dataset_asset(
        dataset_id="voc2012-benchmark-subset",
        name="PASCAL VOC2012",
        sample_count=120,
        hashes={"md5": "6cd6e144f989b92b3379bac3b3de84fd"},
    )
    engine.register_model_asset(
        model_id="trojai-id-00000028",
        architecture="ResNet50",
        digest="cd88076498c5c79fce68bffef38102f3394ef5c9f6691dc2f0efc48bf51f3e0b",
        access_level="white-box",
    )

    # 3. Ingest Data Integrity
    data_results_path = os.path.join(WORKSPACE_ROOT, "data-integrity", "results", "integrity_results.json")
    if os.path.exists(data_results_path):
        engine.ingest_data_integrity_results(data_results_path)

    # 4. Ingest Model Integrity
    model_findings_path = os.path.join(WORKSPACE_ROOT, "model-integrity", "findings.json")
    if os.path.exists(model_findings_path):
        engine.ingest_model_integrity_results(model_findings_path)

    # 5. Ingest Inference Provenance (valid seal)
    engine.ingest_and_verify_inference_seals([sample_valid_seal])

    # 6. Ingest Distribution Shift
    drift_results_path = os.path.join(WORKSPACE_ROOT, "drift-monitor", "results", "drift_results.json")
    if os.path.exists(drift_results_path):
        engine.ingest_drift_results(drift_results_path)

    # 7. Assemble Report
    report = engine.assemble_report()
    assert len(report.checks) >= 3
    assert len(report.findings) > 0

    # 8. Generate Reports (JSON, MD, HTML)
    generator = AssuranceReportGenerator(tmp_path)
    json_path, md_path, html_path = generator.generate(report, sign_report=True)

    assert json_path.exists()
    assert md_path.exists()
    assert html_path.exists()

    # 9. Verify Generated Report and Audit Chain
    verifier = AssuranceReportVerifier()
    res = verifier.verify_report(json_path)
    assert res["verdict"] == "VALID"
    assert res["report_hash_valid"] is True
    assert res["signature_valid"] is True
    assert res["audit_chain_valid"] is True
