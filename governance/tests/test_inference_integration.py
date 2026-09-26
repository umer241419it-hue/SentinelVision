"""
Tests for Inference Provenance integration into Governance Layer.
Validates:
- Valid seal verification -> PASS / ACCEPT
- Modified input tensor -> FAIL / QUARANTINE
- Modified output summary -> FAIL / QUARANTINE
- Wrong model digest -> FAIL / QUARANTINE
- Nonce reuse / replay detection
"""

import copy
import pytest
from governance.engine import GovernanceEngine
from governance.schema import FindingStatus, GovernanceDisposition, SeverityLevel


def test_valid_inference_seal_integration(sample_valid_seal):
    engine = GovernanceEngine()
    engine.ingest_and_verify_inference_seals([sample_valid_seal])
    report = engine.assemble_report()

    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.status == FindingStatus.PASS.value
    assert finding.severity == SeverityLevel.LOW.value
    assert finding.recommendation.disposition == GovernanceDisposition.ACCEPT.value


def test_modified_input_inference_seal_quarantine(sample_valid_seal):
    tampered_seal = copy.deepcopy(sample_valid_seal)
    # Flip first character of inputHash
    original_hash = tampered_seal["inputHash"]
    new_char = "0" if original_hash[0] != "0" else "1"
    tampered_seal["inputHash"] = new_char + original_hash[1:]

    engine = GovernanceEngine()
    engine.ingest_and_verify_inference_seals([tampered_seal])
    report = engine.assemble_report()

    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.status == FindingStatus.FAIL.value
    assert finding.severity == SeverityLevel.CRITICAL.value
    assert finding.recommendation.disposition == GovernanceDisposition.QUARANTINE.value
    assert "Integrity violation" in finding.description
    assert report.overall_assessment.disposition == GovernanceDisposition.QUARANTINE.value


def test_modified_output_inference_seal_quarantine(sample_valid_seal):
    tampered_seal = copy.deepcopy(sample_valid_seal)
    # Alter predicted output
    tampered_seal["outputSummary"] = {"confidence": 0.12, "predicted_class": 99}

    engine = GovernanceEngine()
    engine.ingest_and_verify_inference_seals([tampered_seal])
    report = engine.assemble_report()

    finding = report.findings[0]
    assert finding.status == FindingStatus.FAIL.value
    assert finding.recommendation.disposition == GovernanceDisposition.QUARANTINE.value


def test_wrong_model_digest_quarantine(sample_valid_seal):
    engine = GovernanceEngine()
    # Expect a different model digest
    expected_digest = "e" * 64
    engine.ingest_and_verify_inference_seals([sample_valid_seal], expected_model_digest=expected_digest)
    report = engine.assemble_report()

    finding = report.findings[0]
    assert finding.status == FindingStatus.FAIL.value
    assert finding.recommendation.disposition == GovernanceDisposition.QUARANTINE.value
    assert "Model digest substitution" in finding.description


def test_inference_seal_nonce_replay_detection(sample_valid_seal):
    replayed_seal = copy.deepcopy(sample_valid_seal)
    replayed_seal["sealID"] = "seal-replayed-002"

    engine = GovernanceEngine()
    # Ingest two seals with the same nonce
    engine.ingest_and_verify_inference_seals([sample_valid_seal, replayed_seal])

    # Check check_record parameters
    inf_check = next(c for c in engine.checks if c.category == "INFERENCE_PROVENANCE")
    assert inf_check.parameters.get("replay_detected") is True
