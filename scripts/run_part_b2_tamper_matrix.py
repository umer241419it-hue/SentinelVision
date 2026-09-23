import base64
import copy
import json
import secrets
import subprocess
import sys
import time
import urllib.request
import urllib.error

COUCHDB_BASE = "http://localhost:5984/mychannel_basic"
BRIDGE_BASE = "http://localhost:3000/findings"
AUTH_HEADER = "Basic " + base64.b64encode(b"admin:adminpw").decode("ascii")


def couchdb_get(asset_id: str) -> dict:
    url = f"{COUCHDB_BASE}/{asset_id}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", AUTH_HEADER)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))


def couchdb_put(asset_id: str, doc: dict) -> dict:
    url = f"{COUCHDB_BASE}/{asset_id}"
    data = json.dumps(doc).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='PUT')
    req.add_header("Authorization", AUTH_HEADER)
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))


def flush_peer_cache():
    subprocess.run(["docker", "restart", "peer0.org1.example.com"], check=True, stdout=subprocess.DEVNULL)
    time.sleep(3.5)


def bridge_get(asset_id: str, retries: int = 5) -> dict:
    url = f"{BRIDGE_BASE}/{asset_id}"
    req = urllib.request.Request(url)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except (urllib.error.URLError, Exception) as e:
            if attempt < retries - 1:
                time.sleep(1.0)
            else:
                raise e


def run_tamper_case(case_num: int, case_name: str, asset_id: str, mutate_fn, authentic_dict: dict):
    print(f"\n{'=' * 80}")
    print(f"CASE {case_num}: {case_name}")
    print(f"Target Asset ID: {asset_id}")
    print(f"{'=' * 80}")

    # 1. Baseline check
    baseline_bridge = bridge_get(asset_id)
    assert baseline_bridge['data']['signatureStatus'] == 'VALID', f"Baseline for {asset_id} is not VALID! Got {baseline_bridge}"
    print(f"[*] Baseline GET verified: signatureStatus={baseline_bridge['data']['signatureStatus']}")

    # 2. Get active doc from CouchDB
    orig_doc = couchdb_get(asset_id)
    tampered_doc = copy.deepcopy(orig_doc)

    # 3. Apply mutation
    mutate_fn(tampered_doc)

    # 4. PUT tampered doc to CouchDB
    put_res = couchdb_put(asset_id, tampered_doc)
    assert put_res.get('ok') is True, f"CouchDB PUT failed: {put_res}"
    print(f"[*] CouchDB document updated (rev: {put_res['rev']}) with tampered fields.")

    # 5. Flush peer cache and query bridge (Tampered State)
    flush_peer_cache()
    tampered_bridge = bridge_get(asset_id)
    status_tampered = tampered_bridge['data']['signatureStatus']
    print("\n--- RAW GET RESPONSE (TAMPERED STATE) ---")
    print(json.dumps(tampered_bridge, indent=2))
    assert status_tampered == 'TAMPERED', f"Expected TAMPERED, got {status_tampered}!"

    # 6. Restore original document to CouchDB using known authentic fields
    cur_doc = couchdb_get(asset_id)
    restored_doc = copy.deepcopy(cur_doc)
    for k, v in authentic_dict.items():
        restored_doc[k] = v
    restore_res = couchdb_put(asset_id, restored_doc)
    assert restore_res.get('ok') is True, f"CouchDB restore PUT failed: {restore_res}"
    print(f"\n[*] CouchDB document restored (rev: {restore_res['rev']}).")

    # 7. Flush peer cache and query bridge (Restored State)
    flush_peer_cache()
    restored_bridge = bridge_get(asset_id)
    status_restored = restored_bridge['data']['signatureStatus']
    print("\n--- RAW GET RESPONSE (RESTORED STATE) ---")
    print(json.dumps(restored_bridge, indent=2))
    assert status_restored == 'VALID', f"Expected VALID after restore, got {status_restored}!"

    print(f"\n[+] Case {case_num} PASSED: signatureStatus TAMPERED confirmed, successfully restored to VALID.")
    return {
        'case_num': case_num,
        'case_name': case_name,
        'asset_id': asset_id,
        'tampered_response': tampered_bridge,
        'restored_response': restored_bridge,
    }


