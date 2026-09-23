import copy
import json
from pathlib import Path
import sys
import urllib.request
import urllib.error

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "crypto-utils"))

from sign import sign_fields

BRIDGE_URL = "http://localhost:3000/findings"


def http_post(payload: dict) -> tuple:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BRIDGE_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            body_json = json.loads(body)
        except Exception:
            body_json = body
        return e.code, body_json


def http_get(asset_id: str) -> tuple:
    url = f"{BRIDGE_URL}/{asset_id}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            body_json = json.loads(body)
        except Exception:
            body_json = body
        return e.code, body_json


def main():
    print("=" * 80)
    print("PART C: DUAL-GUARD VERIFICATION SUITE (chaincode v1.4 sequence 4)")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # 1. BASELINE: Fresh finding with brand-new assetID AND brand-new evidenceHash
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("1. BASELINE: SUBMIT FRESH FINDING (Brand-new assetID and evidenceHash)")
    print("=" * 80)
    baseline_payload_8 = {
        "assetID": "finding-stage5-guard-v14-baseline",
        "moduleName": "ModelIntegrity-NeuralCleanse-MAD-STRIP",
        "reason": "Part C Baseline: fresh finding for dual-guard testing",
        "evidenceHash": "1000000000000000000000000000000000000000000000000000000000000001",
        "confidence": "0.92",
        "severity": "HIGH",
        "disposition": "QUARANTINE",
        "timestamp": "2026-09-23T11:30:00Z"
    }
    baseline_sig = sign_fields("ModelIntegrity", baseline_payload_8)
    baseline_payload = dict(baseline_payload_8)
    baseline_payload["signature"] = baseline_sig

    print("\n--- 1a. POST BASELINE FINDING ---")
    post_status_1, post_resp_1 = http_post(baseline_payload)
    print(f"HTTP Status: {post_status_1}")
    print("Response Body:")
    print(json.dumps(post_resp_1, indent=2))
    assert post_status_1 == 201, f"Expected 201, got {post_status_1}"

    print("\n--- 1b. GET BASELINE FINDING ---")
    get_status_1, get_resp_1 = http_get(baseline_payload["assetID"])
    print(f"HTTP Status: {get_status_1}")
    print("Response Body:")
    print(json.dumps(get_resp_1, indent=2))
    assert get_status_1 == 200, f"Expected 200, got {get_status_1}"
    assert get_resp_1["data"]["signatureStatus"] == "VALID"

    # -------------------------------------------------------------------------
    # 2. EVIDENCE-REPLAY: Different assetID, same evidenceHash -> DUPLICATE_EVIDENCE
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("2. EVIDENCE-REPLAY: REUSE EVIDENCE HASH UNDER NEW ASSETID")
    print("=" * 80)
    replay_payload_8 = {
        "assetID": "finding-stage5-guard-v14-replay",
        "moduleName": "ModelIntegrity-NeuralCleanse-MAD-STRIP",
        "reason": "Part C Replay: attacker re-submitting identical evidence under new assetID",
        "evidenceHash": "1000000000000000000000000000000000000000000000000000000000000001",
        "confidence": "0.92",
        "severity": "HIGH",
        "disposition": "QUARANTINE",
        "timestamp": "2026-09-23T11:31:00Z"
    }
    replay_sig = sign_fields("ModelIntegrity", replay_payload_8)
    replay_payload = dict(replay_payload_8)
    replay_payload["signature"] = replay_sig

    print("\n--- 2a. POST REPLAYED EVIDENCE FINDING ---")
    post_status_2, post_resp_2 = http_post(replay_payload)
    print(f"HTTP Status: {post_status_2}")
    print("Response Body:")
    print(json.dumps(post_resp_2, indent=2) if isinstance(post_resp_2, dict) else post_resp_2)
    assert post_status_2 == 500, f"Expected 500, got {post_status_2}"
    details_str_2 = json.dumps(post_resp_2)
    assert "DUPLICATE_EVIDENCE" in details_str_2, "DUPLICATE_EVIDENCE error not found in response!"
    assert "ASSET_EXISTS" not in details_str_2, "Unexpected ASSET_EXISTS triggered on brand-new assetID!"
    print("[+] VERIFIED: Rejected specifically with DUPLICATE_EVIDENCE (not ASSET_EXISTS).")

    # -------------------------------------------------------------------------
    # 3. ASSETID-OVERWRITE: Reuse baseline assetID with new evidenceHash -> ASSET_EXISTS
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("3. ASSETID-OVERWRITE: REUSE EXISTING ASSETID WITH NEW EVIDENCE HASH")
    print("=" * 80)
    overwrite_payload_8 = {
        "assetID": "finding-stage5-guard-v14-baseline",
        "moduleName": "ModelIntegrity-NeuralCleanse-MAD-STRIP",
        "reason": "Part C Overwrite: attempt to overwrite existing assetID with new evidence",
        "evidenceHash": "2000000000000000000000000000000000000000000000000000000000000002",
        "confidence": "0.75",
        "severity": "MEDIUM",
        "disposition": "ACCEPT",
        "timestamp": "2026-09-23T11:32:00Z"
    }
    overwrite_sig = sign_fields("ModelIntegrity", overwrite_payload_8)
    overwrite_payload = dict(overwrite_payload_8)
    overwrite_payload["signature"] = overwrite_sig

    print("\n--- 3a. POST OVERWRITE ATTEMPT ---")
    post_status_3, post_resp_3 = http_post(overwrite_payload)
    print(f"HTTP Status: {post_status_3}")
    print("Response Body:")
    print(json.dumps(post_resp_3, indent=2) if isinstance(post_resp_3, dict) else post_resp_3)
    assert post_status_3 == 500, f"Expected 500, got {post_status_3}"
    details_str_3 = json.dumps(post_resp_3)
    assert "ASSET_EXISTS" in details_str_3, "ASSET_EXISTS error not found in response!"
    assert "DUPLICATE_EVIDENCE" not in details_str_3, "Unexpected DUPLICATE_EVIDENCE triggered on brand-new evidenceHash!"
    print("[+] VERIFIED: Rejected specifically with ASSET_EXISTS (not DUPLICATE_EVIDENCE).")

    # -------------------------------------------------------------------------
    # 4. FALSE-POSITIVE: Brand-new assetID and brand-new evidenceHash
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("4. FALSE-POSITIVE CHECK: BRAND-NEW ASSETID AND BRAND-NEW EVIDENCE HASH")
    print("=" * 80)
    clean_payload_8 = {
        "assetID": "finding-stage5-guard-v14-clean",
        "moduleName": "ModelIntegrity-NeuralCleanse-MAD-STRIP",
        "reason": "Part C Clean: legitimate finding with brand-new assetID and evidenceHash",
        "evidenceHash": "3000000000000000000000000000000000000000000000000000000000000003",
        "confidence": "0.88",
        "severity": "HIGH",
        "disposition": "QUARANTINE",
        "timestamp": "2026-09-23T11:33:00Z"
    }
    clean_sig = sign_fields("ModelIntegrity", clean_payload_8)
    clean_payload = dict(clean_payload_8)
    clean_payload["signature"] = clean_sig

    print("\n--- 4a. POST LEGITIMATE NEW FINDING ---")
    post_status_4, post_resp_4 = http_post(clean_payload)
    print(f"HTTP Status: {post_status_4}")
    print("Response Body:")
    print(json.dumps(post_resp_4, indent=2))
    assert post_status_4 == 201, f"Expected 201, got {post_status_4}"

    print("\n--- 4b. GET LEGITIMATE NEW FINDING ---")
    get_status_4, get_resp_4 = http_get(clean_payload["assetID"])
    print(f"HTTP Status: {get_status_4}")
    print("Response Body:")
    print(json.dumps(get_resp_4, indent=2))
    assert get_status_4 == 200, f"Expected 200, got {get_status_4}"
    assert get_resp_4["data"]["signatureStatus"] == "VALID"
    print("[+] VERIFIED: Succeeded normally; neither guard over-triggered.")

    # -------------------------------------------------------------------------
    # 5. REGRESSION CHECK: Read pre-existing findings
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("5. REGRESSION CHECK: READ PRE-EXISTING LEDGER FINDINGS")
    print("=" * 80)
    print("\n--- 5a. GET model-id-00000028 (SIGNED PRE-CHANGE FINDING) ---")
    status_5a, resp_5a = http_get("model-id-00000028")
    print(f"HTTP Status: {status_5a}")
    print("Response Body:")
    print(json.dumps(resp_5a, indent=2))
    assert status_5a == 200, f"Expected 200, got {status_5a}"
    assert resp_5a["data"]["signatureStatus"] == "VALID"

    print("\n--- 5b. GET seal-12998250-3384-4f66-a0db-080eb5dd5f39 (UNSIGNED_LEGACY) ---")
    status_5b, resp_5b = http_get("seal-12998250-3384-4f66-a0db-080eb5dd5f39")
    print(f"HTTP Status: {status_5b}")
    print("Response Body:")
    print(json.dumps(resp_5b, indent=2))
    assert status_5b == 200, f"Expected 200, got {status_5b}"
    assert resp_5b["data"]["signatureStatus"] == "UNSIGNED_LEGACY"
    print("[+] VERIFIED: Both pre-existing findings read back identically.")

    print("\n" + "=" * 80)
    print("ALL PART C DUAL-GUARD TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    main()