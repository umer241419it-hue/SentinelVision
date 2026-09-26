"""
Bridge integration tests (task.md 15.8).

Two layers:

1. Offline (always run): the generated finding satisfies every validation rule
   the existing bridge enforces before calling Fabric, and the evidence hash
   binding verifies.

2. Live (opt-in via SENTINELVISION_LIVE_BRIDGE=1): submits a finding through
   the running bridge (POST /findings), expects HTTP 201, then reads it back
   via GET /findings/:id and compares. Requires the Fabric test network +
   bridge up (see ../bridge/README.md).
"""

import json
import os
import urllib.request

import pytest

from conftest import write_image_set

from src.run_drift_monitor import run, submit_finding_to_bridge

BRIDGE_RULES = {
    "required_fields": ["assetID", "moduleName", "reason", "evidenceHash",
                        "confidence", "severity", "disposition", "timestamp", "signature"],
}


def _generate_finding(env, tmp_output_dir):
    live = write_image_set(str(tmp_output_dir / "live-bridge"), 12, "normal", 8000)
    output = run(
        config=env["config"],
        input_dir=live,
        base_dir=env["base_dir"],
        timestamp_fixed="2026-01-01T00:00:00Z",
    )
    assert output["results"], "expected at least one completed window"
    return output["results"][0]["finding"]


def test_finding_satisfies_bridge_validation(env, tmp_path):
    finding = _generate_finding(env, tmp_path)
    for field in BRIDGE_RULES["required_fields"]:
        assert field in finding and finding[field] not in (None, "")
    # confidence numeric in [0,1]
    conf = float(finding["confidence"])
    assert 0.0 <= conf <= 1.0
    # severity/disposition vocabulary matches Model-Integrity-era bridge rules
    assert finding["severity"] in {"LOW", "MEDIUM", "HIGH"}
    assert finding["disposition"] in {"ACCEPT", "REVIEW"}
    assert len(finding["evidenceHash"]) == 64
    assert len(finding["signature"]) == 128
    from verify import verify_fields
    raw_fields = {k: v for k, v in finding.items() if k != "signature"}
    assert verify_fields("DistributionShift", raw_fields, finding["signature"]) is True


def test_submit_finding_to_bridge_offline_failure_shape(env, tmp_path):
    """When no bridge is running the submit helper must return a clean failure
    shape (no exception), so the CLI keeps producing local results."""
    finding = _generate_finding(env, tmp_path)
    result = submit_finding_to_bridge(finding, "http://localhost:9", timeout=2)
    assert result["submitted"] is False
    assert result["http_status"] is None or result["http_status"] >= 400


@pytest.mark.live
def test_live_bridge_roundtrip(env, tmp_path):
    """Opt-in live test: finding -> POST /findings (201) -> GET /findings/:id
    -> returned finding matches submitted finding."""
    if os.environ.get("SENTINELVISION_LIVE_BRIDGE") != "1":
        pytest.skip("set SENTINELVISION_LIVE_BRIDGE=1 with the bridge + Fabric test network running")

    finding = _generate_finding(env, tmp_path)
    bridge_url = os.environ.get("SENTINELVISION_BRIDGE_URL", "http://localhost:3000")

    result = submit_finding_to_bridge(finding, bridge_url)
    assert result["submitted"] is True, result
    assert result["http_status"] == 201

    verification = result.get("ledger_verification", {})
    data = verification.get("data") or verification.get("bridge_response", {}).get("data")
    assert data, f"no ledger payload returned: {verification}"

    # The ledger record must match the submitted finding field-for-field.
    for field in BRIDGE_RULES["required_fields"]:
        assert str(data.get(field)) == str(finding[field]), field

def test_submit_finding_to_bridge_sends_all_nine_fields(monkeypatch, env, tmp_path):
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
        return MockHTTPResponse(json.dumps({"data": {"assetID": "test"}}).encode("utf-8"), status=200)

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    finding = _generate_finding(env, tmp_path)
    result = submit_finding_to_bridge(finding, "http://localhost:3000")

    assert result["submitted"] is True
    assert len(captured_requests) >= 1
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


def test_permanent_crypto_sign_verify_tamper_and_prefix(env, tmp_path):
    from sign import find_private_key_path
    try:
        find_private_key_path("DistributionShift")
    except FileNotFoundError:
        pytest.skip("Private key for DistributionShift not found")

    from verify import verify_fields, REGISTRY_PATH
    from src.finding_builder import build_finding, sanitize_component
    from src.evidence_builder import build_and_store_evidence

    finding = _generate_finding(env, tmp_path)
    raw_fields = {k: v for k, v in finding.items() if k != "signature"}

    # 1. Sign & verify -> valid
    assert verify_fields("DistributionShift", raw_fields, finding["signature"]) is True

    # 2. Mutate one field -> invalid
    tampered_fields = dict(raw_fields, severity="HIGH" if raw_fields["severity"] != "HIGH" else "LOW")
    assert verify_fields("DistributionShift", tampered_fields, finding["signature"]) is False

    tampered_reason = dict(raw_fields, reason=raw_fields["reason"] + " (tampered)")
    assert verify_fields("DistributionShift", tampered_reason, finding["signature"]) is False

    # 3. Module name prefix resolution matching bridge/src/index.js
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry = json.load(f)
    keys = sorted(registry.keys(), key=len, reverse=True)
    resolved_module = next((k for k in keys if finding["moduleName"].startswith(k)), None)
    assert resolved_module == "DistributionShift"

    # 4. Run-scoped uniqueness (different assetID and different evidenceHash)
    run_res = {
        "reference": {"reference_id": "ref1"},
        "live_window": {"window_id": "win1"},
        "policy": {"confidence": 0.85, "severity": "HIGH", "disposition": "REVIEW", "reason": "shift"},
    }
    f_run1 = build_finding(run_res, "a" * 64, "2026-01-01T00:00:00Z", run_id="run01")
    f_run2 = build_finding(run_res, "b" * 64, "2026-01-01T00:00:00Z", run_id="run02")
    assert f_run1["assetID"] != f_run2["assetID"]
    assert "run01" in f_run1["assetID"]
    assert "run02" in f_run2["assetID"]

    ev1 = build_and_store_evidence(
        run_res, str(tmp_path / "store1"), timestamp="2026-01-01T00:00:00Z", run_id="run01"
    )
    ev2 = build_and_store_evidence(
        run_res, str(tmp_path / "store2"), timestamp="2026-01-01T00:00:00Z", run_id="run02"
    )
    assert ev1["evidence_hash"] != ev2["evidence_hash"]

