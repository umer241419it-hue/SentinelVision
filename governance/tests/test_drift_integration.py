"""
Tests for Distribution-Shift / Drift Monitoring Integration into Governance.
Validates:
- Normal distribution (NO_SIGNIFICANT_SHIFT) -> PASS / ACCEPT
- Material operational shift (OPERATIONAL_SHIFT_LIKELY) -> WARNING / REVIEW
- Unexplained shift (UNEXPLAINED_SHIFT) -> REVIEW / REVIEW
- Missing reference / insufficient sample count -> NOT_ASSESSED / REVIEW
"""

from governance.engine import GovernanceEngine
from governance.schema import FindingStatus, GovernanceDisposition, SeverityLevel


def test_normal_distribution_drift_pass():
    drift_data = {
        "run": {"reference_id": "ref-v1", "run_id": "test-run"},
        "results": [
            {
                "window_id": "win-clean-01",
                "assessment": "NO_SIGNIFICANT_SHIFT",
                "image_count": 100,
                "mmd": {"statistic": 0.002, "threshold": 0.009, "p_value": 0.45},
            }
        ],
    }
    engine = GovernanceEngine()
    engine.ingest_drift_results(drift_data)
    report = engine.assemble_report()

    assert len(report.findings) == 1
    f = report.findings[0]
    assert f.status == FindingStatus.PASS.value
    assert f.severity == SeverityLevel.LOW.value
    assert f.recommendation.disposition == GovernanceDisposition.ACCEPT.value


def test_material_operational_shift_review():
    drift_data = {
        "run": {"reference_id": "ref-v1", "run_id": "test-run"},
        "results": [
            {
                "window_id": "win-lighting-01",
                "assessment": "OPERATIONAL_SHIFT_LIKELY",
                "image_count": 100,
                "mmd": {"statistic": 0.045, "threshold": 0.009, "p_value": 0.001},
                "diagnostics": {"brightness_mean_delta": -0.32},
            }
        ],
    }
    engine = GovernanceEngine()
    engine.ingest_drift_results(drift_data)
    report = engine.assemble_report()

    f = report.findings[0]
    assert f.status == FindingStatus.WARNING.value
    assert f.severity == SeverityLevel.MEDIUM.value
    assert f.recommendation.disposition == GovernanceDisposition.REVIEW.value
    assert report.overall_assessment.disposition == GovernanceDisposition.REVIEW.value


def test_unexplained_shift_review():
    drift_data = {
        "run": {"reference_id": "ref-v1", "run_id": "test-run"},
        "results": [
            {
                "window_id": "win-unexplained-01",
                "assessment": "UNEXPLAINED_SHIFT",
                "image_count": 100,
                "mmd": {"statistic": 0.082, "threshold": 0.009, "p_value": 0.0},
            }
        ],
    }
    engine = GovernanceEngine()
    engine.ingest_drift_results(drift_data)
    report = engine.assemble_report()

    f = report.findings[0]
    assert f.status == FindingStatus.REVIEW.value
    assert f.severity == SeverityLevel.HIGH.value
    assert f.recommendation.disposition == GovernanceDisposition.REVIEW.value


def test_insufficient_samples_drift():
    drift_data = {
        "run": {"reference_id": "ref-v1"},
        "results": [
            {
                "window_id": "win-small-01",
                "assessment": "INSUFFICIENT_EVIDENCE",
                "image_count": 12,
                "mmd": {"statistic": 0.0, "threshold": 0.009},
            }
        ],
    }
    engine = GovernanceEngine()
    engine.ingest_drift_results(drift_data)
    report = engine.assemble_report()

    f = report.findings[0]
    assert f.status == FindingStatus.NOT_ASSESSED.value
    assert f.recommendation.disposition == GovernanceDisposition.REVIEW.value
