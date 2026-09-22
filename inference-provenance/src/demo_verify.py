"""
SentinelVision - Stage 5 Part A: Demo Sealed Record Verification
Demonstrates verify_seal() against a genuine sealed record and three
tampered variants (tampered outputSummary, modelDigest, timestamp).
"""
import copy
import datetime
import json
import os
from pathlib import Path
import sys
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

from calibrate_channel_order import patch_model
from verify_seal import verify_seal
from wrapper import sealed_predict

MODEL_ID = "id-00000028"
MODEL_ASSET_ID = f"model-{MODEL_ID}"
MODEL_DIR = PROJECT_ROOT / "model-integrity" / "data" / "trojai_sample" / MODEL_ID
MODEL_PATH = MODEL_DIR / "model.pt"
EXAMPLE_DATA_DIR = MODEL_DIR / "example_data"
SAMPLE_IMG_PATH = EXAMPLE_DATA_DIR / "class_0_example_0.png"


def compute_file_sha256(filepath: Path) -> str:
    import hashlib

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


def generate_genuine_record():
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
        "device": str(device),
        "source_sample": "example_data/class_0_example_0.png",
    }

    with torch.no_grad():
        _, record = sealed_predict(
            model=model,
            input_tensor=input_tensor,
            model_asset_id=MODEL_ASSET_ID,
            model_digest=model_digest,
            config=config,
        )
    return record


def main():
    print("================================================================================")
    print("STAGE 5 PART A: INFERENCE PROVENANCE SEAL VERIFICATION DEMO")
    print("================================================================================")

    # 1. Generate / load genuine sealed record
    record = generate_genuine_record()
    print("\n--- 1. GENUINE SEALED RECORD ---")
    print(json.dumps(record, indent=2))

    # 2. Verify genuine record as-is
    print("\n--- 2. VERIFY GENUINE RECORD ---")
    res_genuine = verify_seal(record)
    print(json.dumps(res_genuine, indent=2))
    assert res_genuine["verdict"] == "VALID", "Genuine record failed verification!"
    assert res_genuine["contentHashMatches"] is True
    assert res_genuine["signatureValid"] is True

    # 3. Create 3 tampered copies
    # a) Tamper outputSummary
    record_tamper_output = copy.deepcopy(record)
    orig_class = record_tamper_output["outputSummary"]["predicted_class"]
    tampered_class = 1 if orig_class == 0 else 0
    record_tamper_output["outputSummary"]["predicted_class"] = tampered_class
    record_tamper_output["outputSummary"]["confidence"] = 0.9999

    # b) Tamper modelDigest (swap in different model digest from id-00000112)
    alt_model_path = PROJECT_ROOT / "model-integrity" / "data" / "trojai_sample" / "id-00000112" / "model.pt"
    alt_digest = compute_file_sha256(alt_model_path) if alt_model_path.exists() else "d0d35a0d607ac4c8c3523b9471dd5eca1118ba6ba66a149aa503688fe776cfb5"
    record_tamper_digest = copy.deepcopy(record)
    record_tamper_digest["modelDigest"] = alt_digest

    # c) Tamper timestamp
    record_tamper_time = copy.deepcopy(record)
    try:
        dt = datetime.datetime.fromisoformat(record_tamper_time["timestamp"])
        dt_mutated = dt + datetime.timedelta(seconds=45)
        record_tamper_time["timestamp"] = dt_mutated.isoformat()
    except Exception:
        record_tamper_time["timestamp"] = record_tamper_time["timestamp"].replace(":00", ":45")

    # 4. Verify all 3 tampered copies
    print("\n--- 3. VERIFY TAMPERED COPIES ---")
    print("\n[TAMPER TEST A] Mutated 'outputSummary' (predicted_class changed 0 -> 1):")
    res_a = verify_seal(record_tamper_output)
    print(json.dumps(res_a, indent=2))

    print(f"\n[TAMPER TEST B] Mutated 'modelDigest' (swapped with model id-00000112 digest):")
    res_b = verify_seal(record_tamper_digest)
    print(json.dumps(res_b, indent=2))

    print("\n[TAMPER TEST C] Mutated 'timestamp' (skewed timestamp by +45s):")
    res_c = verify_seal(record_tamper_time)
    print(json.dumps(res_c, indent=2))

    # 5. Clear summary table
    print("\n================================================================================")
    print("VERIFICATION SUMMARY: BEFORE & AFTER TAMPERING")
    print("================================================================================")
    print(f"{'Condition / Test Case':<35} | {'Field Mutated':<18} | {'Hash Match':<10} | {'Sig Valid':<10} | {'Verdict':<8}")
    print("-" * 89)
    print(f"{'Genuine Record (Untampered)':<35} | {'(none)':<18} | {str(res_genuine['contentHashMatches']):<10} | {str(res_genuine['signatureValid']):<10} | {res_genuine['verdict']:<8}")
    print(f"{'Tamper Attack A (Class Spoofing)':<35} | {'outputSummary':<18} | {str(res_a['contentHashMatches']):<10} | {str(res_a['signatureValid']):<10} | {res_a['verdict']:<8}")
    print(f"{'Tamper Attack B (Model Substitution)':<35} | {'modelDigest':<18} | {str(res_b['contentHashMatches']):<10} | {str(res_b['signatureValid']):<10} | {res_b['verdict']:<8}")
    print(f"{'Tamper Attack C (Timestamp Replay/Skew)':<35} | {'timestamp':<18} | {str(res_c['contentHashMatches']):<10} | {str(res_c['signatureValid']):<10} | {res_c['verdict']:<8}")
    print("================================================================================")


if __name__ == "__main__":
    main()
