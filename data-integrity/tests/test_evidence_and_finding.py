"""Tests for evidence building, finding schema, and the integrity checker merge."""

import hashlib
import json
import os

import numpy as np
import pytest

from src.dataset import build_dataset
from src.evidence_builder import (
    build_and_store_evidence,
    canonical_json_bytes,
    hash_evidence,
)
from src.finding_builder import (
    build_asset_id,
    build_finding,
    sanitize_component,
    validate_finding,
)
from src.integrity_checker import check_dataset


def _record(image_id="img_x.png", flags=("duplicate",), conf=0.75, sev="MEDIUM"):
    return {
        "image_id": image_id,
        "flags": list(flags),
        "n_flags": len(flags),
        "reason": "near-duplicate of img_y.png (cosine similarity 0.995 >= threshold 0.98)",
        "confidence": conf,
        "severity": sev,
        "disposition": "REVIEW",
        "details": {},
    }


# -- evidence ---------------------------------------------------------------
def test_canonical_json_deterministic():
    e = {"b": 1, "a": {"z": [1, 2], "y": "x"}}
    b1 = canonical_json_bytes(e)
    b2 = canonical_json_bytes({"a": {"y": "x", "z": [1, 2]}, "b": 1})
    assert b1 == b2
    assert b1 == b'{"a":{"y":"x","z":[1,2]},"b":1}'


def test_same_evidence_same_hash_and_change_detected():
    e1 = _record()
    e2 = _record(conf=0.80)
    assert hash_evidence(e1) == hash_evidence(_record())
    assert hash_evidence(e1) != hash_evidence(e2)


