"""
SentinelVision - Canonical Assurance Report & Governance Schema.

Defines the versioned, extensible schema for findings, evidence, coverage,
audit trails, and unified assurance reports.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Union

SCHEMA_VERSION = "1.0.0"


class FindingCategory(str, Enum):
    DATA_INTEGRITY = "DATA_INTEGRITY"
    MODEL_INTEGRITY = "MODEL_INTEGRITY"
    INFERENCE_PROVENANCE = "INFERENCE_PROVENANCE"
    OUTPUT_TAMPERING = "OUTPUT_TAMPERING"
    DISTRIBUTION_SHIFT = "DISTRIBUTION_SHIFT"
    AUDIT = "AUDIT"
    CONFIGURATION = "CONFIGURATION"
    COVERAGE = "COVERAGE"


class FindingStatus(str, Enum):
    PASS = "PASS"
    INFO = "INFO"
    REVIEW = "REVIEW"
    WARNING = "WARNING"
    FAIL = "FAIL"
    NOT_ASSESSED = "NOT_ASSESSED"


class SeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


class GovernanceDisposition(str, Enum):
    ACCEPT = "ACCEPT"
    REVIEW = "REVIEW"
    QUARANTINE = "QUARANTINE"


class OverallStatus(str, Enum):
    PASS = "PASS"
    PASS_WITH_LIMITATIONS = "PASS_WITH_LIMITATIONS"
    REVIEW = "REVIEW"
    FAIL = "FAIL"
    NOT_ASSESSED = "NOT_ASSESSED"


class SupportStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_ASSESSED = "NOT_ASSESSED"


class AttackClass(str, Enum):
    LABEL_FLIPPING = "LABEL_FLIPPING"
    SYSTEMATIC_MISLABELING = "SYSTEMATIC_MISLABELING"
    DUPLICATE_FLOODING = "DUPLICATE_FLOODING"
    OUT_OF_DISTRIBUTION_INSERTION = "OUT_OF_DISTRIBUTION_INSERTION"
    TRIGGER_INJECTION = "TRIGGER_INJECTION"
    BACKDOOR_BEHAVIOUR = "BACKDOOR_BEHAVIOUR"
    MODEL_SUBSTITUTION = "MODEL_SUBSTITUTION"
    MODEL_MODIFICATION = "MODEL_MODIFICATION"
    INFERENCE_TAMPERING = "INFERENCE_TAMPERING"
    INFERENCE_REPLAY = "INFERENCE_REPLAY"
    DISTRIBUTION_SHIFT = "DISTRIBUTION_SHIFT"
    CONTRIBUTOR_RISK_AGGREGATION = "CONTRIBUTOR_RISK_AGGREGATION"


@dataclass
class EvidenceItem:
    """Stable evidence reference attached to a finding."""
    type: str
    reference: str
    description: Optional[str] = None
    metric: Optional[str] = None
    value: Optional[Union[float, int, str, bool]] = None
    threshold: Optional[Union[float, int, str]] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "type": self.type,
            "reference": self.reference,
        }
        if self.description is not None:
            d["description"] = self.description
        if self.metric is not None:
            d["metric"] = self.metric
        if self.value is not None:
            d["value"] = self.value
        if self.threshold is not None:
            d["threshold"] = self.threshold
        if self.details is not None:
            d["details"] = self.details
        return d


@dataclass
class ConfidenceAssessment:
    """Transparent confidence explanation."""
    value: Union[float, str]  # float in [0.0, 1.0] or "UNKNOWN"
    interpretation: str       # HIGH, MEDIUM, LOW, UNKNOWN
    basis: List[str] = field(default_factory=list)
    threshold: Optional[Any] = None
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "interpretation": self.interpretation,
            "basis": list(self.basis),
            "threshold": self.threshold,
            "limitations": list(self.limitations),
        }


@dataclass
class Recommendation:
    """Actionable recommendation for analysts."""
    disposition: str  # ACCEPT, REVIEW, QUARANTINE
    reason: str
    suggested_action: str
    priority: str = "ROUTINE"  # ROUTINE, ELEVATED, URGENT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "disposition": self.disposition,
            "reason": self.reason,
            "suggested_action": self.suggested_action,
            "priority": self.priority,
        }


@dataclass
class CanonicalFinding:
    """Canonical finding schema uniting all modules."""
    finding_id: str
    category: str
    asset_id: str
    status: str
    severity: str
    confidence: ConfidenceAssessment
    title: str
    description: str
    evidence: List[EvidenceItem]
    affected_scope: str
    detection_method: str
    access_assumptions: str
    recommendation: Recommendation
    limitations: List[str]
    timestamp: str
    module_name: Optional[str] = None
    evidence_hash: Optional[str] = None
    signature: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "category": str(self.category),
            "asset_id": str(self.asset_id),
            "status": str(self.status),
            "severity": str(self.severity),
            "confidence": self.confidence.to_dict() if isinstance(self.confidence, ConfidenceAssessment) else self.confidence,
            "title": str(self.title),
            "description": str(self.description),
            "evidence": [e.to_dict() if isinstance(e, EvidenceItem) else e for e in self.evidence],
            "affected_scope": str(self.affected_scope),
            "detection_method": str(self.detection_method),
            "access_assumptions": str(self.access_assumptions),
            "recommendation": self.recommendation.to_dict() if isinstance(self.recommendation, Recommendation) else self.recommendation,
            "limitations": list(self.limitations),
            "timestamp": str(self.timestamp),
            "module_name": self.module_name,
            "evidence_hash": self.evidence_hash,
            "signature": self.signature,
        }


@dataclass
class CheckRecord:
    """Record of an individual integrity check executed or skipped."""
    check_id: str
    category: str
    name: str
    module: str
    description: str
    execution_status: str  # COMPLETED, FAILED, SKIPPED, NOT_ASSESSED
    timestamp: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    findings_generated: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "category": self.category,
            "name": self.name,
            "module": self.module,
            "description": self.description,
            "execution_status": self.execution_status,
            "timestamp": self.timestamp,
            "parameters": self.parameters,
            "findings_generated": self.findings_generated,
        }


@dataclass
class OverallAssessment:
    """Overall pipeline assessment."""
    overall_status: str  # PASS, PASS_WITH_LIMITATIONS, REVIEW, FAIL, NOT_ASSESSED
    disposition: str     # ACCEPT, REVIEW, QUARANTINE
    summary: str
    critical_findings: int
    warning_findings: int
    review_findings: int
    pass_findings: int
    not_assessed: int
    basis: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "disposition": self.disposition,
            "summary": self.summary,
            "critical_findings": self.critical_findings,
            "warning_findings": self.warning_findings,
            "review_findings": self.review_findings,
            "pass_findings": self.pass_findings,
            "not_assessed": self.not_assessed,
            "basis": list(self.basis),
        }


@dataclass
class CapabilityCoverage:
    """Individual assurance capability coverage declaration."""
    capability: str
    support_status: str  # SUPPORTED, PARTIALLY_SUPPORTED, UNSUPPORTED, NOT_ASSESSED
    access_required: str
    evidence_types: List[str]
    description: str
    finding_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "support_status": self.support_status,
            "access_required": self.access_required,
            "evidence_types": list(self.evidence_types),
            "description": self.description,
            "finding_ids": list(self.finding_ids),
        }


@dataclass
class AttackClassCoverage:
    """Coverage declaration for specific threat/attack class."""
    attack_class: str
    support_status: str  # SUPPORTED, PARTIALLY_SUPPORTED, UNSUPPORTED, NOT_ASSESSED
    detection_method: str
    required_access: str
    confidence_limitations: str
    finding_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attack_class": self.attack_class,
            "support_status": self.support_status,
            "detection_method": self.detection_method,
            "required_access": self.required_access,
            "confidence_limitations": self.confidence_limitations,
            "finding_ids": list(self.finding_ids),
        }


@dataclass
class CoverageMatrix:
    """Full coverage statement and attack class declarations."""
    capabilities: List[CapabilityCoverage] = field(default_factory=list)
    attack_classes: List[AttackClassCoverage] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capabilities": [c.to_dict() if isinstance(c, CapabilityCoverage) else c for c in self.capabilities],
            "attack_classes": [a.to_dict() if isinstance(a, AttackClassCoverage) else a for a in self.attack_classes],
        }


@dataclass
class AssuranceReport:
    """The canonical machine-readable assurance report."""
    schema_version: str
    assessment_id: str
    assessment_timestamp: str
    system: Dict[str, Any]
    assets: Dict[str, Any]
    access_profile: Dict[str, Any]
    checks: List[CheckRecord]
    findings: List[CanonicalFinding]
    overall_assessment: OverallAssessment
    coverage: CoverageMatrix
    limitations: List[str]
    recommendations: List[Dict[str, Any]]
    audit: Dict[str, Any]
    reproducibility: Dict[str, Any]
    report_integrity: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "schema_version": self.schema_version,
            "assessment_id": self.assessment_id,
            "assessment_timestamp": self.assessment_timestamp,
            "system": self.system,
            "assets": self.assets,
            "access_profile": self.access_profile,
            "checks": [c.to_dict() if isinstance(c, CheckRecord) else c for c in self.checks],
            "findings": [f.to_dict() if isinstance(f, CanonicalFinding) else f for f in self.findings],
            "overall_assessment": self.overall_assessment.to_dict() if isinstance(self.overall_assessment, OverallAssessment) else self.overall_assessment,
            "coverage": self.coverage.to_dict() if isinstance(self.coverage, CoverageMatrix) else self.coverage,
            "limitations": list(self.limitations),
            "recommendations": list(self.recommendations),
            "audit": self.audit,
            "reproducibility": self.reproducibility,
        }
        if self.report_integrity is not None:
            data["report_integrity"] = self.report_integrity
        return data


def validate_report_dict(report: Dict[str, Any]) -> List[str]:
    """
    Validate a raw report dictionary against canonical schema constraints.
    Returns a list of validation error strings (empty if valid).
    """
    errors = []
    required_top = [
        "schema_version",
        "assessment_id",
        "assessment_timestamp",
        "system",
        "assets",
        "access_profile",
        "checks",
        "findings",
        "overall_assessment",
        "coverage",
        "limitations",
        "recommendations",
        "audit",
        "reproducibility",
    ]
    for key in required_top:
        if key not in report or report[key] is None:
            errors.append(f"Missing required top-level field: '{key}'")

    if "schema_version" in report:
        ver = str(report["schema_version"])
        if not re.match(r"^\d+\.\d+(\.\d+)?$", ver):
            errors.append(f"Invalid schema_version format: '{ver}' (expected 'X.Y' or 'X.Y.Z')")

    if "overall_assessment" in report and isinstance(report["overall_assessment"], dict):
        oa = report["overall_assessment"]
        status = oa.get("overall_status")
        valid_statuses = {s.value for s in OverallStatus}
        if status not in valid_statuses:
            errors.append(f"Invalid overall_status: '{status}'. Allowed: {sorted(valid_statuses)}")
        disp = oa.get("disposition")
        valid_disps = {d.value for d in GovernanceDisposition}
        if disp not in valid_disps:
            errors.append(f"Invalid overall disposition: '{disp}'. Allowed: {sorted(valid_disps)}")

    if "findings" in report and isinstance(report["findings"], list):
        valid_categories = {c.value for c in FindingCategory}
        valid_finding_statuses = {s.value for s in FindingStatus}
        valid_severities = {s.value for s in SeverityLevel}
        valid_disps = {d.value for d in GovernanceDisposition}

        for idx, f in enumerate(report["findings"]):
            prefix = f"findings[{idx}] ({f.get('finding_id', 'unknown')})"
            for f_key in ["finding_id", "category", "asset_id", "status", "severity", "confidence", "title", "description", "evidence", "recommendation"]:
                if f_key not in f or f[f_key] is None:
                    errors.append(f"{prefix}: missing required field '{f_key}'")

            if f.get("category") and f["category"] not in valid_categories:
                errors.append(f"{prefix}: invalid category '{f['category']}'")
            if f.get("status") and f["status"] not in valid_finding_statuses:
                errors.append(f"{prefix}: invalid status '{f['status']}'")
            if f.get("severity") and f["severity"] not in valid_severities:
                errors.append(f"{prefix}: invalid severity '{f['severity']}'")

            conf = f.get("confidence")
            if isinstance(conf, dict):
                val = conf.get("value")
                if val != "UNKNOWN":
                    try:
                        fv = float(val)
                        if not (0.0 <= fv <= 1.0):
                            errors.append(f"{prefix}: confidence value {fv} out of range [0.0, 1.0]")
                    except (ValueError, TypeError):
                        errors.append(f"{prefix}: invalid confidence value '{val}'")
            elif conf is not None:
                errors.append(f"{prefix}: confidence must be an object with value, interpretation, basis")

            rec = f.get("recommendation")
            if isinstance(rec, dict):
                disp = rec.get("disposition")
                if disp not in valid_disps:
                    errors.append(f"{prefix}: invalid recommendation disposition '{disp}'")

    if "audit" in report and isinstance(report["audit"], dict):
        audit = report["audit"]
        if "chain_valid" not in audit:
            errors.append("audit: missing 'chain_valid'")
        if "events" not in audit or not isinstance(audit["events"], list):
            errors.append("audit: missing or invalid 'events' list")

    return errors
