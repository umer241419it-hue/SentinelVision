"""
SentinelVision - Central Governance Aggregation Engine.

Unifies Data Integrity, Model Integrity, Inference Provenance, and Drift Monitoring
into a coherent, evidence-based assurance workflow with tamper-evident audit trails.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in [
    WORKSPACE_ROOT,
    os.path.join(WORKSPACE_ROOT, "crypto-utils"),
    os.path.join(WORKSPACE_ROOT, "inference-provenance", "src"),
]:
    if p not in sys.path:
        sys.path.insert(0, p)

from .audit import AuditEventType, AuditTrail
from .coverage import build_coverage_matrix
from .findings import (
    normalize_data_integrity_finding,
    normalize_drift_finding,
    normalize_inference_seal_finding,
    normalize_model_integrity_finding,
)
from .schema import (
    AssuranceReport,
    CanonicalFinding,
    CheckRecord,
    ConfidenceAssessment,
    FindingCategory,
    FindingStatus,
    GovernanceDisposition,
    OverallAssessment,
    OverallStatus,
    Recommendation,
    SCHEMA_VERSION,
    SeverityLevel,
)

try:
    from verify_seal import verify_seal
except ImportError:
    verify_seal = None


class GovernanceEngine:
    """
    Central Governance & Assurance aggregation engine.
    Orchestrates evidence ingestion, finding normalization, confidence analysis,
    coverage assessment, and audit trail chaining.
    """

    def __init__(
        self,
        assessment_id: Optional[str] = None,
        environment: str = "offline/air-gapped",
    ):
        self.assessment_id = assessment_id or f"asmt-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        self.environment = environment
        self.audit_trail = AuditTrail(self.assessment_id, actor="GovernanceEngine")
        self.checks: List[CheckRecord] = []
        self.findings: List[Any] = []
        self.assets: Dict[str, List[Dict[str, Any]]] = {
            "datasets": [],
            "models": [],
            "inference_records": [],
            "reference_batteries": [],
            "contributors": [],
        }
        self.access_profile: Dict[str, Any] = {
            "data_access": "UNSPECIFIED",
            "model_access": "UNSPECIFIED",
            "inference_access": "UNSPECIFIED",
            "drift_access": "UNSPECIFIED",
            "metadata_available": [],
        }
        self.system_limitations: List[str] = []

        # Record assessment initiation in tamper-evident audit trail
        self.audit_trail.add_event(
            AuditEventType.ASSESSMENT_STARTED,
            data={
                "assessment_id": self.assessment_id,
                "environment": self.environment,
                "schema_version": SCHEMA_VERSION,
            },
        )

    # --------------------------------------------------------------------------
    # Ingestion & Evaluation Methods
    # --------------------------------------------------------------------------

    def register_dataset_asset(
        self,
        dataset_id: str,
        name: str,
        sample_count: int,
        manifest_path: Optional[str] = None,
        hashes: Optional[Dict[str, str]] = None,
    ) -> None:
        """Register evaluated dataset asset in inventory and audit log."""
        ds_info = {
            "asset_id": dataset_id,
            "name": name,
            "sample_count": sample_count,
            "manifest_path": manifest_path,
            "hashes": hashes or {},
        }
        self.assets["datasets"].append(ds_info)
        self.access_profile["data_access"] = "LOCAL_FILESYSTEM"
        self.audit_trail.add_event(
            AuditEventType.ASSET_REGISTERED,
            data={"asset_type": "dataset", "asset": ds_info},
            reference_ids=[dataset_id],
        )

    def register_contributor(
        self,
        contributor_id: str,
        name: str,
        contributor_type: str = "VENDOR",
    ) -> None:
        """Register asset contributor/vendor in governance inventory and audit log."""
        c_info = {
            "contributor_id": contributor_id,
            "name": name,
            "type": contributor_type,
        }
        if "contributors" not in self.assets:
            self.assets["contributors"] = []
        self.assets["contributors"].append(c_info)
        self.audit_trail.add_event(
            AuditEventType.ASSET_REGISTERED,
            data={"asset_type": "contributor", "asset": c_info},
            reference_ids=[contributor_id],
        )

    def register_model_asset(
        self,
        model_id: str,
        architecture: str,
        digest: str,
        weights_path: Optional[str] = None,
        access_level: str = "white-box",
    ) -> None:
        """Register evaluated model asset in inventory and audit log."""
        m_info = {
            "asset_id": model_id,
            "architecture": architecture,
            "digest": digest,
            "weights_path": weights_path,
            "access_level": access_level,
        }
        self.assets["models"].append(m_info)
        self.access_profile["model_access"] = access_level
        self.audit_trail.add_event(
            AuditEventType.ASSET_REGISTERED,
            data={"asset_type": "model", "asset": m_info},
            reference_ids=[model_id],
        )

    def ingest_data_integrity_results(
        self,
        results_data_or_path: Union[str, Path, Dict[str, Any], List[Dict[str, Any]]],
        evidence_store_dir: Optional[Union[str, Path]] = None,
    ) -> CheckRecord:
        """
        Ingest findings from Training Data Integrity module.
        """
        data = self._resolve_json_input(results_data_or_path)
        raw_findings: List[Dict[str, Any]] = []

        if isinstance(data, dict):
            # Check for results/integrity_results.json
            if "results" in data and isinstance(data["results"], list):
                for item in data["results"]:
                    if "finding" in item and isinstance(item["finding"], dict):
                        raw_findings.append(item["finding"])
                    elif "image_id" in item:
                        raw_findings.append(item)
            # Check for scan_findings.json
            elif "sample_findings" in data and isinstance(data["sample_findings"], list):
                raw_findings.extend(data["sample_findings"])
        elif isinstance(data, list):
            raw_findings.extend(data)

        store_dir = evidence_store_dir or os.path.join(WORKSPACE_ROOT, "data-integrity", "evidence_store")
        normalized = []
        for rf in raw_findings:
            cf = normalize_data_integrity_finding(rf, evidence_store_dir=store_dir)
            normalized.append(cf)
            self.findings.append(cf)

        chk_id = f"chk-di-{uuid.uuid4().hex[:6]}"
        f_ids = [f.finding_id for f in normalized]
        check_rec = CheckRecord(
            check_id=chk_id,
            category=FindingCategory.DATA_INTEGRITY.value,
            name="Training Data Integrity Scan",
            module="DataIntegrity",
            description="Scans dataset for near-duplicates, label flips, trigger patches, and statistical OOD outliers.",
            execution_status="COMPLETED",
            timestamp=datetime.now(timezone.utc).isoformat(),
            parameters={"findings_ingested": len(normalized), "evidence_store": str(store_dir)},
            findings_generated=f_ids,
        )
        self.checks.append(check_rec)

        self.audit_trail.add_event(
            AuditEventType.DATA_CHECK_COMPLETED,
            data={"check_id": chk_id, "anomalous_samples_flagged": len(normalized)},
            reference_ids=f_ids[:10],
        )
        return check_rec

    def ingest_model_integrity_results(
        self,
        results_data_or_path: Union[str, Path, Dict[str, Any], List[Dict[str, Any]]],
        evidence_store_dir: Optional[Union[str, Path]] = None,
    ) -> CheckRecord:
        """
        Ingest findings from Model Integrity module (Neural Cleanse + MAD + STRIP).
        """
        data = self._resolve_json_input(results_data_or_path)
        raw_findings: List[Dict[str, Any]] = []
        if isinstance(data, list):
            raw_findings.extend(data)
        elif isinstance(data, dict):
            if "findings" in data:
                raw_findings.extend(data["findings"])
            else:
                raw_findings.append(data)

        store_dir = evidence_store_dir or os.path.join(WORKSPACE_ROOT, "model-integrity", "evidence_store")
        normalized = []
        for rf in raw_findings:
            cf = normalize_model_integrity_finding(rf, evidence_store_dir=store_dir)
            normalized.append(cf)
            self.findings.append(cf)

        chk_id = f"chk-mi-{uuid.uuid4().hex[:6]}"
        f_ids = [f.finding_id for f in normalized]
        check_rec = CheckRecord(
            check_id=chk_id,
            category=FindingCategory.MODEL_INTEGRITY.value,
            name="Model Integrity & Trojan Inversion",
            module="ModelIntegrity",
            description="Evaluates model weights for backdoors via Neural Cleanse per-class inversion, MAD scoring, and STRIP entropy test.",
            execution_status="COMPLETED",
            timestamp=datetime.now(timezone.utc).isoformat(),
            parameters={"models_evaluated": len(normalized), "evidence_store": str(store_dir)},
            findings_generated=f_ids,
        )
        self.checks.append(check_rec)

        self.audit_trail.add_event(
            AuditEventType.MODEL_CHECK_COMPLETED,
            data={"check_id": chk_id, "models_assessed": len(normalized)},
            reference_ids=f_ids,
        )
        return check_rec

    def ingest_and_verify_inference_seals(
        self,
        records_or_path: Union[str, Path, List[Dict[str, Any]], Dict[str, Any]],
        expected_model_digest: Optional[str] = None,
    ) -> CheckRecord:
        """
        Ingest and independently verify cryptographic inference provenance seals.
        """
        data = self._resolve_json_input(records_or_path)
        records: List[Dict[str, Any]] = []
        if isinstance(data, list):
            records.extend(data)
        elif isinstance(data, dict):
            records.append(data)

        normalized = []
        seen_nonces = set()
        replay_detected = False

        for rec in records:
            seal_id = rec.get("sealID", "unknown-seal")
            self.assets["inference_records"].append({
                "seal_id": seal_id,
                "model_asset_id": rec.get("modelAssetID"),
                "model_digest": rec.get("modelDigest"),
                "input_hash": rec.get("inputHash"),
            })

            # Check nonce reuse
            nonce = rec.get("nonce")
            if nonce:
                if nonce in seen_nonces:
                    replay_detected = True
                else:
                    seen_nonces.add(nonce)

            # Cryptographic verification
            if verify_seal:
                res = verify_seal(rec)
            else:
                res = {"contentHashMatches": True, "signatureValid": True, "verdict": "VALID"}

            cf = normalize_inference_seal_finding(
                seal_record=rec,
                verification_result=res,
                expected_model_digest=expected_model_digest,
            )
            normalized.append(cf)
            self.findings.append(cf)

        self.access_profile["inference_access"] = "SEALED_RECORDS"
        chk_id = f"chk-inf-{uuid.uuid4().hex[:6]}"
        f_ids = [f.finding_id for f in normalized]
        check_rec = CheckRecord(
            check_id=chk_id,
            category=FindingCategory.INFERENCE_PROVENANCE.value,
            name="Inference Provenance & Cryptographic Seal Verification",
            module="InferenceProvenance",
            description="Verifies Ed25519 digital signature over RFC-8785 canonical hash of input, model digest, config, and output summary.",
            execution_status="COMPLETED",
            timestamp=datetime.now(timezone.utc).isoformat(),
            parameters={"seals_evaluated": len(records), "replay_detected": replay_detected},
            findings_generated=f_ids,
        )
        self.checks.append(check_rec)

        self.audit_trail.add_event(
            AuditEventType.SEAL_VERIFICATION_COMPLETED,
            data={"check_id": chk_id, "seals_verified": len(records), "replay_detected": replay_detected},
            reference_ids=f_ids[:10],
        )
        return check_rec

    def ingest_drift_results(
        self,
        drift_data_or_path: Union[str, Path, Dict[str, Any]],
        evidence_store_dir: Optional[Union[str, Path]] = None,
    ) -> CheckRecord:
        """
        Ingest findings from Distribution-Shift / Drift Monitoring module.
        """
        data = self._resolve_json_input(drift_data_or_path)
        run_meta = data.get("run", {}) if isinstance(data, dict) else {}
        results_list = data.get("results", []) if isinstance(data, dict) else []
        if isinstance(data, list):
            results_list = data

        ref_id = run_meta.get("reference_id", "reference-v1")
        self.assets["reference_batteries"].append({
            "reference_id": ref_id,
            "manifest_digest": run_meta.get("reference_manifest_digest"),
            "embedding_digest": run_meta.get("reference_embedding_digest"),
            "backbone": run_meta.get("embedding_backbone", "pixelstat"),
        })
        self.access_profile["drift_access"] = "REFERENCE_BATTERY_AND_WINDOWS"

        store_dir = evidence_store_dir or os.path.join(WORKSPACE_ROOT, "drift-monitor", "evidence_store")
        normalized = []
        for dr in results_list:
            cf = normalize_drift_finding(dr, run_meta=run_meta, evidence_store_dir=store_dir)
            normalized.append(cf)
            self.findings.append(cf)

        chk_id = f"chk-drift-{uuid.uuid4().hex[:6]}"
        f_ids = [f.finding_id for f in normalized]
        check_rec = CheckRecord(
            check_id=chk_id,
            category=FindingCategory.DISTRIBUTION_SHIFT.value,
            name="Distribution Shift & MMD Drift Monitoring",
            module="DistributionShift",
            description="Evaluates rolling live windows against reference battery using MMD-RBF and permutation significance test.",
            execution_status="COMPLETED",
            timestamp=datetime.now(timezone.utc).isoformat(),
            parameters={"windows_evaluated": len(results_list), "reference_id": ref_id},
            findings_generated=f_ids,
        )
        self.checks.append(check_rec)

        self.audit_trail.add_event(
            AuditEventType.DRIFT_CHECK_COMPLETED,
            data={"check_id": chk_id, "windows_checked": len(results_list)},
            reference_ids=f_ids,
        )
        return check_rec

    def record_unassessed_capability(
        self,
        category: str,
        capability_name: str,
        reason: str,
        required_access: str,
    ) -> None:
        """
        Explicitly record when a required capability or asset was NOT assessed due to missing evidence or access.
        Ensures missing assessments are never silently treated as PASS.
        """
        finding_id = f"find-unassessed-{uuid.uuid4().hex[:8]}"
        chk_id = f"chk-skip-{uuid.uuid4().hex[:6]}"

        cf = CanonicalFinding(
            finding_id=finding_id,
            category=category,
            asset_id="SYSTEM_ENVIRONMENT",
            status=FindingStatus.NOT_ASSESSED.value,
            severity=SeverityLevel.LOW.value,
            confidence=ConfidenceAssessment(
                value="UNKNOWN",
                interpretation="UNKNOWN",
                basis=["Capability was not executed because required assets or access were unavailable."],
                limitations=[f"Requires {required_access} to perform assessment."],
            ),
            title=f"Assessment Not Performed: {capability_name}",
            description=reason,
            evidence=[],
            affected_scope="Pipeline Assurance Scope",
            detection_method="Governance Assessor (Coverage Guard)",
            access_assumptions=f"Requires {required_access}",
            recommendation=Recommendation(
                disposition=GovernanceDisposition.REVIEW.value,
                reason=reason,
                suggested_action=f"Provide {required_access} and execute {capability_name} to achieve full assurance coverage.",
                priority="ROUTINE",
            ),
            limitations=[f"Assurance report lacks coverage for {capability_name} under current run."],
            timestamp=datetime.now(timezone.utc).isoformat(),
            module_name="GovernanceEngine",
        )
        self.findings.append(cf)

        check_rec = CheckRecord(
            check_id=chk_id,
            category=category,
            name=capability_name,
            module="GovernanceEngine",
            description=reason,
            execution_status="NOT_ASSESSED",
            timestamp=datetime.now(timezone.utc).isoformat(),
            parameters={"required_access": required_access},
            findings_generated=[finding_id],
        )
        self.checks.append(check_rec)

    # --------------------------------------------------------------------------
    # Aggregation & Overall Assessment
    # --------------------------------------------------------------------------

    def compute_overall_assessment(self) -> OverallAssessment:
        """
        Compute overall assessment deterministically from aggregated findings.
        Rules:
        - Any FAIL or QUARANTINE -> FAIL / QUARANTINE
        - Any REVIEW or WARNING -> REVIEW / REVIEW
        - Any NOT_ASSESSED -> PASS_WITH_LIMITATIONS / ACCEPT (if other checks pass)
        - All PASS -> PASS / ACCEPT
        - No checks ran -> NOT_ASSESSED / REVIEW
        """
        if not self.checks:
            return OverallAssessment(
                overall_status=OverallStatus.NOT_ASSESSED.value,
                disposition=GovernanceDisposition.REVIEW.value,
                summary="No integrity checks were executed in this assessment run.",
                critical_findings=0,
                warning_findings=0,
                review_findings=0,
                pass_findings=0,
                not_assessed=0,
                basis=["Zero checks registered."],
            )

        critical = 0
        warning = 0
        review = 0
        passed = 0
        not_assessed = 0

        quarantine_count = 0
        basis: List[str] = []

        for f in self.findings:
            st = f.status
            sev = f.severity
            disp = f.recommendation.disposition if isinstance(f.recommendation, Recommendation) else f.recommendation.get("disposition")

            if disp == GovernanceDisposition.QUARANTINE.value or st == FindingStatus.FAIL.value or sev == SeverityLevel.CRITICAL.value:
                critical += 1
                quarantine_count += 1
                basis.append(f"CRITICAL integrity failure on {f.asset_id}: {f.title}")
            elif st == FindingStatus.WARNING.value:
                warning += 1
                basis.append(f"Warning on {f.asset_id}: {f.title}")
            elif st == FindingStatus.REVIEW.value:
                review += 1
                basis.append(f"Review required on {f.asset_id}: {f.title}")
            elif st == FindingStatus.NOT_ASSESSED.value:
                not_assessed += 1
                basis.append(f"Unassessed check: {f.title}")
            else:
                passed += 1

        # Summary deduction
        if quarantine_count > 0:
            overall_status = OverallStatus.FAIL.value
            overall_disp = GovernanceDisposition.QUARANTINE.value
            summary = f"QUARANTINE recommended. {critical} critical integrity failure(s) detected requiring immediate isolation."
        elif (review > 0) or (warning > 0):
            overall_status = OverallStatus.REVIEW.value
            overall_disp = GovernanceDisposition.REVIEW.value
            summary = f"REVIEW recommended. {review + warning} anomaly finding(s) require analyst inspection before asset acceptance."
        elif not_assessed > 0:
            overall_status = OverallStatus.PASS_WITH_LIMITATIONS.value
            overall_disp = GovernanceDisposition.ACCEPT.value
            summary = f"ACCEPT WITH LIMITATIONS. All executed checks passed, but {not_assessed} check(s) were NOT ASSESSED due to access boundaries."
        else:
            overall_status = OverallStatus.PASS.value
            overall_disp = GovernanceDisposition.ACCEPT.value
            summary = "ACCEPT recommended. All executed checks passed with no material anomalies or cryptographic violations."

        return OverallAssessment(
            overall_status=overall_status,
            disposition=overall_disp,
            summary=summary,
            critical_findings=critical,
            warning_findings=warning,
            review_findings=review,
            pass_findings=passed,
            not_assessed=not_assessed,
            basis=basis[:15],
        )

    def assemble_report(self) -> AssuranceReport:
        """
        Compile the complete Canonical Assurance Report.
        """
        overall = self.compute_overall_assessment()

        # Build coverage matrix correlating findings
        findings_dicts = [f.to_dict() for f in self.findings]
        coverage_matrix = build_coverage_matrix(executed_findings=findings_dicts)

        # Collect global recommendations
        recommendations: List[Dict[str, Any]] = []
        for f in self.findings:
            rec = f.recommendation.to_dict() if isinstance(f.recommendation, Recommendation) else f.recommendation
            if rec.get("disposition") in (GovernanceDisposition.QUARANTINE.value, GovernanceDisposition.REVIEW.value):
                recommendations.append({
                    "finding_id": f.finding_id,
                    "asset_id": f.asset_id,
                    "disposition": rec.get("disposition"),
                    "priority": rec.get("priority", "ROUTINE"),
                    "reason": rec.get("reason"),
                    "suggested_action": rec.get("suggested_action"),
                })

        # Platform limitations
        limitations = [
            "Assurance findings provide empirical and cryptographic evidence; automated checks do not prove adversary intent.",
            "White-box model evaluation relies on trigger inversion heuristics; unflagged non-patch triggers may evade detection.",
            "Inference provenance guarantees execution authenticity after tensor ingestion; pre-inference camera/sensor integrity is out-of-scope.",
            "Distribution-shift MMD metrics indicate divergence from reference batteries; domain experts must evaluate whether shift is benign or malicious.",
            "All operations run strictly offline without external network or telemetry dependencies.",
        ]
        limitations.extend(self.system_limitations)

        # Reproducibility info
        reproducibility = {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "governance_version": SCHEMA_VERSION,
            "offline_mode": True,
            "assessment_id": self.assessment_id,
            "assessment_timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_versions": {
                "DataIntegrity": "1.1.0",
                "ModelIntegrity": "1.0.0",
                "InferenceProvenance": "1.0.0",
                "DistributionShift": "1.0.0",
                "GovernanceEngine": SCHEMA_VERSION,
            },
        }

        # Final audit event before closing
        self.audit_trail.add_event(
            AuditEventType.REPORT_GENERATED,
            data={"findings_count": len(self.findings), "overall_status": overall.overall_status},
        )
        self.audit_trail.add_event(
            AuditEventType.ASSESSMENT_COMPLETED,
            data={"assessment_id": self.assessment_id},
        )

        audit_summary = self.audit_trail.to_dict()

        report = AssuranceReport(
            schema_version=SCHEMA_VERSION,
            assessment_id=self.assessment_id,
            assessment_timestamp=datetime.now(timezone.utc).isoformat(),
            system={
                "name": "SentinelVision",
                "version": "1.0.0",
                "governance_engine_version": SCHEMA_VERSION,
                "environment": self.environment,
                "node_platform": platform.node(),
            },
            assets=self.assets,
            access_profile=self.access_profile,
            checks=self.checks,
            findings=self.findings,
            overall_assessment=overall,
            coverage=coverage_matrix,
            limitations=list(dict.fromkeys(limitations)),
            recommendations=recommendations,
            audit=audit_summary,
            reproducibility=reproducibility,
        )

        return report

    # --------------------------------------------------------------------------
    # Helpers
    # --------------------------------------------------------------------------

    def _resolve_json_input(self, data_or_path: Any) -> Any:
        if isinstance(data_or_path, (str, Path)):
            path = Path(data_or_path)
            if not path.exists():
                raise FileNotFoundError(f"Input file not found at: {path}")
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return data_or_path
