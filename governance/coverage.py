"""
SentinelVision - Platform Coverage & Attack-Class Declarations.

Maintains the authoritative registry of assurance capabilities and attack-class coverage,
honestly reflecting partial implementations, known limitations, and unsupported threats.
"""

from typing import Any, Dict, List, Optional
from .schema import (
    AttackClass,
    AttackClassCoverage,
    CapabilityCoverage,
    CoverageMatrix,
    SupportStatus,
)

SYSTEM_CAPABILITY_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "capability": "Label Anomaly & Flip Detection",
        "support_status": SupportStatus.PARTIALLY_SUPPORTED.value,
        "access_required": "Dataset images + annotations",
        "evidence_types": ["confident_learning_discrepancy", "cross_validation_probabilities"],
        "description": "Flags label flipping via cleanlab confident learning on standardized pixelstat/ResNet embeddings.",
    },
    {
        "capability": "Near-Duplicate Flooding Detection",
        "support_status": SupportStatus.PARTIALLY_SUPPORTED.value,
        "access_required": "Dataset images",
        "evidence_types": ["pairwise_cosine_similarity", "duplicate_cluster_manifest"],
        "description": "Identifies exact and transformed image duplicates by pairwise standardized cosine similarity on embeddings.",
    },
    {
        "capability": "Out-of-Distribution Insertion Detection",
        "support_status": SupportStatus.PARTIALLY_SUPPORTED.value,
        "access_required": "Dataset images + clean calibration subset",
        "evidence_types": ["mahalanobis_distance", "class_conditional_threshold"],
        "description": "Calculates class-conditional trimmed Mahalanobis distance in embedding space against robust calibration.",
    },
    {
        "capability": "Training Data Trigger Patch Detection",
        "support_status": SupportStatus.PARTIALLY_SUPPORTED.value,
        "access_required": "Dataset images + candidate labels",
        "evidence_types": ["patch_residual_cross_correlation", "visual_residual_artifact"],
        "description": "Detects localized high-frequency trigger patterns across sample subsets using residual cross-correlation.",
    },
    {
        "capability": "Model Trojan & Backdoor Inversion",
        "support_status": SupportStatus.PARTIALLY_SUPPORTED.value,
        "access_required": "White-box model weights (PyTorch .pt) + calibration sample data",
        "evidence_types": ["neural_cleanse_mad_index", "strip_entropy_deficit", "inverted_patch_manifest"],
        "description": "Per-class trigger inversion with Median Absolute Deviation (MAD) anomaly scoring, corroborated by STRIP entropy testing.",
    },
    {
        "capability": "Model Substitution & Tamper Detection",
        "support_status": SupportStatus.SUPPORTED.value,
        "access_required": "Model weights file + reference registry / seal digest",
        "evidence_types": ["sha256_model_digest", "registry_signature"],
        "description": "Verifies cryptographic SHA-256 weight hash against signed registry and inference provenance seals.",
    },
    {
        "capability": "Inference Output Sealing & Provenance",
        "support_status": SupportStatus.SUPPORTED.value,
        "access_required": "Sealed inference records (9 signed fields + RFC-8785 canonical hash)",
        "evidence_types": ["ed25519_signature", "rfc8785_content_hash", "input_tensor_hash"],
        "description": "Verifies immutable cryptographic binding among input tensor, model digest, execution config, nonce, and output.",
    },
    {
        "capability": "Inference Replay Detection",
        "support_status": SupportStatus.SUPPORTED.value,
        "access_required": "Inference nonce / sequence metadata + ledger state",
        "evidence_types": ["cryptographic_nonce", "duplicate_evidence_hash_guard"],
        "description": "Enforces per-execution 128-bit cryptographic nonces and duplicate evidence hash rejection on ledger.",
    },
    {
        "capability": "Distribution Shift & Drift Monitoring",
        "support_status": SupportStatus.SUPPORTED.value,
        "access_required": "Reference battery embeddings + live window images",
        "evidence_types": ["maximum_mean_discrepancy_rbf", "permutation_p_value", "diagnostic_metrics"],
        "description": "Calculates MMD with RBF kernel against reference battery with null-calibrated threshold and operational diagnostics.",
    },
    {
        "capability": "Contributor & Provenance Risk Aggregation",
        "support_status": SupportStatus.PARTIALLY_SUPPORTED.value,
        "access_required": "Multi-contributor provenance metadata (contributor, source, batch IDs)",
        "evidence_types": ["group_concentration_ratio", "systematic_confusion_matrix"],
        "description": "Aggregates sample findings across contributor/batch dimensions to detect systematic contributor misbehavior.",
    },
]

