"""
SentinelVision - Principled Evidence Fusion Layer.

Fuses heterogeneous integrity signals:
1. Label anomalies (Cleanlab confident learning out-of-sample error probabilities)
2. Near-duplicate anomalies (Cosine similarity in standardized embedding space)
3. Out-Of-Distribution (OOD) anomalies (Class-conditional Mahalanobis distance)
4. Training-data trigger anomalies (Patch residual normalized cross-correlation & clique clustering)
5. Group/provenance anomalies (Systematic mislabelling z-scores and concentration)

Principles:
- Strict decoupling of Confidence (evidence certainty: 0.0 to 1.0) and Severity (impact: LOW, MEDIUM, HIGH, CRITICAL).
- Probabilistic noisy-OR fusion for multi-sensor confidence:
    C_combined = 1.0 - PROD_{i=1}^k (1.0 - c_i)
  capped at 0.98 to account for epistemic uncertainty.
- Clear separation between statistical distribution shift (OOD) and confirmed adversarial manipulation (trigger/flipping).
- Evidence-grounded disposition policy (ACCEPT, REVIEW, QUARANTINE).
"""

from typing import Any, Dict, List, Optional, Tuple

SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
ORDER_TO_SEVERITY = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "CRITICAL"}


class EvidenceFusionEngine:
    """
    Principled multi-sensor fusion engine for computer vision training-data integrity.
    """

    def __init__(
        self,
        base_confidence_cap: float = 0.98,
        quarantine_confidence_threshold: float = 0.90,
    ):
        self.base_confidence_cap = base_confidence_cap
        self.quarantine_confidence_threshold = quarantine_confidence_threshold

    def fuse_sample_evidence(
        self,
        sample_id: str,
        detector_flags: Dict[str, Dict[str, Any]],
        provenance_info: Optional[Dict[str, str]] = None,
        group_findings: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fuse detector flags for a single sample.

        Args:
            sample_id: Unique identifier of the sample.
            detector_flags: Dict mapping detector_name -> {
                "flagged": bool,
                "confidence": float,
                "severity": str,
                "reason": str,
                "details": dict,
            }
            provenance_info: Optional provenance metadata for the sample.
            group_findings: Optional list of group-level findings matching this sample's group.

        Returns:
            Fused record dict, or None if no detectors flagged the sample.
        """
        active_flags = {
            det_name: flag_data
            for det_name, flag_data in detector_flags.items()
            if flag_data.get("flagged", False)
        }

        if not active_flags:
            return None

        # 1. Calculate Combined Confidence using Noisy-OR
        # P(flagged_correctly) = 1 - PROD(1 - c_i)
        unconfidences = []
        for det_name, data in active_flags.items():
            c = float(data.get("confidence", 0.50))
            c = max(0.01, min(0.99, c))
            unconfidences.append(1.0 - c)

        prod_unconf = 1.0
        for u in unconfidences:
            prod_unconf *= u

        raw_fused_conf = 1.0 - prod_unconf
        fused_confidence = round(min(self.base_confidence_cap, max(0.50, raw_fused_conf)), 2)

        # 2. Determine Severity
        # Severity reflects impact, not just certainty:
        # - Trigger injection has critical security impact -> CRITICAL / HIGH
        # - Systematic mislabelling / multi-detector consensus -> HIGH
        # - Near-duplicate or cleanlab flip alone -> MEDIUM / LOW
        # - OOD alone (distribution anomaly without confirmed backdoor) -> MEDIUM
        highest_severity_rank = 0
        has_trigger = "trigger" in active_flags or "trigger_detector" in active_flags
        has_label_flip = "label_flip" in active_flags
        has_duplicate = "duplicate" in active_flags
        has_ood = "ood" in active_flags

        for data in active_flags.values():
            s = data.get("severity", "LOW").upper()
            rank = SEVERITY_ORDER.get(s, 0)
            if rank > highest_severity_rank:
                highest_severity_rank = rank

        # Escalation policy
        if has_trigger:
            highest_severity_rank = max(highest_severity_rank, SEVERITY_ORDER["HIGH"])
            if fused_confidence >= 0.88:
                highest_severity_rank = SEVERITY_ORDER["CRITICAL"]
        elif len(active_flags) >= 2:
            # Multi-detector consensus escalates severity
            highest_severity_rank = max(highest_severity_rank, SEVERITY_ORDER["HIGH"])

        # Check for group-level anomaly escalation
        associated_group_findings = []
        if group_findings and provenance_info:
            for gf in group_findings:
                gt = gf.get("group_type")
                gid = gf.get("group_id")
                if provenance_info.get(f"{gt}_id") == gid:
                    associated_group_findings.append(gf)
                    if gf.get("severity") == "HIGH":
                        highest_severity_rank = max(highest_severity_rank, SEVERITY_ORDER["HIGH"])

        fused_severity = ORDER_TO_SEVERITY[highest_severity_rank]

        # 3. Determine Disposition
        # QUARANTINE requires HIGH/CRITICAL severity and high statistical confidence
        if (
            fused_severity in ("HIGH", "CRITICAL")
            and fused_confidence >= self.quarantine_confidence_threshold
            and has_trigger
        ):
            disposition = "QUARANTINE"
        else:
            disposition = "REVIEW"

        # 4. Synthesize Reason and Evidence Details
        reasons = []
        for det_name, data in active_flags.items():
            r = data.get("reason")
            if r:
                reasons.append(f"[{det_name}] {r}")

        if associated_group_findings:
            for gf in associated_group_findings:
                reasons.append(f"[Group: {gf['group_type']}={gf['group_id']}] {gf.get('reason')}")

        fused_record = {
            "sample_id": sample_id,
            "flags": sorted(list(active_flags.keys())),
            "n_flags": len(active_flags),
            "confidence": fused_confidence,
            "severity": fused_severity,
            "disposition": disposition,
            "reason": " | ".join(reasons),
            "details": {
                det_name: data.get("details", {}) for det_name, data in active_flags.items()
            },
            "provenance": provenance_info or {},
            "associated_groups": [
                f"{gf.get('group_type')}:{gf.get('group_id')}" for gf in associated_group_findings
            ],
            "fusion_math": {
                "method": "noisy_or_probabilistic_independence",
                "inputs": {
                    det_name: round(float(data.get("confidence", 0.5)), 2)
                    for det_name, data in active_flags.items()
                },
                "fused_confidence": fused_confidence,
            },
        }

        return fused_record
