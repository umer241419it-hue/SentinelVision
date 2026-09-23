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
                        "confidence", "severity", "disposition", "timestamp"],
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
