"""
Tests for Confidence Scoring and Analyst Disposition Engine.
"""

from governance.confidence import build_confidence_assessment, interpret_confidence_value
from governance.disposition import determine_disposition
from governance.schema import (
    FindingCategory,
    FindingStatus,
    GovernanceDisposition,
    SeverityLevel,
)


def test_confidence_interpretations():
    assert interpret_confidence_value(0.95) == "HIGH"
    assert interpret_confidence_value(0.80) == "HIGH"
    assert interpret_confidence_value(0.79) == "MEDIUM"
    assert interpret_confidence_value(0.50) == "MEDIUM"
    assert interpret_confidence_value(0.49) == "LOW"
    assert interpret_confidence_value("UNKNOWN") == "UNKNOWN"
    assert interpret_confidence_value(None) == "UNKNOWN"


def test_confidence_assessment_structure():
    conf = build_confidence_assessment(
        value=0.88,
        basis=["Corroborated by STRIP", "MAD index exceeds threshold"],
        limitations=["Only evaluated on patch triggers"],
    )
    d = conf.to_dict()
    assert d["value"] == 0.88
    assert d["interpretation"] == "HIGH"
    assert len(d["basis"]) == 2
    assert len(d["limitations"]) == 1


def test_disposition_clean_pass_accept():
    rec = determine_disposition(
        category=FindingCategory.DATA_INTEGRITY.value,
        status=FindingStatus.PASS.value,
        severity=SeverityLevel.LOW.value,
        reason="Checks passed cleanly.",
    )
    assert rec.disposition == GovernanceDisposition.ACCEPT.value
    assert rec.priority == "ROUTINE"


def test_disposition_anomaly_review():
    rec = determine_disposition(
        category=FindingCategory.DISTRIBUTION_SHIFT.value,
        status=FindingStatus.WARNING.value,
        severity=SeverityLevel.MEDIUM.value,
        reason="MMD indicates lighting shift.",
    )
    assert rec.disposition == GovernanceDisposition.REVIEW.value
    assert rec.priority == "ELEVATED"


def test_disposition_critical_tamper_quarantine():
    rec = determine_disposition(
        category=FindingCategory.INFERENCE_PROVENANCE.value,
        status=FindingStatus.FAIL.value,
        severity=SeverityLevel.CRITICAL.value,
        reason="Digital signature verification failed.",
    )
    assert rec.disposition == GovernanceDisposition.QUARANTINE.value
    assert rec.priority == "URGENT"


def test_disposition_not_assessed():
    rec = determine_disposition(
        category=FindingCategory.MODEL_INTEGRITY.value,
        status=FindingStatus.NOT_ASSESSED.value,
        severity=SeverityLevel.LOW.value,
        reason="Model weights unavailable.",
    )
    assert rec.disposition == GovernanceDisposition.REVIEW.value
