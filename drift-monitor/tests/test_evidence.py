"""
Unit tests - evidence canonicalization/hashing and 8-field finding schema
(task.md 15.6 + 15.7).
"""

import hashlib
import json
import os

import pytest

from src.drift_detector import map_to_finding_policy
from src.evidence_builder import (
    canonical_json_bytes,
    build_and_store_evidence,
    hash_evidence,
)
from src.finding_builder import (
    build_asset_id,
    build_finding,
    sanitize_component,
    validate_evidence_hash_binding,
    validate_finding,
)


def _canonical(evidence) -> bytes:
    return canonical_json_bytes(evidence)


class TestEvidence:
    def test_canonical_json_deterministic(self):
        evidence = {"b": 1, "a": {"z": [1, 2], "y": None}, "c": "x"}
        b1 = _canonical(evidence)
        b2 = _canonical({"c": "x", "a": {"y": None, "z": [1, 2]}, "b": 1})
        assert b1 == b2
        assert b1 == b'{"a":{"y":null,"z":[1,2]},"b":1,"c":"x"}'

    def test_same_evidence_same_sha256(self):
        evidence = {"module": "DistributionShift", "assessment": "NO_SIGNIFICANT_SHIFT"}
        assert hash_evidence(evidence) == hash_evidence(dict(evidence))
        expected = hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert hash_evidence(evidence) == expected

    def test_changing_one_value_changes_hash(self):
        evidence = {"module": "DistributionShift", "mmd": 0.1}
        h1 = hash_evidence(evidence)
        evidence2 = {"module": "DistributionShift", "mmd": 0.2}
        assert hash_evidence(evidence2) != h1

    def test_evidence_file_name_equals_hash(self, tmp_path):
        run_result = {
            "module": "DistributionShift",
            "module_version": "1.0.0",
            "reference": {"reference_id": "reference-v1", "manifest_digest": "d" * 64,
                          "preprocessing": {}},
            "live_window": {"window_id": "window-000001-abc", "image_count": 10},
            "mmd": {"mmd": 0.05, "kernel": "rbf", "kernel_parameters": {"bandwidth": 1.0},
                    "p_value": None, "permutation_count": 0, "seed": None,
                    "reference_count": 40, "live_count": 10},
            "threshold": {"calibration_id": "threshold-abc123", "value": 0.1, "method": "reference_null"},
            "diagnostics": {"image_diagnostics": {"levels": {}}, "details": {},
                            "assessment_explanation": {}},
            "assessment": "NO_SIGNIFICANT_SHIFT",
            "policy": {"confidence": 0.7, "severity": "LOW", "disposition": "ACCEPT", "reason": "ok"},
        }
        stored = build_and_store_evidence(run_result, str(tmp_path / "store"),
                                          timestamp="2026-01-01T00:00:00Z")
        fname = os.path.basename(stored["evidence_path"])
        assert fname == f"{stored['evidence_hash']}.json"
        with open(stored["evidence_path"], "rb") as f:
            data = f.read()
        assert hashlib.sha256(data).hexdigest() == stored["evidence_hash"]
        # The stored file IS the canonical bytes.
        assert data == canonical_json_bytes(stored["evidence"])

    def test_timestamp_changes_hash(self, tmp_path):
        run_result = {"module": "DistributionShift", "reference": {}, "live_window": {},
                      "mmd": {}, "threshold": {}, "diagnostics": {},
                      "assessment": "NO_SIGNIFICANT_SHIFT", "policy": {}}
        s1 = build_and_store_evidence(run_result, str(tmp_path), timestamp="2026-01-01T00:00:00Z")
        s2 = build_and_store_evidence(run_result, str(tmp_path), timestamp="2026-01-02T00:00:00Z")
        assert s1["evidence_hash"] != s2["evidence_hash"]

    def test_evidence_contains_limitations_and_coverage(self, tmp_path):
        run_result = {"module": "DistributionShift", "reference": {}, "live_window": {},
                      "mmd": {}, "threshold": {}, "diagnostics": {},
                      "assessment": "NO_SIGNIFICANT_SHIFT", "policy": {}}
        stored = build_and_store_evidence(run_result, str(tmp_path), timestamp="t")
        assert stored["evidence"]["limitations"]
        assert "malicious manipulation" in " ".join(stored["evidence"]["limitations"]).lower()
        assert "Coverage:" in stored["evidence"]["coverage_statement"]


