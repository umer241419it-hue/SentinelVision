"""
Tests for Report Generation, Tamper-Evident Hashing, and Cryptographic Verification.
"""

import json
from pathlib import Path
from governance.engine import GovernanceEngine
from governance.report import AssuranceReportGenerator
from governance.verifier import AssuranceReportVerifier


def test_report_generation_and_verification_cycle(tmp_path):
    engine = GovernanceEngine()
    engine.register_dataset_asset("voc2012-eval", "VOC2012", 120)
    engine.record_unassessed_capability("MODEL_INTEGRITY", "Model Inversion", "Omitted in test", "weights")
    report = engine.assemble_report()

    generator = AssuranceReportGenerator(tmp_path)
    json_path, md_path, html_path = generator.generate(report, sign_report=True)

    # 1. Check generated files exist and are non-empty
    assert json_path.is_file() and json_path.stat().st_size > 0
    assert md_path.is_file() and md_path.stat().st_size > 0
    assert html_path.is_file() and html_path.stat().st_size > 0

    # 2. Check report content
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "report_integrity" in data
    assert data["report_integrity"]["report_hash"]
    assert data["report_integrity"]["signer"] == "GovernanceEngine"

    # 3. Independent verification should SUCCEED
    verifier = AssuranceReportVerifier()
    res = verifier.verify_report(json_path)
    assert res["verdict"] == "VALID"
    assert res["report_hash_valid"] is True
    assert res["signature_valid"] is True
    assert res["audit_chain_valid"] is True


def test_tampered_report_verification_fails(tmp_path):
    engine = GovernanceEngine()
    report = engine.assemble_report()

    generator = AssuranceReportGenerator(tmp_path)
    json_path, _, _ = generator.generate(report, sign_report=True)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Tamper with summary in overall_assessment
    data["overall_assessment"]["summary"] = "MALICIOUSLY_ALTERED_SUMMARY"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Verification must catch the tamper
    verifier = AssuranceReportVerifier()
    res = verifier.verify_report(json_path)
    assert res["verdict"] == "TAMPERED"
    assert res["report_hash_valid"] is False
    assert any("hash mismatch" in issue for issue in res["issues"])
