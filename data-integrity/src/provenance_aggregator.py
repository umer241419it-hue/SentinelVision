"""
SentinelVision - Provenance Aggregator and Systematic Mislabelling Detector.

Aggregates sample-level integrity findings across provenance dimensions
(contributor, source, batch, collection) and detects systematic group-level
anomalies (e.g., systematic mislabelling, duplicate flooding by contributor,
trigger insertion clusters).

Provides:
- Contributor, source, batch, and collection level rollups
- Systematic mislabelling pattern detection (dominant class confusion,
  binomial / z-score deviation from global dataset baseline)
- Clear handling of missing or partial provenance metadata with explicit limitations
- Separation of confidence (evidence strength) and severity (risk impact)
- Non-incriminating, evidence-based terminology ("anomalous annotation pattern",
  "elevated integrity risk", "requires review")
"""

from collections import Counter, defaultdict
import math
from typing import Any, Dict, List, Optional, Tuple


class ProvenanceAggregator:
    """
    Aggregates sample-level findings across provenance dimensions and detects
    systematic group-level integrity anomalies.
    """

    SUPPORTED_GROUP_TYPES = ("contributor", "source", "batch", "collection")

    def __init__(
        self,
        anomaly_rate_threshold: float = 0.10,
        min_group_size: int = 5,
        min_anomaly_count: int = 3,
        z_score_threshold: float = 2.5,
    ):
        """
        Args:
            anomaly_rate_threshold: Minimum fraction of anomalous samples in a group
                                    to flag an elevated risk.
            min_group_size: Minimum number of samples in a group to evaluate statistics.
            min_anomaly_count: Minimum absolute count of anomalies to trigger group finding.
            z_score_threshold: Standard deviations above baseline to flag systematic anomaly.
        """
        self.anomaly_rate_threshold = anomaly_rate_threshold
        self.min_group_size = min_group_size
        self.min_anomaly_count = min_anomaly_count
        self.z_score_threshold = z_score_threshold

    def aggregate(
        self,
        sample_findings: List[Dict[str, Any]],
        provenance_records: Dict[str, Dict[str, str]],
        dataset_samples: Optional[List[Dict[str, Any]]] = None,
        total_sample_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate sample findings by contributor, source, batch, and collection.

        Args:
            sample_findings: List of finding records (each having 'assetID' or 'sample_id',
                             'reason', 'confidence', 'severity', 'disposition',
                             and optional 'details' / 'flags').
            provenance_records: Dict mapping sample_id -> provenance dict
                                {"contributor_id": ..., "source_id": ..., "batch_id": ..., "collection_id": ...}
            dataset_samples: Optional list of all dataset samples (to calculate full group sizes).
            total_sample_count: Total samples in dataset (if dataset_samples not provided).

        Returns:
            Dict containing:
                "group_findings": List of findings per group
                "group_summaries": Detailed metrics per group
                "limitations": List of limitations if metadata is missing/incomplete
                "global_baseline": Overall dataset anomaly rates
        """
        limitations: List[str] = []

        if not provenance_records:
            return {
                "group_findings": [],
                "group_summaries": {},
                "limitations": [
                    "Contributor attribution unavailable: contributor metadata not supplied.",
                    "Source attribution unavailable: source metadata not supplied.",
                    "Batch attribution unavailable: batch metadata not supplied.",
                    "Collection attribution unavailable: collection metadata not supplied.",
                ],
                "global_baseline": {},
            }

        # Check which metadata fields are present across provenance_records
        sample_prov = next(iter(provenance_records.values()))
        for group_type in self.SUPPORTED_GROUP_TYPES:
            field_name = f"{group_type}_id"
            if field_name not in sample_prov or not any(p.get(field_name) for p in provenance_records.values()):
                limitations.append(f"{group_type.capitalize()} attribution unavailable: {group_type} metadata not supplied.")

        # Map sample finding by sample_id
        findings_by_sample: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for f in sample_findings:
            sid = f.get("sample_id") or f.get("assetID", "").replace("image-", "")
            # Handle potential run_id prefix in assetID
            if "-" in sid and not sid.startswith("voc2012_"):
                # e.g., image-run123-voc2012_000001
                parts = sid.split("-")
                sid = parts[-1]
            findings_by_sample[sid].append(f)

        # Calculate group population sizes
        group_members: Dict[str, Dict[str, List[str]]] = {
            gt: defaultdict(list) for gt in self.SUPPORTED_GROUP_TYPES
        }

        if dataset_samples:
            for s in dataset_samples:
                sid = s.get("sample_id") or s.get("image_id")
                prov = provenance_records.get(sid, {})
                for gt in self.SUPPORTED_GROUP_TYPES:
                    gid = prov.get(f"{gt}_id")
                    if gid:
                        group_members[gt][gid].append(sid)
        else:
            for sid, prov in provenance_records.items():
                for gt in self.SUPPORTED_GROUP_TYPES:
                    gid = prov.get(f"{gt}_id")
                    if gid:
                        group_members[gt][gid].append(sid)

        total_samples = (
            total_sample_count
            or (len(dataset_samples) if dataset_samples else len(provenance_records))
        )
        total_flagged_samples = len(findings_by_sample)
        global_anomaly_rate = (
            (total_flagged_samples / total_samples) if total_samples > 0 else 0.0
        )

        global_baseline = {
            "total_samples": total_samples,
            "total_flagged_samples": total_flagged_samples,
            "global_anomaly_rate": round(global_anomaly_rate, 4),
        }

        group_findings: List[Dict[str, Any]] = []
        group_summaries: Dict[str, Dict[str, Any]] = {
            gt: {} for gt in self.SUPPORTED_GROUP_TYPES
        }

        # Analyze each group type
        for gt in self.SUPPORTED_GROUP_TYPES:
            for gid, members in group_members[gt].items():
                g_size = len(members)
                if g_size == 0:
                    continue

                # Collect findings for samples in this group
                g_findings: List[Dict[str, Any]] = []
                g_flagged_samples: set = set()
                finding_types: Counter = Counter()
                confusion_counter: Counter = Counter()

                for sid in members:
                    if sid in findings_by_sample:
                        g_flagged_samples.add(sid)
                        for sf in findings_by_sample[sid]:
                            g_findings.append(sf)
                            # Extract finding types
                            ftype = sf.get("anomaly_type") or sf.get("flag") or sf.get("reason", "")
                            if "label" in ftype.lower() or "flip" in ftype.lower():
                                finding_types["label_anomaly"] += 1
                                # Check for class confusion info
                                details = sf.get("details", {})
                                orig = details.get("original_label") or details.get("observed_class")
                                pred = details.get("predicted_label") or details.get("suggested_class")
                                if orig and pred and orig != pred:
                                    confusion_counter[f"{orig} -> {pred}"] += 1
                            elif "duplicate" in ftype.lower():
                                finding_types["duplicate_anomaly"] += 1
                            elif "ood" in ftype.lower() or "distribution" in ftype.lower():
                                finding_types["ood_anomaly"] += 1
                            elif "trigger" in ftype.lower() or "backdoor" in ftype.lower():
                                finding_types["trigger_anomaly"] += 1
                            else:
                                finding_types[ftype] += 1

                affected_count = len(g_flagged_samples)
                affected_fraction = affected_count / g_size if g_size > 0 else 0.0

                # Calculate z-score deviation from global baseline
                z_score = 0.0
                if g_size >= self.min_group_size and global_anomaly_rate > 0:
                    # Normal approximation to binomial: SE = sqrt(p * (1 - p) / n)
                    p = global_anomaly_rate
                    se = math.sqrt(p * (1.0 - p) / g_size) if p < 1.0 else 0.001
                    if se > 0:
                        z_score = (affected_fraction - p) / se

                # Dominant confusion for systematic mislabelling
                dominant_confusion = None
                dominant_confusion_count = 0
                if confusion_counter:
                    dominant_confusion, dominant_confusion_count = confusion_counter.most_common(1)[0]

                # Group metrics summary
                summary = {
                    "group_type": gt,
                    "group_id": gid,
                    "sample_count": g_size,
                    "affected_samples": affected_count,
                    "affected_fraction": round(affected_fraction, 4),
                    "finding_type_counts": dict(finding_types),
                    "dominant_confusion": (
                        f"{dominant_confusion} ({dominant_confusion_count}x)"
                        if dominant_confusion
                        else None
                    ),
                    "z_score": round(z_score, 2),
                }
                group_summaries[gt][gid] = summary

                # Evaluate whether to generate a formal group finding
                is_anomalous = (
                    g_size >= self.min_group_size
                    and affected_count >= self.min_anomaly_count
                    and (affected_fraction >= self.anomaly_rate_threshold or z_score >= self.z_score_threshold)
                )

                if is_anomalous:
                    # Determine severity and confidence
                    # Decoupled confidence: statistical strength based on sample size and z-score
                    conf_raw = 0.65 + min(0.30, 0.05 * max(0.0, z_score))
                    confidence = round(min(0.95, max(0.60, conf_raw)), 2)

                    # Severity: based on fraction affected and presence of specific threat vectors
                    if affected_fraction >= 0.25 or finding_types.get("trigger_anomaly", 0) > 0:
                        severity = "HIGH"
                    elif affected_fraction >= 0.15:
                        severity = "MEDIUM"
                    else:
                        severity = "LOW"

                    # Build finding description
                    reasons: List[str] = []
                    if dominant_confusion and dominant_confusion_count >= 3:
                        reasons.append(
                            f"Systematic mislabelling anomaly: dominant confusion {dominant_confusion} "
                            f"({dominant_confusion_count}/{affected_count} label anomalies)"
                        )
                    elif finding_types.get("label_anomaly", 0) >= 3:
                        reasons.append(
                            f"Elevated label anomaly rate: {finding_types['label_anomaly']} anomalies "
                            f"({affected_fraction*100:.1f}% vs {global_anomaly_rate*100:.1f}% baseline)"
                        )
                    if finding_types.get("duplicate_anomaly", 0) >= 3:
                        reasons.append(
                            f"Near-duplicate concentration: {finding_types['duplicate_anomaly']} duplicate pairs in group"
                        )
                    if finding_types.get("trigger_anomaly", 0) > 0:
                        reasons.append(
                            f"Trigger pattern concentration: {finding_types['trigger_anomaly']} trigger detections in group"
                        )
                    if finding_types.get("ood_anomaly", 0) >= 3:
                        reasons.append(
                            f"OOD concentration: {finding_types['ood_anomaly']} OOD samples in group"
                        )

                    if not reasons:
                        reasons.append(
                            f"Elevated aggregate anomaly rate ({affected_fraction*100:.1f}% vs "
                            f"{global_anomaly_rate*100:.1f}% baseline, z={z_score:.1f})"
                        )

                    finding_record = {
                        "finding_id": f"group_{gt}_{gid}",
                        "group_type": gt,
                        "group_id": gid,
                        "affected_samples": affected_count,
                        "total_samples": g_size,
                        "affected_fraction": round(affected_fraction, 4),
                        "finding_types": sorted(list(finding_types.keys())),
                        "confidence": confidence,
                        "severity": severity,
                        "disposition": "REVIEW",
                        "finding": "Elevated systematic annotation anomaly" if "label_anomaly" in finding_types else "Elevated integrity risk",
                        "reason": "; ".join(reasons),
                        "dominant_confusion": summary["dominant_confusion"],
                        "z_score": round(z_score, 2),
                        "evidence_refs": [
                            f.get("evidenceHash") or f.get("finding_id") or f.get("assetID")
                            for f in g_findings[:10]
                            if (f.get("evidenceHash") or f.get("finding_id") or f.get("assetID"))
                        ],
                    }
                    group_findings.append(finding_record)

        # Sort group findings by severity and affected_fraction descending
        group_findings.sort(
            key=lambda gf: (
                {"HIGH": 2, "MEDIUM": 1, "LOW": 0}.get(gf["severity"], 0),
                gf["affected_fraction"],
            ),
            reverse=True,
        )

        return {
            "group_findings": group_findings,
            "group_summaries": group_summaries,
            "limitations": limitations,
            "global_baseline": global_baseline,
        }
