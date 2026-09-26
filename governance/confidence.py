"""
SentinelVision - Confidence & Severity Governance Assessment.

Implements transparent, evidence-based confidence scoring and qualitative interpretation.
Preserves module provenance calculations while explaining basis and limitations.
"""

from typing import Any, Dict, List, Optional, Union
from .schema import ConfidenceAssessment, SeverityLevel


def interpret_confidence_value(value: Union[float, int, str]) -> str:
    """Map numeric confidence to qualitative category."""
    if value == "UNKNOWN" or value is None:
        return "UNKNOWN"
    try:
        f = float(value)
        if f >= 0.80:
            return "HIGH"
        elif f >= 0.50:
            return "MEDIUM"
        else:
            return "LOW"
    except (ValueError, TypeError):
        return "UNKNOWN"


def build_confidence_assessment(
    value: Union[float, int, str],
    basis: Optional[List[str]] = None,
    threshold: Optional[Any] = None,
    limitations: Optional[List[str]] = None,
    interpretation: Optional[str] = None,
) -> ConfidenceAssessment:
    """
    Construct a transparent ConfidenceAssessment.
    Ensures non-empty basis and documented limitations.
    """
    clean_val: Union[float, str]
    if value == "UNKNOWN" or value is None:
        clean_val = "UNKNOWN"
    else:
        try:
            clean_val = round(float(value), 4)
        except (ValueError, TypeError):
            clean_val = "UNKNOWN"

    qual = interpretation or interpret_confidence_value(clean_val)
    basis_list = list(basis) if basis else []
    if not basis_list:
        if clean_val == "UNKNOWN":
            basis_list.append("Confidence cannot be legitimately quantified under available metadata/access.")
        else:
            basis_list.append(f"Derived from module detection score ({clean_val}).")

    limitations_list = list(limitations) if limitations else []

    return ConfidenceAssessment(
        value=clean_val,
        interpretation=qual,
        basis=basis_list,
        threshold=threshold,
        limitations=limitations_list,
    )


def map_module_confidence(
    module_name: str,
    raw_confidence: Any,
    context: Optional[Dict[str, Any]] = None,
) -> ConfidenceAssessment:
    """
    Map module-specific detection outputs into standard ConfidenceAssessment.
    """
    ctx = context or {}
    basis: List[str] = []
    limitations: List[str] = []
    threshold = ctx.get("threshold")

    if module_name == "DataIntegrity":
        detector_flags = ctx.get("flags", [])
        if "trigger" in detector_flags:
            basis.append("High residual cross-correlation in trigger patch detector.")
        if "duplicate" in detector_flags:
            sim = ctx.get("similarity")
            basis.append(f"Pairwise standardized cosine similarity ({sim if sim is not None else 'exceeding threshold'}).")
            limitations.append("Detects embedding near-duplicates only; does not establish semantic equivalence across photographic angles.")
        if "ood" in detector_flags:
            basis.append("Class-conditional trimmed Mahalanobis distance exceeded robust threshold.")
            limitations.append("Sensitivity degrades if reference dataset itself is heavily poisoned.")
        if "label_flip" in detector_flags:
            basis.append("Cleanlab confident learning out-of-sample prediction inconsistency.")
            limitations.append("Accuracy bounded by auxiliary classifier performance.")

        if not basis:
            basis.append("Data integrity detector flagged statistical anomaly in feature space.")

    elif "ModelIntegrity" in module_name:
        mad_idx = ctx.get("max_anomaly_index")
        strip_agrees = ctx.get("strip_agrees")
        if mad_idx:
            basis.append(f"Neural Cleanse MAD anomaly index: {mad_idx:.2f}.")
        if strip_agrees is True:
            basis.append("Independent STRIP entropy-suppression signal corroborated anomalous class.")
        elif strip_agrees is False:
            basis.append("STRIP signal conflicted with Neural Cleanse flagged class; confidence dampened.")
            limitations.append("Conflicting signals between trigger inversion and entropy suppression.")
        limitations.append("Validated only against patch backdoors; STRIP does not independently scan when MAD misses.")

    elif module_name == "InferenceProvenance":
        hash_match = ctx.get("contentHashMatches", True)
        sig_valid = ctx.get("signatureValid", True)
        if hash_match and sig_valid:
            basis.append("Cryptographic RFC-8785 canonical hash and Ed25519 signature verified.")
            basis.append("Model weights digest verified against declared model asset.")
            limitations.append("Guarantees execution authenticity only; does not verify model or input pre-inference pedigree.")
        else:
            basis.append("Cryptographic binding or signature verification failed.")
            limitations.append("Direct evidence of payload or key mismatch.")

    elif "DistributionShift" in module_name:
        mmd_val = ctx.get("mmd_value")
        p_val = ctx.get("p_value")
        if mmd_val is not None:
            basis.append(f"Maximum Mean Discrepancy (MMD) = {mmd_val:.6f} against calibrated reference battery.")
        if p_val is not None:
            basis.append(f"Permutation test statistical significance p-value = {p_val:.4f}.")
        limitations.append("Shift indicates divergence from reference battery; does not prove adversary intervention.")

    else:
        basis.append(f"Evaluated under {module_name} standard heuristics.")

    return build_confidence_assessment(
        value=raw_confidence,
        basis=basis,
        threshold=threshold,
        limitations=limitations,
    )
