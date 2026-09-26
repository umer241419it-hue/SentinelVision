"""
Tests for Tamper-Evident Governance Audit Trail and Hash Chaining.
"""

from governance.audit import (
    AuditEventType,
    AuditTrail,
    GENESIS_PREV_HASH,
    compute_event_hash,
    verify_audit_events,
)


def test_audit_trail_valid_chain():
    trail = AuditTrail("asmt-test-001")
    trail.add_event(AuditEventType.ASSESSMENT_STARTED, data={"run": 1})
    trail.add_event(AuditEventType.ASSET_REGISTERED, data={"asset_id": "model-1"}, reference_ids=["model-1"])
    trail.add_event(AuditEventType.DATA_CHECK_COMPLETED, data={"samples": 100})
    trail.add_event(AuditEventType.ASSESSMENT_COMPLETED)

    is_valid, reason = trail.verify_chain()
    assert is_valid is True
    assert reason is None

    events = trail.events
    assert len(events) == 4
    assert events[0]["previous_event_hash"] == GENESIS_PREV_HASH
    assert events[1]["previous_event_hash"] == events[0]["event_hash"]
    assert events[2]["previous_event_hash"] == events[1]["event_hash"]
    assert events[3]["previous_event_hash"] == events[2]["event_hash"]


def test_audit_trail_detects_data_tamper():
    trail = AuditTrail("asmt-test-002")
    trail.add_event(AuditEventType.ASSESSMENT_STARTED)
    trail.add_event(AuditEventType.MODEL_CHECK_COMPLETED, data={"result": "PASS"})
    trail.add_event(AuditEventType.ASSESSMENT_COMPLETED)

    # Tamper with event 1 data
    trail.events[1]["data"]["result"] = "TAMPERED_RESULT"

    is_valid, reason = trail.verify_chain()
    assert is_valid is False
    assert "Tampered event content" in reason


def test_audit_trail_detects_event_deletion():
    trail = AuditTrail("asmt-test-003")
    trail.add_event(AuditEventType.ASSESSMENT_STARTED)
    trail.add_event(AuditEventType.DATA_CHECK_COMPLETED, data={"step": 1})
    trail.add_event(AuditEventType.MODEL_CHECK_COMPLETED, data={"step": 2})
    trail.add_event(AuditEventType.ASSESSMENT_COMPLETED)

    # Delete intermediate event
    del trail.events[1]

    is_valid, reason = trail.verify_chain()
    assert is_valid is False
    assert "Sequence break" in reason or "Broken hash chain" in reason


def test_audit_trail_detects_event_reorder():
    trail = AuditTrail("asmt-test-004")
    trail.add_event(AuditEventType.ASSESSMENT_STARTED)
    trail.add_event(AuditEventType.DATA_CHECK_COMPLETED, data={"step": 1})
    trail.add_event(AuditEventType.MODEL_CHECK_COMPLETED, data={"step": 2})
    trail.add_event(AuditEventType.ASSESSMENT_COMPLETED)

    # Swap events 1 and 2
    trail.events[1], trail.events[2] = trail.events[2], trail.events[1]

    is_valid, reason = trail.verify_chain()
    assert is_valid is False
