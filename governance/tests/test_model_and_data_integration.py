"""
Tests for Data Integrity and Model Integrity Findings Ingestion into Governance.
"""

from governance.engine import GovernanceEngine
from governance.schema import FindingStatus, GovernanceDisposition, OverallStatus, SeverityLevel


def test_model_integrity_clean_pass():
    model_finding = {
        "assetID": "model-clean-01",
        "moduleName": "ModelIntegrity-NeuralCleanse-MAD-STRIP",
        "reason": "No anomalous class detected by Neural Cleanse + MAD.",
        "evidenceHash": "8940e54c11228b71006be17eeede70a636a0380fe147fd3aee6f2430a9cfdb5b",
        "confidence": "0.38",
        "severity": "LOW",
        "disposition": "ACCEPT",
        "timestamp": "2026-09-22T11:37:01Z",
    }
    engine = GovernanceEngine()
    engine.ingest_model_integrity_results([model_finding])
    report = engine.assemble_report()

    f = report.findings[0]
    assert f.status == FindingStatus.PASS.value
    assert f.severity == SeverityLevel.LOW.value
    assert f.recommendation.disposition == GovernanceDisposition.ACCEPT.value


def test_model_integrity_corroborated_backdoor_quarantine():
    model_finding = {
        "assetID": "model-trojan-01",
        "moduleName": "ModelIntegrity-NeuralCleanse-MAD-STRIP",
        "reason": "Class 2 flagged by Neural Cleanse + MAD (anomaly index 3.13) and independently corroborated by STRIP entropy-suppression.",
        "evidenceHash": "ebc9937b69204858ac0ba24c40141a773307694d18db2a89a5cbd93df240d75f",
        "confidence": "0.85",
        "severity": "CRITICAL",
        "disposition": "QUARANTINE",
        "timestamp": "2026-09-22T11:37:01Z",
    }
    engine = GovernanceEngine()
    engine.ingest_model_integrity_results([model_finding])
    report = engine.assemble_report()

    f = report.findings[0]
    assert f.status == FindingStatus.FAIL.value
    assert f.severity == SeverityLevel.CRITICAL.value
    assert f.recommendation.disposition == GovernanceDisposition.QUARANTINE.value
    assert report.overall_assessment.disposition == GovernanceDisposition.QUARANTINE.value


def test_data_integrity_findings_review():
    data_findings = [
        {
            "assetID": "image-dup-001",
            "moduleName": "DataIntegrity",
            "reason": "near-duplicate of img_0017.png (cosine 1.00 >= threshold 0.99)",
            "evidenceHash": "32d343a39e18c47b05feb818901d0555ec47b3caa80d6e9554302eb043ea125f",
            "confidence": "0.60",
            "severity": "MEDIUM",
            "disposition": "REVIEW",
            "timestamp": "2026-01-01T00:00:00Z",
        },
        {
            "assetID": "image-ood-002",
            "moduleName": "DataIntegrity",
            "reason": "statistical outlier (Mahalanobis distance 103.52 > threshold 59.83)",
            "evidenceHash": "001ac054f60c4b1e7cd904713d07f4fcf96a1b1b5f7c7a59d7199a205d4feab8",
            "confidence": "0.75",
            "severity": "HIGH",
            "disposition": "REVIEW",
            "timestamp": "2026-01-01T00:00:00Z",
        },
    ]
    engine = GovernanceEngine()
    engine.ingest_data_integrity_results(data_findings)
    report = engine.assemble_report()

    assert len(report.findings) == 2
    assert report.overall_assessment.overall_status == OverallStatus.REVIEW.value
    assert report.overall_assessment.disposition == GovernanceDisposition.REVIEW.value


def test_missing_assessment_never_silently_pass():
    engine = GovernanceEngine()
    # Only clean model check executed
    engine.ingest_model_integrity_results([
        {
            "assetID": "model-clean-01",
            "moduleName": "ModelIntegrity",
            "reason": "Clean",
            "severity": "LOW",
            "disposition": "ACCEPT",
            "confidence": "0.5",
        }
    ])
    # Explicitly record unassessed data integrity check
    engine.record_unassessed_capability(
        category="DATA_INTEGRITY",
        capability_name="Training Data Integrity",
        reason="Dataset not provided.",
        required_access="Dataset images",
    )
    report = engine.assemble_report()

    oa = report.overall_assessment
    # Cannot be unconditional PASS! Must be PASS_WITH_LIMITATIONS
    assert oa.overall_status == OverallStatus.PASS_WITH_LIMITATIONS.value
    assert oa.not_assessed == 1
    assert "LIMITATIONS" in oa.summary
