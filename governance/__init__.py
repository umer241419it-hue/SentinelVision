"""
SentinelVision - Governance & Assurance Reporting Layer.

Trustworthy Computer Vision Integrity Assurance for Data, Models and Inference Outputs
in Multi-Contributor Pipelines (SIH PS 26228).
"""

__version__ = "1.0.0"

from .schema import (
    AssuranceReport,
    CanonicalFinding,
    FindingCategory,
    FindingStatus,
    SeverityLevel,
    GovernanceDisposition,
    OverallStatus,
    SupportStatus,
    AttackClass,
)
from .engine import GovernanceEngine
from .report import AssuranceReportGenerator
from .verifier import AssuranceReportVerifier
from .audit import AuditTrail, AuditEvent

__all__ = [
    "AssuranceReport",
    "CanonicalFinding",
    "FindingCategory",
    "FindingStatus",
    "SeverityLevel",
    "GovernanceDisposition",
    "OverallStatus",
    "SupportStatus",
    "AttackClass",
    "GovernanceEngine",
    "AssuranceReportGenerator",
    "AssuranceReportVerifier",
    "AuditTrail",
    "AuditEvent",
]