def main():
    print("=" * 80)
    print("STAGE 5 PART B2: MULTI-FIELD, MULTI-MODULE LIVE LEDGER TAMPER MATRIX")
    print("=" * 80)

    AUTHENTIC_MODEL_INTEGRITY = {
        "evidenceHash": "8940e54c11228b71006be17eeede70a636a0380fe147fd3aee6f2430a9cfdb5b",
        "reason": "No anomalous class detected by Neural Cleanse + MAD (max anomaly index 0.76, below threshold).",
        "disposition": "ACCEPT",
        "severity": "LOW",
        "confidence": "0.38",
        "moduleName": "ModelIntegrity-NeuralCleanse-MAD-STRIP",
        "timestamp": "2026-09-22T11:37:01Z",
        "signature": "26dd7187d230ffc93c215dfd2773240d5d7048e8c6024246b90f34443b38925367d8e228946558559afe5ac5e88ebd2cc39e07d6692dc9c26a9b979f3ceef90d"
    }

    AUTHENTIC_INFERENCE_PROVENANCE = {
        "evidenceHash": "c4c74a5a21d8f864e7d21682ad08f8f82772ad84de80afcb09216fabd6214d58",
        "reason": "Sealed inference record created and self-verified for model model-id-00000028; cryptographically binds input, model digest, config, and output under Ed25519 signature.",
        "disposition": "ACCEPT",
        "severity": "LOW",
        "confidence": "1.0",
        "moduleName": "InferenceProvenance-Ed25519Seal",
        "timestamp": "2026-09-22T11:37:17.404080+00:00",
        "signature": "171948c2ed19995e308eb154d8d15c67b8aad77cb5c075e011f3bb859c5be692780f86fa8b878f1c9cdf081c8effc0856cec29b2db27177e982dbaad7a8d830b"
    }

    # Pre-step: Restore model-id-00000028 from initial failed run if needed
    print("[*] Performing pre-flight check on model-id-00000028...")
    cur_doc = couchdb_get("model-id-00000028")
    if cur_doc.get("evidenceHash") != AUTHENTIC_MODEL_INTEGRITY["evidenceHash"]:
        print("[*] Restoring model-id-00000028 to clean authentic state...")
        for k, v in AUTHENTIC_MODEL_INTEGRITY.items():
            cur_doc[k] = v
        couchdb_put("model-id-00000028", cur_doc)
        flush_peer_cache()
    check = bridge_get("model-id-00000028")
    print(f"[*] Pre-flight model-id-00000028 signatureStatus: {check['data']['signatureStatus']}")
    assert check['data']['signatureStatus'] == 'VALID'

    results = []

    # Case 1: Tamper evidenceHash on Model Integrity finding
    def mutate_case1(doc):
        doc['evidenceHash'] = 'ffff000011228b71006be17eeede70a636a0380fe147fd3aee6f2430a9cfdb5b'

    results.append(run_tamper_case(
        1,
        "Tamper 'evidenceHash' on Model Integrity finding",
        "model-id-00000028",
        mutate_case1,
        AUTHENTIC_MODEL_INTEGRITY,
    ))

    # Case 2: Tamper reason on Model Integrity finding
    def mutate_case2(doc):
        doc['reason'] = "CRITICAL ADVERSARIAL OVERRIDE: Ledger document content modified directly in database."

    results.append(run_tamper_case(
        2,
        "Tamper 'reason' on Model Integrity finding",
        "model-id-00000028",
        mutate_case2,
        AUTHENTIC_MODEL_INTEGRITY,
    ))

    # Case 3: Tamper TWO fields simultaneously (disposition + severity)
    def mutate_case3(doc):
        doc['disposition'] = "QUARANTINE"
        doc['severity'] = "CRITICAL"

    results.append(run_tamper_case(
        3,
        "Tamper TWO fields simultaneously ('disposition' + 'severity') on Model Integrity finding",
        "model-id-00000028",
        mutate_case3,
        AUTHENTIC_MODEL_INTEGRITY,
    ))

    # Case 4: Tamper on an INFERENCE PROVENANCE finding (seal-a91c5355-...)
    def mutate_case4(doc):
        doc['reason'] = "TAMPERED PROVENANCE: Fabricated inference record claiming unverified model execution."

    results.append(run_tamper_case(
        4,
        "Tamper 'reason' on Inference Provenance finding",
        "seal-a91c5355-37e1-4590-a7e2-b53dc595db1a",
        mutate_case4,
        AUTHENTIC_INFERENCE_PROVENANCE,
    ))

    # Case 5: FORGED-SIGNATURE ATTEMPT on live finding
    def mutate_case5(doc):
        doc['disposition'] = "QUARANTINE"
        doc['signature'] = secrets.token_hex(64)  # 128 hex chars random forgery

    results.append(run_tamper_case(
        5,
        "Forged-Signature Attempt on live finding (field altered + random 128-hex signature)",
        "model-id-00000028",
        mutate_case5,
        AUTHENTIC_MODEL_INTEGRITY,
    ))

    print("\n" + "=" * 80)
    print("ALL 5 LIVE LEDGER TAMPER CASES COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == '__main__':
    main()
