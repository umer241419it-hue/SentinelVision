"""
SentinelVision - Governance Recommendations & Dispositions.

Determines evidence-backed analyst dispositions (ACCEPT, REVIEW, QUARANTINE)
with clear rationale and concrete operational next steps.
Never claims malicious intent unless conclusively established by cryptographic proof.
"""

from typing import Any, Dict, List, Optional
from .schema import GovernanceDisposition, Recommendation, SeverityLevel, FindingStatus


def determine_disposition(
    category: str,
    status: str,
    severity: str,
    reason: str,
    evidence_details: Optional[Dict[str, Any]] = None,
) -> Recommendation:
    """
    Produce an analyst recommendation with disposition, rationale, and suggested action.
    """
    details = evidence_details or {}

    # 1. Cryptographic failures or confirmed tamper -> QUARANTINE
    if status == FindingStatus.FAIL or severity == SeverityLevel.CRITICAL:
        if category in ("INFERENCE_PROVENANCE", "OUTPUT_TAMPERING"):
            return Recommendation(
                disposition=GovernanceDisposition.QUARANTINE.value,
                reason="Cryptographic binding or signature verification failed for inference record.",
                suggested_action="Quarantine inference output immediately; verify model weights and execution pipeline authenticity.",
                priority="URGENT",
            )
        if category == "MODEL_INTEGRITY":
            return Recommendation(
                disposition=GovernanceDisposition.QUARANTINE.value,
                reason="Model exhibits high-confidence trojan/backdoor behavior with corroborating entropy suppression.",
                suggested_action="Quarantine model binary from inference pipelines; initiate model weights audit and retrain candidate.",
                priority="URGENT",
            )
        if category == "DATA_INTEGRITY":
            return Recommendation(
                disposition=GovernanceDisposition.QUARANTINE.value,
                reason="High-confidence trigger patch pattern identified in training data.",
                suggested_action="Isolate flagged images and associated contributor batch before model ingestion.",
                priority="URGENT",
            )
        return Recommendation(
            disposition=GovernanceDisposition.QUARANTINE.value,
            reason=f"Integrity check failed with critical severity: {reason}",
            suggested_action="Quarantine asset pending manual forensic investigation.",
            priority="URGENT",
        )

    # 2. Anomalies, shifts, or uncorroborated flags -> REVIEW
    if status in (FindingStatus.REVIEW, FindingStatus.WARNING) or severity in (SeverityLevel.HIGH, SeverityLevel.MEDIUM):
        if category == "DISTRIBUTION_SHIFT":
            diag = details.get("diagnostics", {})
            diag_reason = details.get("reason", "")
            return Recommendation(
                disposition=GovernanceDisposition.REVIEW.value,
                reason=f"Statistically significant distribution shift detected against reference battery ({reason}).",
                suggested_action="Inspect operational environmental changes (lighting, sensor calibrations, contributor drift) before production deployment.",
                priority="ELEVATED",
            )
        if category == "DATA_INTEGRITY":
            return Recommendation(
                disposition=GovernanceDisposition.REVIEW.value,
                reason=f"Data statistical anomaly detected: {reason}.",
                suggested_action="Review sample annotations and provenance batch with domain analyst before training inclusion.",
                priority="ELEVATED",
            )
        if category == "MODEL_INTEGRITY":
            return Recommendation(
                disposition=GovernanceDisposition.REVIEW.value,
                reason=f"Model integrity anomaly flagged but lacks conclusive corroboration: {reason}.",
                suggested_action="Conduct targeted behavioral testing on flagged classes; review training dataset lineage.",
                priority="ELEVATED",
            )
        return Recommendation(
            disposition=GovernanceDisposition.REVIEW.value,
            reason=f"Anomaly requires analyst investigation: {reason}",
            suggested_action="Conduct secondary verification under supervisory review.",
            priority="ELEVATED",
        )

    # 3. Not assessed / unavailable evidence -> REVIEW with advisory
    if status == FindingStatus.NOT_ASSESSED:
        return Recommendation(
            disposition=GovernanceDisposition.REVIEW.value,
            reason="Required access, metadata, or baseline artifacts were unavailable during evaluation.",
            suggested_action="Provide required reference battery, model weights, or provenance metadata to complete assurance check.",
            priority="ROUTINE",
        )

    # 4. Clean pass -> ACCEPT
    return Recommendation(
        disposition=GovernanceDisposition.ACCEPT.value,
        reason="No material integrity anomalies or cryptographic violations detected under executed checks.",
        suggested_action="Asset cleared for deployment under declared access profile and known limitations.",
        priority="ROUTINE",
    )
