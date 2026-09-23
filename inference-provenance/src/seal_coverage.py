import warnings
warnings.filterwarnings('ignore')

import hashlib
import json
import os
import sys
from pathlib import Path
from PIL import Image
import numpy as np
import torch

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'model-integrity'))
sys.path.insert(0, str(PROJECT_ROOT / 'crypto-utils'))
sys.path.insert(0, str(PROJECT_ROOT / 'inference-provenance' / 'src'))

from wrapper import sealed_predict
from verify_seal import verify_seal
from calibrate_channel_order import patch_model

MANIFEST_PATH = PROJECT_ROOT / 'model-integrity' / 'calibration_manifest.json'
OUTPUT_PATH = PROJECT_ROOT / 'inference-provenance' / 'seal_coverage_results.json'


def compute_file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return h.hexdigest()


def load_input_image(path: Path, channel_order: str = 'BGR') -> torch.Tensor:
    img = Image.open(path).convert('RGB')
    arr = np.array(img).astype(np.float32) / 255.0  # HWC, [0, 1]
    if channel_order == 'BGR':
        arr = arr[:, :, ::-1].copy()
    tensor = torch.from_numpy(arr).permute(2, 0, 1)  # CHW
    return tensor.unsqueeze(0)  # NCHW


def get_architecture(model) -> str:
    name = type(model).__name__
    if name == 'Inception3':
        return 'InceptionV3'
    elif name == 'DenseNet':
        return 'DenseNet121'
    elif name == 'ResNet':
        return 'ResNet50'
    return name


def main():
    with open(MANIFEST_PATH, 'r') as f:
        manifest = json.load(f)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'Starting seal coverage test across {len(manifest)} models on device: {device}')

    results = []

    for entry in manifest:
        model_id = entry['model_id']
        channel_order = entry.get('chosen_channel_order', 'BGR')
        model_dir = PROJECT_ROOT / 'model-integrity' / 'data' / 'trojai_sample' / model_id
        model_path = model_dir / 'model.pt'
        example_dir = model_dir / 'example_data'

        # Pick first available example image
        sample_img_path = example_dir / 'class_0_example_0.png'
        if not sample_img_path.exists():
            candidates = sorted(list(example_dir.glob('*.png')))
            if not candidates:
                raise FileNotFoundError(f'No example images found in {example_dir}')
            sample_img_path = candidates[0]

        # 1. SHA-256 before
        sha_before = compute_file_sha256(model_path)

        # Load and patch model
        model = torch.load(model_path, map_location=device, weights_only=False)
        patch_model(model)
        model = model.to(device)
        model.eval()

        arch = get_architecture(model)

        # Load input
        input_tensor = load_input_image(sample_img_path, channel_order=channel_order).to(device)

        config = {
            'channel_order': channel_order,
            'normalization': 'min-max [0, 1]',
            'input_resolution': [input_tensor.shape[2], input_tensor.shape[3]],
            'device': str(device),
            'source_sample': str(sample_img_path.relative_to(PROJECT_ROOT)),
        }

        # 2. Run sealed_predict()
        with torch.no_grad():
            output, record = sealed_predict(
                model=model,
                input_tensor=input_tensor,
                model_asset_id=f'model-{model_id}',
                model_digest=sha_before,
                config=config,
            )

        # 3. Run verify_seal()
        verify_res = verify_seal(record)
        verdict = verify_res['verdict']

        # 4. SHA-256 after
        sha_after = compute_file_sha256(model_path)

        if sha_before != sha_after:
            raise RuntimeError(f'FATAL: Model hash mismatch for {model_id}! Before: {sha_before}, After: {sha_after}')

        if verdict != 'VALID':
            raise RuntimeError(f'FATAL: Verification failed for {model_id}! Result: {verify_res}')

        record_entry = {
            'model_id': model_id,
            'architecture': arch,
            'sha_before': sha_before,
            'sha_after': sha_after,
            'verdict': verdict,
        }
        results.append(record_entry)
        print(f'[{len(results)}/15] {model_id:<12} | {arch:<12} | Hash Match: {sha_before == sha_after} | Verdict: {verdict}')

    with open(OUTPUT_PATH, 'w') as f:
        json.dump(results, f, indent=2)

    print(f'\nAll {len(results)} models verified successfully. Saved results to {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
