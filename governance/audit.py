"""
SentinelVision - Tamper-Evident Governance Audit Trail.

Implements sequential SHA-256 cryptographic hash chaining across all governance lifecycle events.
Modification, insertion, deletion, or reordering of historical audit events is immediately detectable.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CRYPTO_UTILS_DIR = os.path.join(WORKSPACE_ROOT, "crypto-utils")
if CRYPTO_UTILS_DIR not in sys.path:
    sys.path.insert(0, CRYPTO_UTILS_DIR)

try:
    from canonical import canonical_json
except ImportError:
    def canonical_json(obj: Dict[str, Any]) -> str:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"))

GENESIS_PREV_HASH = "0" * 64


class AuditEventType:
    ASSESSMENT_STARTED = "ASSESSMENT_STARTED"
    ASSET_REGISTERED = "ASSET_REGISTERED"
    DATA_CHECK_COMPLETED = "DATA_CHECK_COMPLETED"
    MODEL_CHECK_COMPLETED = "MODEL_CHECK_COMPLETED"
    SEAL_VERIFICATION_COMPLETED = "SEAL_VERIFICATION_COMPLETED"
    DRIFT_CHECK_COMPLETED = "DRIFT_CHECK_COMPLETED"
    FINDING_CREATED = "FINDING_CREATED"
    REPORT_GENERATED = "REPORT_GENERATED"
    ASSESSMENT_COMPLETED = "ASSESSMENT_COMPLETED"


def compute_event_hash(event_dict: Dict[str, Any]) -> str:
    """
    Compute SHA-256 digest of canonical JSON serialization of an event dictionary,
    excluding the 'event_hash' key itself.
    """
    payload = {k: v for k, v in event_dict.items() if k != "event_hash"}
    canonical_str = canonical_json(payload)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


@dataclass
class AuditEvent:
    event_id: str
    sequence_index: int
    timestamp: str
    assessment_id: str
    event_type: str
    actor: str
    reference_ids: List[str]
    data: Dict[str, Any]
    previous_event_hash: str
    event_hash: str = ""

    def __post_init__(self):
        if not self.event_hash:
            self.event_hash = compute_event_hash(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "event_id": self.event_id,
            "sequence_index": self.sequence_index,
            "timestamp": self.timestamp,
            "assessment_id": self.assessment_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "reference_ids": list(self.reference_ids),
            "data": dict(self.data),
            "previous_event_hash": self.previous_event_hash,
        }
        if self.event_hash:
            d["event_hash"] = self.event_hash
        return d


class AuditTrail:
    """
    Append-only tamper-evident audit trail backed by SHA-256 hash chaining.
    """

    def __init__(self, assessment_id: str, actor: str = "GovernanceEngine"):
        self.assessment_id = assessment_id
        self.actor = actor
        self.events: List[Dict[str, Any]] = []

    def add_event(
        self,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        reference_ids: Optional[List[str]] = None,
        actor: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record a new event, chaining to previous_event_hash and computing event_hash.
        """
        seq = len(self.events)
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        evt_actor = actor or self.actor
        ref_ids = list(reference_ids) if reference_ids else []
        evt_data = dict(data) if data else {}

        prev_hash = self.events[-1]["event_hash"] if self.events else GENESIS_PREV_HASH
        evt_id = f"evt-{self.assessment_id[-8:]}-{seq:04d}"

        event_payload = {
            "event_id": evt_id,
            "sequence_index": seq,
            "timestamp": ts,
            "assessment_id": self.assessment_id,
            "event_type": event_type,
            "actor": evt_actor,
            "reference_ids": ref_ids,
            "data": evt_data,
            "previous_event_hash": prev_hash,
        }
        event_hash = compute_event_hash(event_payload)
        event_payload["event_hash"] = event_hash

        self.events.append(event_payload)
        return event_payload

    def verify_chain(self) -> Tuple[bool, Optional[str]]:
        """
        Verify cryptographic integrity of all events in the audit chain.
        Returns:
            (True, None) if completely valid.
            (False, error_reason) if any tampering, omission, or corruption is detected.
        """
        return verify_audit_events(self.events)

    def to_dict(self) -> Dict[str, Any]:
        is_valid, reason = self.verify_chain()
        return {
            "chain_valid": is_valid,
            "verification_status": "VALID" if is_valid else f"TAMPERED: {reason}",
            "event_count": len(self.events),
            "genesis_hash": GENESIS_PREV_HASH,
            "final_chain_hash": self.events[-1]["event_hash"] if self.events else GENESIS_PREV_HASH,
            "events": list(self.events),
        }


def verify_audit_events(events: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """
    Stand-alone verification function for audit event list.
    Checks:
    1. Genesis previous_event_hash matches 64 zeros.
    2. Sequence indices are contiguous starting at 0.
    3. Each event's recomputed hash matches stored event_hash.
    4. Each event's previous_event_hash matches preceding event's event_hash.
    """
    if not events:
        return True, None

    for i, evt in enumerate(events):
        seq = evt.get("sequence_index")
        if seq != i:
            return False, f"Sequence break at index {i}: expected sequence_index={i}, found {seq}"

        stored_prev = evt.get("previous_event_hash")
        expected_prev = GENESIS_PREV_HASH if i == 0 else events[i - 1].get("event_hash")
        if stored_prev != expected_prev:
            return False, f"Broken hash chain at sequence {i} ({evt.get('event_id')}): previous_event_hash does not match preceding event_hash"

        stored_hash = evt.get("event_hash")
        if not stored_hash:
            return False, f"Event {evt.get('event_id')} missing event_hash"

        recomputed_hash = compute_event_hash(evt)
        if recomputed_hash != stored_hash:
            return False, f"Tampered event content at sequence {i} ({evt.get('event_id')}): recomputed {recomputed_hash} != stored {stored_hash}"

    return True, None
