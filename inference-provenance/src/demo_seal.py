"""
SentinelVision - Stage 5 Part A: Demo Sealed Inference
Demonstrates sealed_predict() on a clean model (id-00000028)
validated under Stage 4 Model Integrity (disposition: ACCEPT).
"""
import warnings
warnings.filterwarnings("ignore")

import hashlib
import json
import os
import sys
from pathlib import Path
from PIL import Image
import numpy as np
import torch

# Path setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "model-integrity"))
sys.path.insert(0, str(PROJECT_ROOT / "crypto-utils"))
sys.path.insert(0, str(PROJECT_ROOT / "inference-provenance" / "src"))

from wrapper import sealed_predict
from calibrate_channel_order import patch_model

MODEL_ID = "id-00000028"
MODEL_ASSET_ID = f"model-{MODEL_ID}"
MODEL_DIR = PROJECT_ROOT / "model-integrity" / "data" / "trojai_sample" / MODEL_ID
MODEL_PATH = MODEL_DIR / "model.pt"
EXAMPLE_DATA_DIR = MODEL_DIR / "example_data"
SAMPLE_IMG_PATH = EXAMPLE_DATA_DIR / "class_0_example_0.png"


def compute_file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return h.hexdigest()


def load_input_image(path: Path, channel_order: str = "BGR") -> torch.Tensor:
    img = Image.open(path).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0  # HWC, [0, 1]
    if channel_order == "BGR":
        arr = arr[:, :, ::-1].copy()
    tensor = torch.from_numpy(arr).permute(2, 0, 1)  # CHW
    return tensor.unsqueeze(0)  # NCHW (1, 3, 224, 224)


def main():
    # 1. Device detection at runtime
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 2. Compute model digest
    model_digest = compute_file_sha256(MODEL_PATH)

    # 3. Load clean model
    model = torch.load(MODEL_PATH, map_location=device, weights_only=False)
    patch_model(model)
    model = model.to(device)
    model.eval()

    # 4. Load real sample input
    input_tensor = load_input_image(SAMPLE_IMG_PATH, channel_order="BGR").to(device)

    # 5. Configuration metadata (device will be live-detected by sealed_predict)
    config = {
        "channel_order": "BGR",
        "normalization": "min-max [0, 1]",
        "input_resolution": [224, 224],
        "device": str(next(model.parameters()).device) if hasattr(model, "parameters") else str(device),
        "source_sample": "example_data/class_0_example_0.png",
    }

    # 6. Execute sealed prediction
    with torch.no_grad():
        output, sealed_record = sealed_predict(
            model=model,
            input_tensor=input_tensor,
            model_asset_id=MODEL_ASSET_ID,
            model_digest=model_digest,
            config=config,
        )

    # 7. Pretty-print sealed record
    print(json.dumps(sealed_record, indent=2))


if __name__ == "__main__":
    main()
