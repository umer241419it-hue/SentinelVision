"""
Tests for Coverage Statement and Attack-Class Declaration.
"""

from governance.coverage import (
    ATTACK_CLASS_DEFINITIONS,
    SYSTEM_CAPABILITY_DEFINITIONS,
    build_coverage_matrix,
)
from governance.schema import AttackClass, SupportStatus


def test_required_attack_classes_present():
    declared_classes = {atk["attack_class"] for atk in ATTACK_CLASS_DEFINITIONS}
    required = [
        AttackClass.LABEL_FLIPPING.value,
        AttackClass.SYSTEMATIC_MISLABELING.value,
        AttackClass.DUPLICATE_FLOODING.value,
        AttackClass.OUT_OF_DISTRIBUTION_INSERTION.value,
        AttackClass.TRIGGER_INJECTION.value,
        AttackClass.BACKDOOR_BEHAVIOUR.value,
        AttackClass.MODEL_SUBSTITUTION.value,
        AttackClass.MODEL_MODIFICATION.value,
        AttackClass.INFERENCE_TAMPERING.value,
        AttackClass.INFERENCE_REPLAY.value,
        AttackClass.DISTRIBUTION_SHIFT.value,
        AttackClass.CONTRIBUTOR_RISK_AGGREGATION.value,
    ]
    for r in required:
        assert r in declared_classes, f"Missing required attack class declaration: {r}"


def test_honest_support_status():
    status_map = {atk["attack_class"]: atk["support_status"] for atk in ATTACK_CLASS_DEFINITIONS}

    # Partially supported items must NOT be claimed as fully supported
    assert status_map[AttackClass.LABEL_FLIPPING.value] == SupportStatus.PARTIALLY_SUPPORTED.value
    assert status_map[AttackClass.BACKDOOR_BEHAVIOUR.value] == SupportStatus.PARTIALLY_SUPPORTED.value
    assert status_map[AttackClass.DUPLICATE_FLOODING.value] == SupportStatus.PARTIALLY_SUPPORTED.value
    assert status_map[AttackClass.OUT_OF_DISTRIBUTION_INSERTION.value] == SupportStatus.PARTIALLY_SUPPORTED.value

    # Supported cryptographic items
    assert status_map[AttackClass.INFERENCE_TAMPERING.value] == SupportStatus.SUPPORTED.value
    assert status_map[AttackClass.MODEL_SUBSTITUTION.value] == SupportStatus.SUPPORTED.value
    assert status_map[AttackClass.DISTRIBUTION_SHIFT.value] == SupportStatus.SUPPORTED.value

    # Unsupported items explicitly documented
    assert status_map["ADVERSARIAL_EVASION_PATCH"] == SupportStatus.UNSUPPORTED.value


def test_coverage_matrix_correlation():
    dummy_findings = [
        {
            "finding_id": "find-1",
            "category": "DATA_INTEGRITY",
            "reason": "Near-duplicate of img_001.png detected",
        },
        {
            "finding_id": "find-2",
            "category": "INFERENCE_PROVENANCE",
            "reason": "Cryptographic seal tampered",
        },
    ]
    matrix = build_coverage_matrix(executed_findings=dummy_findings)
    m_dict = matrix.to_dict()

    # Verify duplicate finding correlated
    dup_atk = next(a for a in m_dict["attack_classes"] if a["attack_class"] == AttackClass.DUPLICATE_FLOODING.value)
    assert "find-1" in dup_atk["finding_ids"]

    # Verify inference tamper finding correlated
    tamper_atk = next(a for a in m_dict["attack_classes"] if a["attack_class"] == AttackClass.INFERENCE_TAMPERING.value)
    assert "find-2" in tamper_atk["finding_ids"]
