import warnings
warnings.filterwarnings('ignore')

import copy
import hashlib
import json
from pathlib import Path
import secrets
import sys
from PIL import Image
import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'model-integrity'))
sys.path.insert(0, str(PROJECT_ROOT / 'crypto-utils'))
sys.path.insert(0, str(PROJECT_ROOT / 'inference-provenance' / 'src'))

from calibrate_channel_order import patch_model
from verify_seal import verify_seal, SIGNED_FIELD_KEYS
from wrapper import sealed_predict
from canonical import canonical_json


def compute_file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return h.hexdigest()


def load_input_image(path: Path, channel_order: str = 'BGR') -> torch.Tensor:
    img = Image.open(path).convert('RGB')
    arr = np.array(img).astype(np.float32) / 255.0
    if channel_order == 'BGR':
        arr = arr[:, :, ::-1].copy()
    tensor = torch.from_numpy(arr).permute(2, 0, 1)
    return tensor.unsqueeze(0)


def generate_record_for_model(model_id: str):
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model_dir = PROJECT_ROOT / 'model-integrity' / 'data' / 'trojai_sample' / model_id
    model_path = model_dir / 'model.pt'
    img_path = model_dir / 'example_data' / 'class_0_example_0.png'

    model_digest = compute_file_sha256(model_path)
    model = torch.load(model_path, map_location=device, weights_only=False)
    patch_model(model)
    model = model.to(device)
    model.eval()

    input_tensor = load_input_image(img_path, channel_order='BGR').to(device)
    config = {
        'channel_order': 'BGR',
        'normalization': 'min-max [0, 1]',
        'input_resolution': [224, 224],
        'device': str(device),
        'source_sample': str(img_path.relative_to(PROJECT_ROOT)),
    }

    with torch.no_grad():
        _, record = sealed_predict(
            model=model,
            input_tensor=input_tensor,
            model_asset_id=f'model-{model_id}',
            model_digest=model_digest,
            config=config,
        )
    return record


def main():
    print('=' * 80)
    print('STAGE 5 PART B1: FULL PER-FIELD TAMPER MATRIX ON SEAL (LOCAL)')
    print('=' * 80)

    base_record = generate_record_for_model('id-00000028')
    res_base = verify_seal(base_record)
    print(f'Base Record (id-00000028) Self-Check: Verdict={res_base["verdict"]}, HashMatch={res_base["contentHashMatches"]}, SigValid={res_base["signatureValid"]}')
    assert res_base['verdict'] == 'VALID'

    print('\n--- 1. Testing 9 Signed Fields Individually ---')
    field_results = []

    for field in SIGNED_FIELD_KEYS:
        tampered = copy.deepcopy(base_record)
        if field == 'sealID':
            tampered['sealID'] = tampered['sealID'] + '-corrupted'
        elif field == 'modelAssetID':
            tampered['modelAssetID'] = 'model-id-99999999-spoofed'
        elif field == 'inputHash':
            tampered['inputHash'] = 'e' + tampered['inputHash'][1:]
        elif field == 'modelDigest':
            tampered['modelDigest'] = '0' * 64
        elif field == 'config':
            tampered['config']['channel_order'] = 'RGB'
            tampered['config']['normalization'] = 'z-score'
        elif field == 'nonce':
            tampered['nonce'] = 'ffffffffffffffffffffffffffffffff'
        elif field == 'timestamp':
            tampered['timestamp'] = '2030-01-01T00:00:00+00:00'
        elif field == 'outputSummary':
            tampered['outputSummary']['predicted_class'] = 999
            tampered['outputSummary']['confidence'] = 0.0001
        elif field == 'signerModule':
            tampered['signerModule'] = 'MaliciousModuleIdentity'

        res = verify_seal(tampered)
        field_results.append({
            'field': field,
            'contentHashMatches': res['contentHashMatches'],
            'signatureValid': res['signatureValid'],
            'verdict': res['verdict'],
        })
        print(f"Field: {field:<16} | HashMatch: {str(res['contentHashMatches']):<5} | SigValid: {str(res['signatureValid']):<5} | Verdict: {res['verdict']}")

    print('\n--- 2. Attack 1: Signature Substitution ---')
    record_b = generate_record_for_model('id-00000112')
    res_b_clean = verify_seal(record_b)
    assert res_b_clean['verdict'] == 'VALID'

    sub_record = copy.deepcopy(record_b)
    sub_record['signature'] = base_record['signature']
    res_sub = verify_seal(sub_record)

    print(f"Model A (id-00000028) Signature: {base_record['signature'][:24]}...")
    print(f"Model B (id-00000112) Signature: {record_b['signature'][:24]}...")
    print(f"Substituted Record on Model B: HashMatch={res_sub['contentHashMatches']}, SigValid={res_sub['signatureValid']}, Verdict={res_sub['verdict']}")

    print('\n--- 3. Attack 2: Forged-Signature Attempt (Random Hex String) ---')
    forged_record_a = copy.deepcopy(base_record)
    forged_record_a['outputSummary']['predicted_class'] = 3
    forged_record_a['signature'] = secrets.token_hex(64)
    res_forged_a = verify_seal(forged_record_a)
    print(f"Case A (Field tampered + random signature + stale contentHash): HashMatch={res_forged_a['contentHashMatches']}, SigValid={res_forged_a['signatureValid']}, Verdict={res_forged_a['verdict']}")

    forged_record_b = copy.deepcopy(base_record)
    forged_record_b['outputSummary']['predicted_class'] = 3
    signed_fields_b = {k: forged_record_b[k] for k in SIGNED_FIELD_KEYS}
    forged_record_b['contentHash'] = hashlib.sha256(canonical_json(signed_fields_b).encode('utf-8')).hexdigest()
    forged_record_b['signature'] = secrets.token_hex(64)
    res_forged_b = verify_seal(forged_record_b)
    print(f"Case B (Field tampered + recomputed contentHash + random signature): HashMatch={res_forged_b['contentHashMatches']}, SigValid={res_forged_b['signatureValid']}, Verdict={res_forged_b['verdict']}")

    print('\n' + '=' * 80)
    print('PART B1 SUMMARY TABLE')
    print('=' * 80)
    header = f"{'Attack / Test Case':<42} | {'Hash Match':<10} | {'Sig Valid':<10} | {'Verdict':<8}"
    print(header)
    print('-' * len(header))
    print(f"{'Genuine Baseline Record':<42} | {str(res_base['contentHashMatches']):<10} | {str(res_base['signatureValid']):<10} | {res_base['verdict']:<8}")
    for fr in field_results:
        label = f"Tamper field '{fr['field']}'"
        print(f"{label:<42} | {str(fr['contentHashMatches']):<10} | {str(fr['signatureValid']):<10} | {fr['verdict']:<8}")
    print(f"{'Attack 1: Signature Substitution':<42} | {str(res_sub['contentHashMatches']):<10} | {str(res_sub['signatureValid']):<10} | {res_sub['verdict']:<8}")
    print(f"{'Attack 2a: Forged Sig (stale contentHash)':<42} | {str(res_forged_a['contentHashMatches']):<10} | {str(res_forged_a['signatureValid']):<10} | {res_forged_a['verdict']:<8}")
    print(f"{'Attack 2b: Forged Sig (recomputed contentHash)':<42} | {str(res_forged_b['contentHashMatches']):<10} | {str(res_forged_b['signatureValid']):<10} | {res_forged_b['verdict']:<8}")
    print('=' * 80)


if __name__ == '__main__':
    main()
