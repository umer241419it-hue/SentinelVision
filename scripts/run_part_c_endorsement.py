import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import urllib.error

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "crypto-utils"))

from sign import sign_fields

BRIDGE_URL = "http://localhost:3000/findings"


def post_finding(payload: dict) -> tuple:
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(BRIDGE_URL, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        try:
            body_json = json.loads(body)
        except Exception:
            body_json = body
        return e.code, body_json


def get_finding(asset_id: str) -> tuple:
    url = f"{BRIDGE_URL}/{asset_id}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')


def main():
    print("=" * 80)
    print("STAGE 5 PART C: RE-VERIFY MULTI-ORG ENDORSEMENT WRITE-TIME GUARANTEE ON v1.2")
    print("=" * 80)

    asset_id = "finding-stage5-endorse-test"
    payload_8 = {
        "assetID": asset_id,
        "moduleName": "ModelIntegrity-NeuralCleanse-MAD-STRIP",
        "reason": "Stage 5 Part C: Endorsement policy verification under chaincode v1.2 9-field schema",
        "evidenceHash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "confidence": "0.95",
        "severity": "CRITICAL",
        "disposition": "QUARANTINE",
        "timestamp": "2026-09-23T08:35:00Z"
    }

    # Generate valid Ed25519 signature for the 8 fields
    sig_hex = sign_fields("ModelIntegrity", payload_8)
    full_payload = dict(payload_8)
    full_payload["signature"] = sig_hex

    print("\n--- 1. PREPARED 9-FIELD SIGNED FINDING ---")
    print(json.dumps(full_payload, indent=2))

    # Step 1: Stop peer0.org2.example.com
    print("\n--- 2. STOPPING peer0.org2.example.com ---")
    subprocess.run(["docker", "stop", "peer0.org2.example.com"], check=True)
    time.sleep(2)
    print("[*] peer0.org2 is now OFFLINE.")

    # Step 2: Attempt POST with peer0.org2 offline
    print("\n--- 3. ATTEMPTING POST WITH peer0.org2 OFFLINE ---")
    status_offline, resp_offline = post_finding(full_payload)
    print(f"HTTP Status: {status_offline}")
    print("Response Body:")
    print(json.dumps(resp_offline, indent=2) if isinstance(resp_offline, dict) else resp_offline)

    # Step 3: Restore peer0.org2.example.com
    print("\n--- 4. RESTORING peer0.org2.example.com ---")
    subprocess.run(["docker", "start", "peer0.org2.example.com"], check=True)
    time.sleep(5)
    print("[*] peer0.org2 is now ONLINE.")

    # Step 4: Repeat identical POST with peer0.org2 online
    print("\n--- 5. REPEATING POST WITH BOTH PEERS ONLINE ---")
    status_online, resp_online = post_finding(full_payload)
    print(f"HTTP Status: {status_online}")
    print("Response Body:")
    print(json.dumps(resp_online, indent=2) if isinstance(resp_online, dict) else resp_online)

    # Step 5: Query GET to verify round-trip and signatureStatus
    print("\n--- 6. VERIFYING GET ROUND-TRIP ---")
    status_get, resp_get = get_finding(asset_id)
    print(f"HTTP Status: {status_get}")
    print("Response Body:")
    print(json.dumps(resp_get, indent=2) if isinstance(resp_get, dict) else resp_get)

    assert status_offline >= 400, "Expected failure when peer0.org2 was offline!"
    assert status_online == 201, "Expected HTTP 201 when peer0.org2 was restored!"
    assert status_get == 200, "Expected HTTP 200 on GET!"
    assert resp_get['data']['signatureStatus'] == 'VALID', "Expected signatureStatus VALID!"

    print("\n" + "=" * 80)
    print("PART C WRITE-TIME GUARANTEE VERIFICATION PASSED ON v1.2!")
    print("=" * 80)


if __name__ == '__main__':
    main()
