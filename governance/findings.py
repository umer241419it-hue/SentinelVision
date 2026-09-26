"""
SentinelVision - Canonical Finding & Evidence Normalization.

Converts heterogeneous results from Data Integrity, Model Integrity,
Inference Provenance, and Distribution-Shift into the unified canonical Finding model.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import uuid

from .confidence import build_confidence_assessment, map_module_confidence
from .disposition import determine_disposition
from .schema import (
    CanonicalFinding,
    EvidenceItem,
    FindingCategory,
    FindingStatus,
    GovernanceDisposition,
    Recommendation,
    SeverityLevel,
)


def _load_evidence_json(store_dir: Union[str, Path], evidence_hash: str) -> Optional[Dict[str, Any]]:
    """Attempt to load raw evidence JSON from evidence store by hash."""
    path = Path(store_dir) / f"{evidence_hash}.json"
    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def normalize_data_integrity_finding(
    raw_finding: Dict[str, Any],
    evidence_store_dir: Optional[Union[str, Path]] = None,
) -> CanonicalFinding:
    """
    Normalize a DataIntegrity finding into a CanonicalFinding.
    Supports 9-field signed finding format as well as scan_findings format.
    """
    asset_id = raw_finding.get("assetID") or raw_finding.get("image_id") or f"image-{uuid.uuid4().hex[:8]}"
    reason = raw_finding.get("reason", "Data integrity anomaly flagged.")
    ev_hash = raw_finding.get("evidenceHash") or raw_finding.get("evidence_hash", "")
    timestamp = raw_finding.get("timestamp") or datetime.now(timezone.utc).isoformat()
    raw_conf = raw_finding.get("confidence", 0.65)
    severity = raw_finding.get("severity", "MEDIUM")
    disposition = raw_finding.get("disposition", "REVIEW")
    sig = raw_finding.get("signature")

    # Load raw evidence if available
    ev_details = None
    if ev_hash and evidence_store_dir:
        ev_details = _load_evidence_json(evidence_store_dir, ev_hash)

    evidence_items: List[EvidenceItem] = []
    if ev_hash:
        evidence_items.append(
            EvidenceItem(
                type="evidence_store_artifact",
                reference=f"sha256:{ev_hash}",
                description="Persisted cryptographic evidence JSON in evidence_store",
            )
        )

    # Classify specific flags from reason/evidence
    flags = []
    reason_lower = reason.lower()
    if "duplicate" in reason_lower:
        flags.append("duplicate")
    if "mislabeled" in reason_lower or "flip" in reason_lower:
        flags.append("label_flip")
    if "outlier" in reason_lower or "mahalanobis" in reason_lower or "ood" in reason_lower:
        flags.append("ood")
    if "trigger" in reason_lower:
        flags.append("trigger")

    if ev_details:
        chk_ctx = ev_details.get("check_context", {})
        details_obj = ev_details.get("details", {})
        if "duplicate" in chk_ctx:
            evidence_items.append(
                EvidenceItem(
                    type="duplicate_metric",
                    reference=asset_id,
                    metric="standardized_cosine_similarity",
                    threshold=chk_ctx["duplicate"].get("threshold", 0.99),
                )
            )
        if "ood" in chk_ctx:
            dist = details_obj.get("ood", {}).get("distance")
            thresh = chk_ctx["ood"].get("threshold")
            evidence_items.append(
                EvidenceItem(
                    type="mahalanobis_distance",
                    reference=asset_id,
                    metric="trimmed_mahalanobis_distance",
                    value=dist,
                    threshold=thresh,
                )
            )
        if "label_flip" in chk_ctx:
            lf = details_obj.get("label_flip", {})
            evidence_items.append(
                EvidenceItem(
                    type="label_prediction_discrepancy",
                    reference=asset_id,
                    description=f"Given '{lf.get('given_label')}' vs Predicted '{lf.get('predicted_label')}'",
                    value=lf.get("confidence_label_wrong"),
                )
            )

    # Status mapping
    status = FindingStatus.REVIEW.value
    if severity == SeverityLevel.CRITICAL.value:
        status = FindingStatus.FAIL.value
    elif severity == SeverityLevel.LOW.value and disposition == GovernanceDisposition.ACCEPT.value:
        status = FindingStatus.PASS.value

    # Confidence assessment
    conf = map_module_confidence(
        module_name="DataIntegrity",
        raw_confidence=raw_conf,
        context={"flags": flags, "details": ev_details},
    )

    # Recommendation
    rec = determine_disposition(
        category=FindingCategory.DATA_INTEGRITY.value,
        status=status,
        severity=severity,
        reason=reason,
        evidence_details=ev_details or {},
    )

    limitations = [
        "Cosine duplicate detection catches embedding-level near-duplicates only; does not identify different photographs of the same scene.",
        "Class-conditional Mahalanobis calibration degrades if reference dataset itself is heavily poisoned.",
        "Label error detection depends on auxiliary classifier accuracy.",
        "Statistical findings indicate anomalies, not malicious adversary intent.",
    ]

    finding_id = f"find-di-{hashlib.sha256(asset_id.encode('utf-8')).hexdigest()[:12]}"
    title = f"Data Integrity Anomaly: {asset_id}"

    return CanonicalFinding(
        finding_id=finding_id,
        category=FindingCategory.DATA_INTEGRITY.value,
        asset_id=asset_id,
        status=status,
        severity=severity,
        confidence=conf,
        title=title,
        description=reason,
        evidence=evidence_items,
        affected_scope=f"Sample {asset_id}",
        detection_method="DataIntegrity (Cosine / Mahalanobis / Cleanlab / Trigger Residual)",
        access_assumptions="Image files and annotations available on local filesystem",
        recommendation=rec,
        limitations=limitations,
        timestamp=timestamp,
        module_name="DataIntegrity",
        evidence_hash=ev_hash,
        signature=sig,
    )


def normalize_model_integrity_finding(
    raw_finding: Dict[str, Any],
    evidence_store_dir: Optional[Union[str, Path]] = None,
) -> CanonicalFinding:
    """
    Normalize a ModelIntegrity finding into a CanonicalFinding.
    """
    asset_id = raw_finding.get("assetID", f"model-{uuid.uuid4().hex[:8]}")
    reason = raw_finding.get("reason", "Model integrity behavioral assessment.")
    ev_hash = raw_finding.get("evidenceHash", "")
    timestamp = raw_finding.get("timestamp") or datetime.now(timezone.utc).isoformat()
    raw_conf = raw_finding.get("confidence", 0.50)
    severity = raw_finding.get("severity", "LOW")
    disposition = raw_finding.get("disposition", "ACCEPT")
    sig = raw_finding.get("signature")

    ev_details = None
    if ev_hash and evidence_store_dir:
        ev_details = _load_evidence_json(evidence_store_dir, ev_hash)

    evidence_items: List[EvidenceItem] = []
    if ev_hash:
        evidence_items.append(
            EvidenceItem(
                type="evidence_store_artifact",
                reference=f"sha256:{ev_hash}",
                description="Persisted cryptographic model integrity evidence JSON in evidence_store",
            )
        )

    strip_agrees = None
    max_mad = None
    if ev_details:
        strip_agrees = ev_details.get("strip_agreement")
        nc_mad = ev_details.get("neural_cleanse_mad", {})
        max_mad = nc_mad.get("max_anomaly_index")
        flagged_cls = nc_mad.get("flagged_class")
        if max_mad is not None:
            evidence_items.append(
                EvidenceItem(
                    type="neural_cleanse_mad_index",
                    reference=asset_id,
                    metric="max_anomaly_index",
                    value=max_mad,
                    threshold=2.0,
                    details={"flagged_class": flagged_cls},
                )
            )
        strip_info = ev_details.get("strip", {})
        if strip_info:
            evidence_items.append(
                EvidenceItem(
                    type="strip_entropy_signal",
                    reference=asset_id,
                    description=f"STRIP top class: {strip_info.get('top_class')}, agreement with MAD: {strip_agrees}",
                    value=strip_agrees,
                )
            )

    status = FindingStatus.PASS.value
    if severity == SeverityLevel.CRITICAL.value:
        status = FindingStatus.FAIL.value
    elif severity in (SeverityLevel.HIGH.value, SeverityLevel.MEDIUM.value):
        status = FindingStatus.REVIEW.value

    conf = map_module_confidence(
        module_name="ModelIntegrity",
        raw_confidence=raw_conf,
        context={"max_anomaly_index": max_mad, "strip_agrees": strip_agrees},
    )

    rec = determine_disposition(
        category=FindingCategory.MODEL_INTEGRITY.value,
        status=status,
        severity=severity,
        reason=reason,
        evidence_details=ev_details or {},
    )

    limitations = [
        "White-box weights access was required for trigger inversion.",
        "STRIP operates as dependent corroboration; does not scan independently if Neural Cleanse misses anomalous classes.",
        "Validated exclusively against patch-style backdoors (BadNets); blended or dynamic perturbations are unsupported.",
    ]

    finding_id = f"find-mi-{hashlib.sha256(asset_id.encode('utf-8')).hexdigest()[:12]}"
    title = f"Model Integrity Assessment: {asset_id}"

    return CanonicalFinding(
        finding_id=finding_id,
        category=FindingCategory.MODEL_INTEGRITY.value,
        asset_id=asset_id,
        status=status,
        severity=severity,
        confidence=conf,
        title=title,
        description=reason,
        evidence=evidence_items,
        affected_scope=f"Model Weights {asset_id}",
        detection_method="ModelIntegrity (Neural Cleanse + MAD + STRIP)",
        access_assumptions="White-box PyTorch model weights access",
        recommendation=rec,
        limitations=limitations,
        timestamp=timestamp,
        module_name="ModelIntegrity",
        evidence_hash=ev_hash,
        signature=sig,
    )


def normalize_inference_seal_finding(
    seal_record: Dict[str, Any],
    verification_result: Dict[str, Any],
    expected_model_digest: Optional[str] = None,
) -> CanonicalFinding:
    """
    Normalize an InferenceProvenance seal and its verification result into a CanonicalFinding.
    """
    seal_id = seal_record.get("sealID", f"seal-{uuid.uuid4().hex[:8]}")
    model_asset_id = seal_record.get("modelAssetID", "unknown-model")
    input_hash = seal_record.get("inputHash", "unknown-input-hash")
    model_digest = seal_record.get("modelDigest", "unknown-model-digest")
    nonce = seal_record.get("nonce", "")
    timestamp = seal_record.get("timestamp") or datetime.now(timezone.utc).isoformat()
    output_summary = seal_record.get("outputSummary", {})

    content_hash_matches = verification_result.get("contentHashMatches", False)
    signature_valid = verification_result.get("signatureValid", False)
    verdict = verification_result.get("verdict", "TAMPERED")
    error = verification_result.get("error")

    # Model digest check against declared reference if provided
    model_digest_matches = True
    if expected_model_digest and model_digest != expected_model_digest:
        model_digest_matches = False

    evidence_items = [
        EvidenceItem(
            type="sealed_inference_record",
            reference=seal_id,
            description="Cryptographic sealed inference output",
            details={
                "modelAssetID": model_asset_id,
                "inputHash": input_hash,
                "modelDigest": model_digest,
                "nonce": nonce,
                "outputSummary": output_summary,
            },
        ),
        EvidenceItem(
            type="cryptographic_verification",
            reference=f"ed25519:{seal_record.get('signature', '')[:16]}...",
            description="RFC-8785 canonical hash and Ed25519 signature verification",
            metric="verdict",
            value=verdict,
            details={
                "contentHashMatches": content_hash_matches,
                "signatureValid": signature_valid,
                "error": error,
            },
        ),
    ]
    if expected_model_digest:
        evidence_items.append(
            EvidenceItem(
                type="model_digest_binding",
                reference=model_digest,
                description=f"Model digest matches declared reference ({model_digest_matches})",
                value=model_digest_matches,
                threshold=expected_model_digest,
            )
        )

    is_valid = (verdict == "VALID") and model_digest_matches
    if is_valid:
        status = FindingStatus.PASS.value
        severity = SeverityLevel.LOW.value
        title = f"Inference Output Authenticity Verified: {seal_id}"
        description = f"Cryptographic seal {seal_id} verified. Model digest, input tensor hash, config, and output binding are authentic."
        conf = build_confidence_assessment(
            value=1.0,
            interpretation="HIGH",
            basis=[
                "Cryptographic RFC-8785 canonical hash verified.",
                "Ed25519 signature validated against InferenceProvenance public key registry.",
                "Model weights digest confirmed.",
            ],
            limitations=["Execution authenticity guaranteed; pre-inference sensory pedigree unverified."],
        )
        rec = Recommendation(
            disposition=GovernanceDisposition.ACCEPT.value,
            reason="Inference seal is cryptographically valid and authentic.",
            suggested_action="Inference result cleared for downstream automated consumption.",
            priority="ROUTINE",
        )
    else:
        status = FindingStatus.FAIL.value
        severity = SeverityLevel.CRITICAL.value
        title = f"Inference Tampering Detected: {seal_id}"
        reasons = []
        if not content_hash_matches:
            reasons.append("RFC-8785 canonical content hash mismatch (payload modified post-signing)")
        if not signature_valid:
            reasons.append("Ed25519 signature invalid or signer key mismatch")
        if not model_digest_matches:
            reasons.append(f"Model digest substitution detected: {model_digest} != expected {expected_model_digest}")
        if error:
            reasons.append(str(error))

        description = f"Integrity violation on inference record {seal_id}: " + "; ".join(reasons)
        conf = build_confidence_assessment(
            value=1.0,
            interpretation="HIGH",
            basis=["Direct mathematical failure in cryptographic hash or signature verification."],
            limitations=["Cryptographic proof of tampering; identity of modifying actor is out-of-band."],
        )
        rec = Recommendation(
            disposition=GovernanceDisposition.QUARANTINE.value,
            reason=description,
            suggested_action="QUARANTINE inference output immediately. Investigate potential model substitution or man-in-the-middle tampering.",
            priority="URGENT",
        )

    finding_id = f"find-inf-{hashlib.sha256(seal_id.encode('utf-8')).hexdigest()[:12]}"

    return CanonicalFinding(
        finding_id=finding_id,
        category=FindingCategory.INFERENCE_PROVENANCE.value,
        asset_id=seal_id,
        status=status,
        severity=severity,
        confidence=conf,
        title=title,
        description=description,
        evidence=evidence_items,
        affected_scope=f"Inference Seal {seal_id} (Model {model_asset_id})",
        detection_method="InferenceProvenance (Ed25519 / RFC-8785 Canonical JSON / SHA-256)",
        access_assumptions="Sealed inference JSON records with registered public key",
        recommendation=rec,
        limitations=["Guarantees post-execution non-repudiation; does not inspect input image acquisition sensor."],
        timestamp=timestamp,
        module_name="InferenceProvenance",
        evidence_hash=seal_record.get("contentHash"),
        signature=seal_record.get("signature"),
    )


def normalize_drift_finding(
    drift_result: Dict[str, Any],
    run_meta: Optional[Dict[str, Any]] = None,
    evidence_store_dir: Optional[Union[str, Path]] = None,
) -> CanonicalFinding:
    """
    Normalize a DistributionShift result/finding into a CanonicalFinding.
    """
    window_id = drift_result.get("window_id", f"win-{uuid.uuid4().hex[:8]}")
    assessment = drift_result.get("assessment", "NO_SIGNIFICANT_SHIFT")
    mmd_info = drift_result.get("mmd", {})
    mmd_val = mmd_info.get("statistic", 0.0)
    p_val = mmd_info.get("p_value", 1.0)
    threshold = mmd_info.get("threshold", 0.01)
    diag = drift_result.get("diagnostics", {})
    image_count = drift_result.get("image_count", 0)

    # Check for attached 9-field finding
    finding_obj = drift_result.get("finding", {})
    ev_hash = finding_obj.get("evidenceHash") or drift_result.get("evidence_hash", "")
    sig = finding_obj.get("signature")
    timestamp = finding_obj.get("timestamp") or (run_meta.get("run_timestamp") if run_meta else None) or datetime.now(timezone.utc).isoformat()

    evidence_items = [
        EvidenceItem(
            type="mmd_drift_metric",
            reference=window_id,
            description="Maximum Mean Discrepancy (MMD) with RBF kernel against reference battery",
            metric="MMD",
            value=round(float(mmd_val), 6) if isinstance(mmd_val, (int, float)) else mmd_val,
            threshold=round(float(threshold), 6) if isinstance(threshold, (int, float)) else threshold,
            details={"p_value": p_val, "image_count": image_count},
        )
    ]
    if ev_hash:
        evidence_items.append(
            EvidenceItem(
                type="evidence_store_artifact",
                reference=f"sha256:{ev_hash}",
                description="Persisted cryptographic drift evidence JSON in evidence_store",
            )
        )
    if diag:
        evidence_items.append(
            EvidenceItem(
                type="operational_drift_diagnostics",
                reference=window_id,
                description="Measurable operational image statistics",
                details=diag,
            )
        )

    # Map assessment to status and severity
    if assessment == "NO_SIGNIFICANT_SHIFT":
        status = FindingStatus.PASS.value
        severity = SeverityLevel.LOW.value
        disposition = GovernanceDisposition.ACCEPT.value
        reason = f"MMD statistic ({mmd_val:.6f}) is within calibrated reference variation (threshold {threshold:.6f})."
    elif assessment == "OPERATIONAL_SHIFT_LIKELY":
        status = FindingStatus.WARNING.value
        severity = SeverityLevel.MEDIUM.value
        disposition = GovernanceDisposition.REVIEW.value
        reason = f"Statistically significant distribution shift detected (MMD {mmd_val:.6f} > {threshold:.6f}), correlated with operational lighting/sensor change."
    elif assessment == "UNEXPLAINED_SHIFT":
        status = FindingStatus.REVIEW.value
        severity = SeverityLevel.HIGH.value
        disposition = GovernanceDisposition.REVIEW.value
        reason = f"Statistically significant distribution shift detected (MMD {mmd_val:.6f} > {threshold:.6f}) without clear operational sensor explanation."
    else:  # INSUFFICIENT_EVIDENCE
        status = FindingStatus.NOT_ASSESSED.value
        severity = SeverityLevel.LOW.value
        disposition = GovernanceDisposition.REVIEW.value
        reason = "Insufficient samples or calibration metadata to assess distribution drift."

    conf = map_module_confidence(
        module_name="DistributionShift",
        raw_confidence=finding_obj.get("confidence", 0.75 if status != FindingStatus.PASS.value else 0.90),
        context={"mmd_value": mmd_val, "p_value": p_val, "threshold": threshold},
    )

    rec = determine_disposition(
        category=FindingCategory.DISTRIBUTION_SHIFT.value,
        status=status,
        severity=severity,
        reason=reason,
        evidence_details={"diagnostics": diag, "reason": reason},
    )

    limitations = [
        "A distribution shift does NOT prove malicious manipulation or identify an adversary.",
        "Threshold validity depends on reference battery representativeness and frozen embedding extractor.",
        "Surfaced for human analyst review to distinguish benign operational drift from adversarial data poisoning.",
    ]

    finding_id = f"find-drift-{hashlib.sha256(window_id.encode('utf-8')).hexdigest()[:12]}"
    title = f"Distribution Shift Assessment: {window_id} ({assessment})"

    return CanonicalFinding(
        finding_id=finding_id,
        category=FindingCategory.DISTRIBUTION_SHIFT.value,
        asset_id=window_id,
        status=status,
        severity=severity,
        confidence=conf,
        title=title,
        description=reason,
        evidence=evidence_items,
        affected_scope=f"Live Window {window_id} ({image_count} samples)",
        detection_method="DistributionShift (MMD-RBF with Permutation Test)",
        access_assumptions="Reference battery embeddings and live window image batches",
        recommendation=rec,
        limitations=limitations,
        timestamp=timestamp,
        module_name="DistributionShift",
        evidence_hash=ev_hash,
        signature=sig,
    )
