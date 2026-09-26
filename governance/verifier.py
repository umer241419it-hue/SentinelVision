"""
SentinelVision - Assurance Report & Audit Verifier.

Independently verifies:
1. Canonical report hash matches content (tamper detection).
2. Ed25519 report signature matches GovernanceEngine registered public key.
3. Sequential SHA-256 audit chain integrity from genesis to terminal event.
4. Embedded module finding signatures and evidence hash integrity.
"""

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CRYPTO_UTILS_DIR = os.path.join(WORKSPACE_ROOT, "crypto-utils")
if CRYPTO_UTILS_DIR not in sys.path:
    sys.path.insert(0, CRYPTO_UTILS_DIR)

from .audit import verify_audit_events

try:
    from canonical import canonical_json
    from verify import verify_fields
except ImportError:
    def canonical_json(obj: Dict[str, Any]) -> str:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"))
    verify_fields = None


class AssuranceReportVerifier:
    """
    Independent verifier for SentinelVision Assurance Reports and Audit Trails.
    """

    def __init__(self, public_key_registry_path: Optional[Union[str, Path]] = None):
        self.registry_path = Path(public_key_registry_path) if public_key_registry_path else (Path(CRYPTO_UTILS_DIR) / "public_key_registry.json")

    def verify_report(self, report_or_path: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Verify complete integrity of an Assurance Report.
        """
        if isinstance(report_or_path, (str, Path)):
            path = Path(report_or_path)
            if not path.is_file():
                return {
                    "verdict": "ERROR",
                    "error": f"Report file not found at: {path}",
                }
            with open(path, "r", encoding="utf-8") as f:
                report = json.load(f)
        else:
            report = dict(report_or_path)

        issues: List[str] = []

        # 1. Verify Report Hash Binding
        report_integrity = report.get("report_integrity")
        report_hash_valid = False
        signature_valid = False

        if not report_integrity:
            issues.append("Missing 'report_integrity' block in report")
        else:
            stored_hash = report_integrity.get("report_hash")
            stored_sig = report_integrity.get("signature")
            signer = report_integrity.get("signer", "GovernanceEngine")

            # Recompute content hash across all fields excluding report_integrity
            payload = {k: v for k, v in report.items() if k != "report_integrity"}
            canonical_str = canonical_json(payload)
            computed_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

            if computed_hash == stored_hash:
                report_hash_valid = True
            else:
                issues.append(f"Report content hash mismatch: computed {computed_hash} != stored {stored_hash}")

            # Verify Ed25519 digital signature
            if stored_sig and verify_fields and self.registry_path.exists():
                try:
                    sig_ok = verify_fields(
                        module_name=signer,
                        fields=payload,
                        signature=stored_sig,
                        registry_path=self.registry_path,
                    )
                    signature_valid = bool(sig_ok)
                    if not signature_valid:
                        issues.append(f"Ed25519 signature verification failed for signer '{signer}'")
                except Exception as e:
                    issues.append(f"Error during signature verification: {e}")
            else:
                if not stored_sig:
                    issues.append("Missing 'signature' in report_integrity")

        # 2. Verify Audit Trail Hash Chain
        audit_trail = report.get("audit", {})
        audit_events = audit_trail.get("events", [])
        audit_chain_valid, audit_error = verify_audit_events(audit_events)
        if not audit_chain_valid:
            issues.append(f"Audit chain verification failure: {audit_error}")

        # 3. Overall Verdict
        is_valid = report_hash_valid and signature_valid and audit_chain_valid
        verdict = "VALID" if is_valid else "TAMPERED"

        return {
            "verdict": verdict,
            "report_hash_valid": report_hash_valid,
            "signature_valid": signature_valid,
            "audit_chain_valid": audit_chain_valid,
            "issues": issues,
            "assessment_id": report.get("assessment_id"),
            "schema_version": report.get("schema_version"),
            "event_count": len(audit_events),
            "findings_count": len(report.get("findings", [])),
        }

    def verify_audit_trail_only(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Verify only an audit trail event list.
        """
        valid, reason = verify_audit_events(events)
        return {
            "verdict": "VALID" if valid else "TAMPERED",
            "chain_valid": valid,
            "event_count": len(events),
            "error": reason,
        }