ATTACK_CLASS_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "attack_class": AttackClass.LABEL_FLIPPING.value,
        "support_status": SupportStatus.PARTIALLY_SUPPORTED.value,
        "detection_method": "Cleanlab confident learning with cross-validated KNN/classifier on embeddings",
        "required_access": "Dataset images and annotations",
        "confidence_limitations": "Accuracy depends on auxiliary classifier; fails on label errors indistinguishable in embedding space.",
    },
    {
        "attack_class": AttackClass.SYSTEMATIC_MISLABELING.value,
        "support_status": SupportStatus.PARTIALLY_SUPPORTED.value,
        "detection_method": "Provenance aggregator confusion matrix across contributor/batch groups",
        "required_access": "Dataset annotations and multi-contributor provenance metadata",
        "confidence_limitations": "Requires contributor metadata; cannot detect if mislabeling is uniformly distributed across all contributors.",
    },
    {
        "attack_class": AttackClass.DUPLICATE_FLOODING.value,
        "support_status": SupportStatus.PARTIALLY_SUPPORTED.value,
        "detection_method": "Pairwise standardized cosine similarity on frozen pixelstat/ResNet embeddings",
        "required_access": "Dataset images",
        "confidence_limitations": "Detects embedding near-duplicates (compression, crops); does not detect different photographs of identical scenes.",
    },
    {
        "attack_class": AttackClass.OUT_OF_DISTRIBUTION_INSERTION.value,
        "support_status": SupportStatus.PARTIALLY_SUPPORTED.value,
        "detection_method": "Class-conditional trimmed Mahalanobis distance with held-out robust calibration",
        "required_access": "Dataset images and clean calibration subset",
        "confidence_limitations": "Reference is fit with trimming; sensitivity degrades if training pool is heavily poisoned.",
    },
    {
        "attack_class": AttackClass.TRIGGER_INJECTION.value,
        "support_status": SupportStatus.PARTIALLY_SUPPORTED.value,
        "detection_method": "Patch residual cross-correlation in data; Neural Cleanse trigger inversion in models",
        "required_access": "Images + candidate labels (data) or model weights + sample inputs (model)",
        "confidence_limitations": "Validated only against localized patch triggers (BadNets style); blended or dynamic triggers are unsupported.",
    },
    {
        "attack_class": AttackClass.BACKDOOR_BEHAVIOUR.value,
        "support_status": SupportStatus.PARTIALLY_SUPPORTED.value,
        "detection_method": "Neural Cleanse trigger norm optimization + MAD anomaly index corroborated by STRIP entropy testing",
        "required_access": "White-box model weights and example clean calibration samples",
        "confidence_limitations": "White-box access mandatory. STRIP only tests classes MAD flags; does not run whole-model independent detector.",
    },
    {
        "attack_class": AttackClass.MODEL_SUBSTITUTION.value,
        "support_status": SupportStatus.SUPPORTED.value,
        "detection_method": "SHA-256 model weights digest verification against registered identity and inference seal",
        "required_access": "Model weights file and registered digest",
        "confidence_limitations": "Requires authoritative baseline model digest in registry.",
    },
    {
        "attack_class": AttackClass.MODEL_MODIFICATION.value,
        "support_status": SupportStatus.SUPPORTED.value,
        "detection_method": "Cryptographic digest binding and read-time signature verification",
        "required_access": "Model weights file and registered module public keys",
        "confidence_limitations": "Catches any bit-level modification; does not assess semantic behavior of unverified models.",
    },
    {
        "attack_class": AttackClass.INFERENCE_TAMPERING.value,
        "support_status": SupportStatus.SUPPORTED.value,
        "detection_method": "Ed25519 digital signature over RFC-8785 canonical JSON of 9 inference fields",
        "required_access": "Sealed inference record and public key registry",
        "confidence_limitations": "Guarantees post-execution non-repudiation; does not certify raw sensory pedigree before tensor ingestion.",
    },
    {
        "attack_class": AttackClass.INFERENCE_REPLAY.value,
        "support_status": SupportStatus.SUPPORTED.value,
        "detection_method": "128-bit cryptographic nonces in sealed records + ledger duplicate evidenceHash guards",
        "required_access": "Sealed inference record and ledger world state",
        "confidence_limitations": "Replay guard prevents byte-identical evidence reuse; does not perform session freshness timeout checks.",
    },
    {
        "attack_class": AttackClass.DISTRIBUTION_SHIFT.value,
        "support_status": SupportStatus.SUPPORTED.value,
        "detection_method": "Maximum Mean Discrepancy (MMD) with RBF kernel and permutation testing vs calibrated reference battery",
        "required_access": "Reference battery embeddings and live window image batches",
        "confidence_limitations": "Detects statistical divergence; cannot independently establish whether shift is natural drift or adversarial insertion.",
    },
    {
        "attack_class": AttackClass.CONTRIBUTOR_RISK_AGGREGATION.value,
        "support_status": SupportStatus.PARTIALLY_SUPPORTED.value,
        "detection_method": "Hypergeometric / binomial concentration testing across provenance metadata dimensions",
        "required_access": "Multi-contributor provenance metadata records",
        "confidence_limitations": "Depends on accurate upstream contributor/batch tagging; cannot detect collusion across disparate contributor IDs.",
    },
    {
        "attack_class": "ADVERSARIAL_EVASION_PATCH",
        "support_status": SupportStatus.UNSUPPORTED.value,
        "detection_method": "None (unsupported in current release)",
        "required_access": "N/A",
        "confidence_limitations": "Adversarial test-time evasion patches (e.g. AdvPatch, optical illusions) are not detected by current static/drift modules.",
    },
    {
        "attack_class": "MODEL_EXTRACTION_STEALING",
        "support_status": SupportStatus.UNSUPPORTED.value,
        "detection_method": "None (unsupported in current release)",
        "required_access": "N/A",
        "confidence_limitations": "Query-rate model stealing and API extraction monitoring are not implemented in the offline integrity architecture.",
    },
]