class TestFinding:
    def _run_result(self):
        return {
            "reference": {"reference_id": "reference-v1"},
            "live_window": {"window_id": "window-000000-abc123"},
            "policy": {"confidence": 0.85, "severity": "HIGH", "disposition": "REVIEW",
                       "reason": "unexplained shift"},
        }

    def test_all_eight_fields(self):
        finding = build_finding(self._run_result(), "a" * 64, "2026-01-01T00:00:00Z")
        assert set(finding) == {"assetID", "moduleName", "reason", "evidenceHash",
                                "confidence", "severity", "disposition", "timestamp"}

    def test_module_name_is_distribution_shift_mmd(self):
        finding = build_finding(self._run_result(), "a" * 64, "t")
        assert finding["moduleName"] == "DistributionShift-MMD"

    def test_asset_id_unique_and_deterministic(self):
        f1 = build_finding(self._run_result(), "a" * 64, "t")
        f2 = build_finding(self._run_result(), "a" * 64, "t")
        assert f1["assetID"] == f2["assetID"]
        other = self._run_result()
        other["live_window"]["window_id"] = "window-000001-fff456"
        f3 = build_finding(other, "a" * 64, "t")
        assert f1["assetID"] != f3["assetID"]
        assert f1["assetID"].startswith("drift-reference-v1-window-")

    def test_confidence_format_and_bounds(self):
        finding = build_finding(self._run_result(), "a" * 64, "t")
        assert finding["confidence"] == "0.85"
        for conf in (0.0, 0.5, 1.0):
            finding["confidence"] = f"{conf:.2f}"
            validate_finding(finding)

    def test_validate_rejects_bad_severity(self):
        finding = build_finding(self._run_result(), "a" * 64, "t")
        finding["severity"] = "CRITICAL"
        with pytest.raises(ValueError, match="severity"):
            validate_finding(finding)

    def test_validate_rejects_bad_disposition(self):
        finding = build_finding(self._run_result(), "a" * 64, "t")
        finding["disposition"] = "QUARANTINE"
        with pytest.raises(ValueError, match="disposition"):
            validate_finding(finding)

    def test_validate_rejects_bad_hash(self):
        finding = build_finding(self._run_result(), "a" * 64, "t")
        finding["evidenceHash"] = "ZZZ"
        with pytest.raises(ValueError, match="evidenceHash"):
            validate_finding(finding)

    def test_validate_rejects_out_of_range_confidence(self):
        finding = build_finding(self._run_result(), "a" * 64, "t")
        finding["confidence"] = "1.5"
        with pytest.raises(ValueError, match="confidence"):
            validate_finding(finding)

    def test_evidence_hash_binding_tamper_check(self, tmp_path):
        finding = build_finding(self._run_result(), "b" * 64, "t")
        with pytest.raises(FileNotFoundError):
            validate_evidence_hash_binding(finding, str(tmp_path))
        # Write tampered bytes under the expected name -> mismatch error.
        (tmp_path / f"{'b' * 64}.json").write_bytes(b"tampered")
        with pytest.raises(ValueError, match="mismatch"):
            validate_evidence_hash_binding(finding, str(tmp_path))

    def test_sanitize_component(self):
        assert sanitize_component("reference v1/α") == "reference-v1"
        assert sanitize_component("") == "unknown"
        assert len(sanitize_component("x" * 500)) <= 64


class TestPolicyMapping:
    def test_no_shift_accept(self):
        p = map_to_finding_policy("NO_SIGNIFICANT_SHIFT", 0.01, 0.1, 0.5)
        assert p["severity"] == "LOW" and p["disposition"] == "ACCEPT"
        assert 0 <= p["confidence"] <= 0.95

    def test_operational_shift_review_medium(self):
        p = map_to_finding_policy("OPERATIONAL_SHIFT_LIKELY", 0.2, 0.1, 0.01)
        assert p["severity"] == "MEDIUM" and p["disposition"] == "REVIEW"

    def test_unexplained_shift_review_high(self):
        p = map_to_finding_policy("UNEXPLAINED_SHIFT", 0.2, 0.1, 0.01)
        assert p["severity"] == "HIGH" and p["disposition"] == "REVIEW"

    def test_insufficient_evidence_limited_confidence(self):
        p = map_to_finding_policy("INSUFFICIENT_EVIDENCE", 0.0, 0.0, None)
        assert p["confidence"] <= 0.20
        assert p["disposition"] == "REVIEW"
        assert p["severity"] == "LOW"

    def test_confidence_never_attributions_attack(self):
        for assessment in ("OPERATIONAL_SHIFT_LIKELY", "UNEXPLAINED_SHIFT",
                           "NO_SIGNIFICANT_SHIFT", "INSUFFICIENT_EVIDENCE"):
            p = map_to_finding_policy(assessment, 0.5, 0.1, 0.001)
            assert "attack" not in p["reason"].lower()
            assert "attacker" not in p["reason"].lower()
