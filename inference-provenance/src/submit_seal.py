"""
SentinelVision - Stage 5 Part A: Submit Sealed Inference Finding to Fabric Ledger
Generates sealed inference record, self-verifies via verify_seal(), persists
evidence to evidence_store/<evidenceHash>.json, and submits 8-field finding
to the Fabric Gateway bridge (POST /findings, GET /findings/:id).
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request
import urllib.error
import warnings

warnings.filterwarnings("ignore")

import numpy as np
from PIL import Image
import torch

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "model-integrity"))
sys.path.insert(0, str(PROJECT_ROOT / "crypto-utils"))
sys.path.insert(0, str(PROJECT_ROOT / "inference-provenance" / "src"))

from canonical import canonical_json
from calibrate_channel_order import patch_model
from verify_seal import verify_seal
from wrapper import sealed_predict
from sign import sign_fields

MODEL_ID = "id-00000028"
MODEL_ASSET_ID = f"model-{MODEL_ID}"
MODEL_DIR = PROJECT_ROOT / "model-integrity" / "data" / "trojai_sample" / MODEL_ID
MODEL_PATH = MODEL_DIR / "model.pt"
EXAMPLE_DATA_DIR = MODEL_DIR / "example_data"
SAMPLE_IMG_PATH = EXAMPLE_DATA_DIR / "class_0_example_0.png"
EVIDENCE_STORE_DIR = PROJECT_ROOT / "inference-provenance" / "evidence_store"

BRIDGE_URL = "http://localhost:3000"


def compute_file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return h.hexdigest()


def load_input_image(path: Path, channel_order: str = "BGR") -> torch.Tensor:
    img = Image.open(path).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    if channel_order == "BGR":
        arr = arr[:, :, ::-1].copy()
    tensor = torch.from_numpy(arr).permute(2, 0, 1)
    return tensor.unsqueeze(0)


def http_post(url: str, payload: dict) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def http_get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def main():
    print("================================================================================")
    print("STAGE 5 PART A: SUBMIT INFERENCE PROVENANCE SEAL TO FABRIC LEDGER")
    print("================================================================================")

    # 1. Device and model setup
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_digest = compute_file_sha256(MODEL_PATH)

    model = torch.load(MODEL_PATH, map_location=device, weights_only=False)
    patch_model(model)
    model = model.to(device)
    model.eval()

    input_tensor = load_input_image(SAMPLE_IMG_PATH, channel_order="BGR").to(device)

    config = {
        "channel_order": "BGR",
        "normalization": "min-max [0, 1]",
        "input_resolution": [224, 224],
        "device": str(next(model.parameters()).device) if hasattr(model, "parameters") else str(device),
        "source_sample": "example_data/class_0_example_0.png",
    }

    # Step 2a: Run sealed_predict()
    print("\n[Step 2a] Executing sealed_predict() on clean model id-00000028...")
    with torch.no_grad():
        output, sealed_record = sealed_predict(
            model=model,
            input_tensor=input_tensor,
            model_asset_id=MODEL_ASSET_ID,
            model_digest=model_digest,
            config=config,
        )

    # Step 2b: Run verify_seal() self-check
    print("\n[Step 2b] Executing verify_seal() self-check on generated record...")
    self_check = verify_seal(sealed_record)
    print(f"Self-Check Result: {json.dumps(self_check, indent=2)}")

    if self_check.get("verdict") != "VALID" or not self_check.get("contentHashMatches") or not self_check.get("signatureValid"):
        raise RuntimeError(f"ABORT: Sealed record self-check failed! Verdict: {self_check.get('verdict')}")
    print("Self-check PASSED: Record is cryptographically VALID under Ed25519 signature.")

    # Step 2c: Serialize FULL record to canonical JSON and store in evidence_store/
    print("\n[Step 2c] Persisting canonical sealed evidence to evidence_store/...")
    EVIDENCE_STORE_DIR.mkdir(parents=True, exist_ok=True)
    canonical_evidence_str = canonical_json(sealed_record)
    evidence_hash = hashlib.sha256(canonical_evidence_str.encode("utf-8")).hexdigest()

    evidence_file_path = EVIDENCE_STORE_DIR / f"{evidence_hash}.json"
    with open(evidence_file_path, "w", encoding="utf-8") as f:
        f.write(canonical_evidence_str)

    print(f"evidenceHash: {evidence_hash}")
    print(f"Evidence file written: {evidence_file_path}")
    assert evidence_file_path.exists(), "Evidence file was not created!"

    # Step 2d: Build 8-field finding matching EXACT chaincode schema
    print("\n[Step 2d] Building 8-field finding matching chaincode schema...")
    seal_id = sealed_record["sealID"]
    asset_id = seal_id if seal_id.startswith("seal-") else f"seal-{seal_id}"

    finding = {
        "assetID": asset_id,
        "moduleName": "InferenceProvenance-Ed25519Seal",
        "reason": f"Sealed inference record created and self-verified for model {MODEL_ASSET_ID}; cryptographically binds input, model digest, config, and output under Ed25519 signature.",
        "evidenceHash": evidence_hash,
        "confidence": "1.0",
        "severity": "LOW",
        "disposition": "ACCEPT",
        "timestamp": sealed_record["timestamp"],
    }
    # Sign the 8 finding fields using module identity 'InferenceProvenance'
    print("\n[Step 2d.1] Signing 8 finding fields with module identity 'InferenceProvenance'...")
    signature = sign_fields("InferenceProvenance", finding)
    finding["signature"] = signature
    print(f"Finding signature: {signature}")
    print("Finding Payload (9 fields):")
    print(json.dumps(finding, indent=2))

    # Step 2e: POST finding to bridge
    print(f"\n[Step 2e] POSTing finding to {BRIDGE_URL}/findings...")
    post_status, post_resp_str = http_post(f"{BRIDGE_URL}/findings", finding)
    print(f"HTTP Status: {post_status}")
    print(f"Raw Response Body:\n{post_resp_str}")

    if post_status not in (200, 201):
        raise RuntimeError(f"Failed to commit finding to Fabric ledger! HTTP {post_status}: {post_resp_str}")

    # Step 2f: GET finding back from bridge
    get_url = f"{BRIDGE_URL}/findings/{asset_id}"
    print(f"\n[Step 2f] GETting finding from {get_url}...")
    get_status, get_resp_str = http_get(get_url)
    print(f"HTTP Status: {get_status}")
    print(f"Raw Response Body:\n{get_resp_str}")

    if get_status != 200:
        raise RuntimeError(f"Failed to query finding from Fabric ledger! HTTP {get_status}: {get_resp_str}")

    # Field-for-field confirmation
    get_json = json.loads(get_resp_str)
    queried_data = get_json.get("data", {})

    print("\n================================================================================")
    print("FIELD-FOR-FIELD VERIFICATION (POST vs GET)")
    print("================================================================================")
    all_matched = True
    for field, expected_val in finding.items():
        queried_val = queried_data.get(field)
        match = (str(expected_val) == str(queried_val))
        if not match:
            all_matched = False
        print(f"Field '{field:<14}': {'MATCH' if match else 'MISMATCH'} (POST: '{expected_val}' | GET: '{queried_val}')")

    print("-" * 80)
    if all_matched:
        print("CONFIRMATION: 9/9 fields match EXACTLY between POSTed finding and queried ledger state!")
    else:
        raise AssertionError("Ledger state mismatch detected!")
    print("================================================================================")


if __name__ == "__main__":
    main()