def build_coverage_matrix(
    executed_findings: Optional[List[Dict[str, Any]]] = None,
    active_capabilities: Optional[List[str]] = None,
) -> CoverageMatrix:
    """
    Build dynamic CoverageMatrix correlating executed findings with capabilities.
    """
    findings = executed_findings or []
    capabilities = []
    for cap_def in SYSTEM_CAPABILITY_DEFINITIONS:
        cap = CapabilityCoverage(
            capability=cap_def["capability"],
            support_status=cap_def["support_status"],
            access_required=cap_def["access_required"],
            evidence_types=list(cap_def["evidence_types"]),
            description=cap_def["description"],
            finding_ids=[],
        )
        capabilities.append(cap)

    attack_classes = []
    for atk_def in ATTACK_CLASS_DEFINITIONS:
        atk = AttackClassCoverage(
            attack_class=atk_def["attack_class"],
            support_status=atk_def["support_status"],
            detection_method=atk_def["detection_method"],
            required_access=atk_def["required_access"],
            confidence_limitations=atk_def["confidence_limitations"],
            finding_ids=[],
        )
        attack_classes.append(atk)

    # Correlate findings to capabilities and attack classes
    for f in findings:
        fid = f.get("finding_id") or f.get("asset_id") or "finding"
        cat = f.get("category", "")
        method = f.get("detection_method", "")
        reason = f.get("reason", "") or f.get("description", "")

        for cap in capabilities:
            if cat in ("DATA_INTEGRITY", "COVERAGE") and ("Label" in cap.capability or "Duplicate" in cap.capability or "Distribution" in cap.capability):
                cap.finding_ids.append(fid)
            elif cat == "MODEL_INTEGRITY" and "Model" in cap.capability:
                cap.finding_ids.append(fid)
            elif cat in ("INFERENCE_PROVENANCE", "OUTPUT_TAMPERING") and ("Inference" in cap.capability or "Replay" in cap.capability):
                cap.finding_ids.append(fid)
            elif cat == "DISTRIBUTION_SHIFT" and "Distribution Shift" in cap.capability:
                cap.finding_ids.append(fid)

        for atk in attack_classes:
            if "duplicate" in reason.lower() and atk.attack_class == AttackClass.DUPLICATE_FLOODING.value:
                atk.finding_ids.append(fid)
            elif "flip" in reason.lower() and atk.attack_class == AttackClass.LABEL_FLIPPING.value:
                atk.finding_ids.append(fid)
            elif "ood" in reason.lower() and atk.attack_class == AttackClass.OUT_OF_DISTRIBUTION_INSERTION.value:
                atk.finding_ids.append(fid)
            elif "trigger" in reason.lower() and atk.attack_class == AttackClass.TRIGGER_INJECTION.value:
                atk.finding_ids.append(fid)
            elif "trojan" in reason.lower() and atk.attack_class == AttackClass.BACKDOOR_BEHAVIOUR.value:
                atk.finding_ids.append(fid)
            elif ("tamper" in reason.lower() or "seal" in reason.lower()) and atk.attack_class == AttackClass.INFERENCE_TAMPERING.value:
                atk.finding_ids.append(fid)
            elif "shift" in reason.lower() and atk.attack_class == AttackClass.DISTRIBUTION_SHIFT.value:
                atk.finding_ids.append(fid)

    return CoverageMatrix(capabilities=capabilities, attack_classes=attack_classes)