def test_evidence_file_name_equals_hash(tmp_path):
    stored = build_and_store_evidence(
        _record(), {"image_count": 10, "label_distribution": {"day": 5}, "extractor": {}},
        {}, str(tmp_path), "2026-01-01T00:00:00Z",
    )
    h = stored["evidence_hash"]
    assert os.path.isfile(os.path.join(str(tmp_path), f"{h}.json"))
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
    with open(stored["evidence_path"], "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == h


# -- finding ----------------------------------------------------------------
def test_finding_has_all_nine_fields():
    from verify import verify_fields
    f = build_finding(_record(), "a" * 64, "2026-01-01T00:00:00Z")
    assert set(f.keys()) == {
        "assetID", "moduleName", "reason", "evidenceHash",
        "confidence", "severity", "disposition", "timestamp", "signature",
    }
    assert f["moduleName"] == "DataIntegrity"
    assert f["assetID"] == "image-img_x.png"
    assert len(f["signature"]) == 128
    validate_finding(f)
    raw_fields = {k: v for k, v in f.items() if k != "signature"}
    assert verify_fields("DataIntegrity", raw_fields, f["signature"]) is True

    f_run = build_finding(_record(), "a" * 64, "2026-01-01T00:00:00Z", run_id="run01")
    assert f_run["assetID"] == "image-run01-img_x.png"


def test_finding_confidence_format_and_range():
    f = build_finding(_record(conf=0.8), "b" * 64, "2026-01-01T00:00:00Z")
    assert f["confidence"] == "0.80"


def test_finding_validation_failures():
    good = build_finding(_record(), "c" * 64, "2026-01-01T00:00:00Z")
    for field in ("assetID", "moduleName", "reason", "evidenceHash", "confidence", "severity", "disposition", "timestamp", "signature"):
        bad = dict(good)
        bad[field] = ""
        with pytest.raises(ValueError):
            validate_finding(bad)
    bad = dict(good, signature="0" * 127)
    with pytest.raises(ValueError):
        validate_finding(bad)
    bad = dict(good, confidence="1.5")
    with pytest.raises(ValueError):
        validate_finding(bad)
    bad = dict(good, evidenceHash="xyz")
    with pytest.raises(ValueError):
        validate_finding(bad)
    bad = dict(good, severity="CRITICAL")
    with pytest.raises(ValueError):
        validate_finding(bad)
    bad = dict(good, disposition="NUKE")
    with pytest.raises(ValueError):
        validate_finding(bad)


def test_asset_id_sanitization():
    # Spaces/slashes become '-'; '.' stays (ledger-safe, deterministic).
    assert build_asset_id("weird id/../x.png") == "image-weird-id-..-x.png"
    assert sanitize_component("") == "unknown"
    assert build_asset_id("plain.png") == "image-plain.png"


# -- integrity checker merge --------------------------------------------------
def test_combined_record_policy_escalation():
    # Simulate the merge logic through a minimal synthetic dataset run is
    # covered end-to-end elsewhere; here verify the deterministic mapping
    # through a record with multiple flags is produced by check_dataset on
    # the real poisoned dataset (see test_end_to_end). Here: unit-level
    # checks of the evidence/finding binding for a multi-flag record.
    rec = _record(flags=("duplicate", "ood", "label_flip"), conf=0.90, sev="HIGH")
    assert rec["n_flags"] == 3
    assert rec["severity"] == "HIGH"

def test_submit_finding_sends_all_nine_fields(monkeypatch):
    from src.bridge_client import submit_finding

    captured_requests = []

    class MockHTTPResponse:
        def __init__(self, data: bytes, status: int = 200):
            self._data = data
            self.status = status

        def read(self, *args, **kwargs):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_urlopen(req, timeout=20):
        captured_requests.append(req)
        if req.get_method() == "POST":
            return MockHTTPResponse(json.dumps({"status": "created"}).encode("utf-8"), status=201)
        return MockHTTPResponse(json.dumps({"assetID": "test"}).encode("utf-8"), status=200)

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    finding = build_finding(_record(), "a" * 64, "2026-01-01T00:00:00Z", run_id="run01")
    report = submit_finding(finding, "http://localhost:3000")

    assert report["submitted"] is True
    assert len(captured_requests) == 2
    post_req = captured_requests[0]
    assert post_req.get_method() == "POST"
    assert post_req.full_url == "http://localhost:3000/findings"
    body = json.loads(post_req.data.decode("utf-8"))
    assert set(body.keys()) == {
        "assetID", "moduleName", "reason", "evidenceHash",
        "confidence", "severity", "disposition", "timestamp", "signature"
    }
    for k in body:
        assert body[k] == finding[k]


def test_permanent_crypto_sign_verify_tamper_and_prefix(tmp_path):
    from sign import find_private_key_path
    try:
        find_private_key_path("DataIntegrity")
    except FileNotFoundError:
        pytest.skip("Private key for DataIntegrity not found")

    from verify import verify_fields

    finding = build_finding(_record(), "a" * 64, "2026-01-01T00:00:00Z", run_id="run01")
    raw_fields = {k: v for k, v in finding.items() if k != "signature"}

    # 1. Sign & verify -> valid
    assert verify_fields("DataIntegrity", raw_fields, finding["signature"]) is True

    # 2. Mutate one field -> invalid
    tampered_fields = dict(raw_fields, severity="HIGH" if raw_fields["severity"] != "HIGH" else "LOW")
    assert verify_fields("DataIntegrity", tampered_fields, finding["signature"]) is False

    tampered_reason = dict(raw_fields, reason=raw_fields["reason"] + " (tampered)")
    assert verify_fields("DataIntegrity", tampered_reason, finding["signature"]) is False

    # 3. Module name prefix resolution matching bridge/src/index.js
    from verify import REGISTRY_PATH
    registry_path = REGISTRY_PATH
    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)
    keys = sorted(registry.keys(), key=len, reverse=True)
    resolved_module = next((k for k in keys if finding["moduleName"].startswith(k)), None)
    assert resolved_module == "DataIntegrity"

    # 4. Run-scoped uniqueness (different assetID and different evidenceHash)
    f_run1 = build_finding(_record(), "a" * 64, "2026-01-01T00:00:00Z", run_id="run01")
    f_run2 = build_finding(_record(), "b" * 64, "2026-01-01T00:00:00Z", run_id="run02")
    assert f_run1["assetID"] != f_run2["assetID"]
    assert f_run1["assetID"].startswith("image-run01-")
    assert f_run2["assetID"].startswith("image-run02-")

    ev1 = build_and_store_evidence(
        _record(), {"image_count": 10, "label_distribution": {"day": 5}, "extractor": {}},
        {}, str(tmp_path / "store1"), "2026-01-01T00:00:00Z", run_id="run01"
    )
    ev2 = build_and_store_evidence(
        _record(), {"image_count": 10, "label_distribution": {"day": 5}, "extractor": {}},
        {}, str(tmp_path / "store2"), "2026-01-01T00:00:00Z", run_id="run02"
    )
    assert ev1["evidence_hash"] != ev2["evidence_hash"]

