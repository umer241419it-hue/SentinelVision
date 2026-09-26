"""
Tests for Canonical Assurance Report Schema validation.
"""

from governance.engine import GovernanceEngine
from governance.schema import (
    AssuranceReport,
    FindingCategory,
    FindingStatus,
    GovernanceDisposition,
    OverallStatus,
    SCHEMA_VERSION,
    SeverityLevel,
    validate_report_dict,
)


def test_valid_report_schema():
    engine = GovernanceEngine()
    engine.record_unassessed_capability(
        category="MODEL_INTEGRITY",
        capability_name="Model Integrity Assessment",
        reason="Model weights not provided.",
        required_access="Model weights",
    )
    report = engine.assemble_report()
    report_dict = report.to_dict()

    errors = validate_report_dict(report_dict)
    assert errors == [], f"Validation errors on valid report: {errors}"
    assert report_dict["schema_version"] == SCHEMA_VERSION
    assert report_dict["overall_assessment"]["overall_status"] == OverallStatus.PASS_WITH_LIMITATIONS.value


def test_missing_required_fields():
    engine = GovernanceEngine()
    report_dict = engine.assemble_report().to_dict()

    del report_dict["assessment_id"]
    del report_dict["overall_assessment"]

    errors = validate_report_dict(report_dict)
    assert any("assessment_id" in err for err in errors)
    assert any("overall_assessment" in err for err in errors)


def test_invalid_overall_status_and_disposition():
    engine = GovernanceEngine()
    report_dict = engine.assemble_report().to_dict()

    report_dict["overall_assessment"]["overall_status"] = "INVALID_STATUS_XYZ"
    report_dict["overall_assessment"]["disposition"] = "INVALID_DISPOSITION"

    errors = validate_report_dict(report_dict)
    assert any("INVALID_STATUS_XYZ" in err for err in errors)
    assert any("INVALID_DISPOSITION" in err for err in errors)


def test_invalid_finding_confidence_and_severity():
    engine = GovernanceEngine()
    engine.record_unassessed_capability(
        category="DATA_INTEGRITY",
        capability_name="Test",
        reason="Test",
        required_access="Test",
    )
    report_dict = engine.assemble_report().to_dict()

    report_dict["findings"][0]["severity"] = "BOGUS_SEVERITY"
    report_dict["findings"][0]["confidence"]["value"] = 2.5  # out of [0, 1]

    errors = validate_report_dict(report_dict)
    assert any("BOGUS_SEVERITY" in err for err in errors)
    assert any("out of range" in err for err in errors)
