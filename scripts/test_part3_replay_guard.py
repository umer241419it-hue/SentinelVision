import copy
import json
from pathlib import Path
import sys
import time
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
    print("STAGE 5 PART 3: PROVING CHAINCODE-LEVEL DUPLICATE-EVIDENCE GUARD")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # STEP 1: BASELINE (Fresh, correctly-signed, genuinely new finding)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("TEST 1: BASELINE SUBMISSION (Genuinely new finding)")
    print("=" * 80)
    baseline_payload_8 = {
        "assetID": "finding-stage5-replay-guard-base",
        "moduleName": "ModelIntegrity-NeuralCleanse-MAD-STRIP",
        "reason": "Stage 5 Part 3 Baseline: Genuinely fresh finding for replay prevention test",
        "evidenceHash": "a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef1",
        "confidence": "0.90",
        "severity": "HIGH",
        "disposition": "QUARANTINE",
        "timestamp": "2026-09-23T09:15:00Z"
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
    # STEP 2: REPLAY ATTEMPT (Same evidenceHash & signature, new assetID)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("TEST 2: REPLAY ATTEMPT (Same evidenceHash resubmitted under new assetID)")
    print("=" * 80)
    replay_payload = copy.deepcopy(baseline_payload)
    replay_payload["assetID"] = "finding-stage5-replay-guard-attack"
    # Keep evidenceHash and signature identical (simulating replaying genuine evidence)

    print("\n--- 2a. POST REPLAYED FINDING ---")
    post_status_2, post_resp_2 = http_post(replay_payload)
    print(f"HTTP Status: {post_status_2}")
    print("Response Body:")
    print(json.dumps(post_resp_2, indent=2) if isinstance(post_resp_2, dict) else post_resp_2)
    assert post_status_2 == 500, f"Expected 500, got {post_status_2}"
    details_str = json.dumps(post_resp_2)
    assert "DUPLICATE_EVIDENCE" in details_str, "DUPLICATE_EVIDENCE error not found in response!"
    assert "finding-stage5-replay-guard-base" in details_str, "Original assetID not cited in DUPLICATE_EVIDENCE error!"
    print("[+] REPLAY REJECTION VERIFIED: Rejected with DUPLICATE_EVIDENCE citing existing assetID.")

    # -------------------------------------------------------------------------
    # STEP 3: FALSE-POSITIVE CHECK (Genuinely different evidenceHash)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("TEST 3: FALSE-POSITIVE CHECK (Different evidenceHash immediately after)")
    print("=" * 80)
    diff_payload_8 = {
        "assetID": "finding-stage5-replay-guard-diff",
        "moduleName": "ModelIntegrity-NeuralCleanse-MAD-STRIP",
        "reason": "Stage 5 Part 3 False-Positive Check: Genuinely distinct evidenceHash",
        "evidenceHash": "b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef2",
        "confidence": "0.85",
        "severity": "CRITICAL",
        "disposition": "QUARANTINE",
        "timestamp": "2026-09-23T09:16:00Z"
    }
    diff_sig = sign_fields("ModelIntegrity", diff_payload_8)
    diff_payload = dict(diff_payload_8)
    diff_payload["signature"] = diff_sig

    print("\n--- 3a. POST DISTINCT FINDING ---")
    post_status_3, post_resp_3 = http_post(diff_payload)
    print(f"HTTP Status: {post_status_3}")
    print("Response Body:")
    print(json.dumps(post_resp_3, indent=2))
    assert post_status_3 == 201, f"Expected 201, got {post_status_3}"

    print("\n--- 3b. GET DISTINCT FINDING ---")
    get_status_3, get_resp_3 = http_get(diff_payload["assetID"])
    print(f"HTTP Status: {get_status_3}")
    print("Response Body:")
    print(json.dumps(get_resp_3, indent=2))
    assert get_status_3 == 200, f"Expected 200, got {get_status_3}"
    assert get_resp_3["data"]["signatureStatus"] == "VALID"
    print("[+] FALSE-POSITIVE CHECK PASSED: Unrelated finding committed and verified normally.")

    # -------------------------------------------------------------------------
    # STEP 4: LEGACY COMPATIBILITY (Read pre-upgrade findings)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("TEST 4: LEGACY COMPATIBILITY (Query pre-existing findings)")
    print("=" * 80)
    print("\n--- 4a. GET PRE-EXISTING 9-FIELD FINDING (model-id-00000028) ---")
    status_4a, resp_4a = http_get("model-id-00000028")
    print(f"HTTP Status: {status_4a}")
    print("Response Body:")
    print(json.dumps(resp_4a, indent=2))
    assert status_4a == 200
    assert resp_4a["data"]["signatureStatus"] == "VALID"

    print("\n--- 4b. GET PRE-EXISTING 8-FIELD FINDING (seal-12998250-3384-4f66-a0db-080eb5dd5f39) ---")
    status_4b, resp_4b = http_get("seal-12998250-3384-4f66-a0db-080eb5dd5f39")
    print(f"HTTP Status: {status_4b}")
    print("Response Body:")
    print(json.dumps(resp_4b, indent=2))
    assert status_4b == 200
    assert resp_4b["data"]["signatureStatus"] == "UNSIGNED_LEGACY"
    print("[+] LEGACY COMPATIBILITY CONFIRMED: Pre-existing findings queryable as before.")

    # -------------------------------------------------------------------------
    # STEP 5: EXACT-KEY RESUBMISSION (Sanity check)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("TEST 5: EXACT-KEY RESUBMISSION (Baseline finding submitted with original assetID)")
    print("=" * 80)
    print("\n--- 5a. POST IDENTICAL BASELINE FINDING AGAIN ---")
    post_status_5, post_resp_5 = http_post(baseline_payload)
    print(f"HTTP Status: {post_status_5}")
    print("Response Body:")
    print(json.dumps(post_resp_5, indent=2) if isinstance(post_resp_5, dict) else post_resp_5)
    details_str_5 = json.dumps(post_resp_5)
    print(f"\nResulting rejection category: {'DUPLICATE_EVIDENCE' if 'DUPLICATE_EVIDENCE' in details_str_5 else 'OTHER'}")

    print("\n" + "=" * 80)
    print("ALL PART 3 VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    main()
