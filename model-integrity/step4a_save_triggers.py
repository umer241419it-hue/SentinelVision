#!/usr/bin/env python3
"""
SentinelVision - Stage 4 Step 4a: Save Optimized Trigger Tensors
Runs Neural Cleanse (300 steps, lambda=0.01) across all 75 (model, class) pairs,
saves mask and pattern tensors to model-integrity/triggers/, compares L1 norms
against Step 2b baseline, and enforces SHA-256 model weight immutability.
"""

import os
import sys
import time
import json
import hashlib
import warnings
import numpy as np
import pandas as pd
from PIL import Image
import torch
import torch.nn as nn
import torch.nn.functional as F

warnings.filterwarnings("ignore")

BASE_DIR = "/home/anyone/projects/SentinelVision/model-integrity"
DATA_DIR = os.path.join(BASE_DIR, "data", "trojai_sample")
MANIFEST_PATH = os.path.join(BASE_DIR, "calibration_manifest.json")
BASELINE_RESULTS_PATH = os.path.join(BASE_DIR, "neural_cleanse_results.json")
TRIGGERS_DIR = os.path.join(BASE_DIR, "triggers")
LOG_JSON_PATH = os.path.join(TRIGGERS_DIR, "trigger_reproduction_results.json")

sys.path.insert(0, BASE_DIR)
from calibrate_channel_order import patch_model


def compute_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return h.hexdigest()


def get_num_classes(model):
    if hasattr(model, 'fc') and isinstance(model.fc, nn.Linear):
        return model.fc.out_features, f"model.fc ({model.fc})"
    if hasattr(model, 'classifier'):
        if isinstance(model.classifier, nn.Linear):
            return model.classifier.out_features, f"model.classifier ({model.classifier})"
        elif isinstance(model.classifier, nn.Sequential) and isinstance(model.classifier[-1], nn.Linear):
            return model.classifier[-1].out_features, f"model.classifier[-1] ({model.classifier[-1]})"
    for name, module in reversed(list(model.named_modules())):
        if isinstance(module, nn.Linear):
            return module.out_features, f"last Linear layer '{name}' ({module})"
    raise ValueError("Could not determine output dimension of final classification layer")


def load_image(path, channel_order="BGR"):
    img = Image.open(path).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    if channel_order == "BGR":
        arr = arr[:, :, ::-1].copy()
    return torch.from_numpy(arr).permute(2, 0, 1)


def main():
    print("==============================================================", flush=True)
    print("Starting Step 4a: Saving Trigger Tensors across ALL 75 Classes on GPU", flush=True)
    print("==============================================================", flush=True)

    total_start_time = time.time()
    os.makedirs(TRIGGERS_DIR, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using execution device: {device} ({torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'})", flush=True)

    if not os.path.exists(MANIFEST_PATH):
        raise FileNotFoundError(f"Calibration manifest not found: {MANIFEST_PATH}")
    if not os.path.exists(BASELINE_RESULTS_PATH):
        raise FileNotFoundError(f"Baseline results not found: {BASELINE_RESULTS_PATH}")

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    with open(BASELINE_RESULTS_PATH, "r") as f:
        baseline_records = json.load(f)

    # Map (model_id, class) -> baseline mask_l1_norm
    baseline_map = {
        (rec["model_id"], rec["class"]): rec["mask_l1_norm"]
        for rec in baseline_records
    }

    print(f"Loaded manifest ({len(manifest)} models) and baseline results ({len(baseline_records)} records).\n", flush=True)

    reg_lambda = 0.01
    lr = 0.1
    steps = 300

    all_comparison_results = []
    hash_verification_records = []
    saved_tensor_pairs = []

    for idx, entry in enumerate(manifest, 1):
        model_id = entry["model_id"]
        channel_order = entry.get("chosen_channel_order", "BGR")
        model_dir = os.path.join(DATA_DIR, model_id)
        model_path = os.path.join(model_dir, "model.pt")
        example_data_dir = os.path.join(model_dir, "example_data")
        csv_path = os.path.join(example_data_dir, "data.csv")

        print(f"[{idx}/{len(manifest)}] Processing {model_id}...", flush=True)

        # 1. SHA-256 before
        sha_before = compute_sha256(model_path)
        print(f"    SHA-256 before: {sha_before}", flush=True)

        model_start_time = time.time()

        try:
            model = torch.load(model_path, map_location=device, weights_only=False)
            patch_model(model)
            model = model.to(device)
            model.eval()

            for param in model.parameters():
                param.requires_grad = False

            num_classes, det_desc = get_num_classes(model)

            df = pd.read_csv(csv_path)
            images_by_class = {}
            for c in range(num_classes):
                class_df = df[df["true_label"] == c]
                images_by_class[c] = []
                for _, row in class_df.iterrows():
                    img_p = os.path.join(example_data_dir, row["file"])
                    images_by_class[c].append(load_image(img_p, channel_order=channel_order))

            for c in range(num_classes):
                other_classes = [oc for oc in range(num_classes) if oc != c]
                batch_tensors = []
                images_per_other = 2
                for oc in other_classes:
                    for i in range(min(images_per_other, len(images_by_class[oc]))):
                        batch_tensors.append(images_by_class[oc][i])

                x = torch.stack(batch_tensors).to(device)
                batch_size = x.shape[0]
                H, W = x.shape[2], x.shape[3]
                target_tensor = torch.full((batch_size,), c, dtype=torch.long, device=device)

                mask_param = torch.zeros(1, 1, H, W, device=device, requires_grad=True)
                pattern_param = torch.zeros(1, 3, H, W, device=device, requires_grad=True)
                optimizer = torch.optim.Adam([mask_param, pattern_param], lr=lr)

                for step in range(steps + 1):
                    optimizer.zero_grad()
                    mask = torch.sigmoid(mask_param)
                    pattern = torch.sigmoid(pattern_param)
                    x_masked = (1.0 - mask) * x + mask * pattern

                    out = model(x_masked)
                    if hasattr(out, "logits"):
                        out = out.logits

                    ce_loss = F.cross_entropy(out, target_tensor)
                    reg_loss = reg_lambda * mask.sum()
                    loss = ce_loss + reg_loss

                    if step == steps:
                        break

                    loss.backward()
                    optimizer.step()

                reproduced_norm = float(mask.sum().item())

                # Save actual optimized mask and pattern tensors (CPU detached)
                mask_save_file = f"{model_id}_class{c}_mask.pt"
                pattern_save_file = f"{model_id}_class{c}_pattern.pt"
                mask_save_path = os.path.join(TRIGGERS_DIR, mask_save_file)
                pattern_save_path = os.path.join(TRIGGERS_DIR, pattern_save_file)

                torch.save(mask.detach().cpu(), mask_save_path)
                torch.save(pattern.detach().cpu(), pattern_save_path)
                saved_tensor_pairs.append((mask_save_file, pattern_save_file))

                # Baseline comparison
                orig_norm = baseline_map.get((model_id, c), None)
                if orig_norm is not None:
                    pct_diff = abs(reproduced_norm - orig_norm) / orig_norm * 100.0
                    exceeds_1pct = pct_diff > 1.0
                else:
                    pct_diff = 0.0
                    exceeds_1pct = False

                flag_str = "FLAGGED (>1%)" if exceeds_1pct else "OK (<=1%)"
                print(f"      Class {c}: orig={orig_norm:.4f} | repro={reproduced_norm:.4f} | diff={pct_diff:.2f}% | {flag_str}", flush=True)

                all_comparison_results.append({
                    "model_id": model_id,
                    "class": c,
                    "original_norm": round(orig_norm, 4) if orig_norm else None,
                    "reproduced_norm": round(reproduced_norm, 4),
                    "percent_difference": round(pct_diff, 4),
                    "exceeds_1pct": bool(exceeds_1pct),
                    "mask_file": mask_save_file,
                    "pattern_file": pattern_save_file
                })

            # 5. SHA-256 after all 5 classes for this model
            sha_after = compute_sha256(model_path)
            print(f"    SHA-256 after:  {sha_after}", flush=True)

            if sha_before != sha_after:
                print(f"FATAL: SHA-256 mismatch for {model_id}!", file=sys.stderr, flush=True)
                hash_verification_records.append({
                    "model_id": model_id,
                    "status": "MISMATCH",
                    "before": sha_before,
                    "after": sha_after
                })
                break
            else:
                print(f"    SHA-256 verified identical: MATCH", flush=True)
                hash_verification_records.append({
                    "model_id": model_id,
                    "status": "MATCH",
                    "sha256": sha_after
                })

            elapsed = time.time() - model_start_time
            print(f"    Completed {model_id} in {elapsed:.2f}s (~{elapsed/60:.2f}m)\n", flush=True)

            # Persist intermediate logs
            with open(LOG_JSON_PATH, "w") as f:
                json.dump(all_comparison_results, f, indent=2)

            del model
            if device.type == "cuda":
                torch.cuda.empty_cache()

        except Exception as e:
            print(f"ERROR processing {model_id}: {str(e)}", file=sys.stderr, flush=True)
            break

    total_time = time.time() - total_start_time

    print("==============================================================", flush=True)
    print("STEP 4a SUMMARY REPORT", flush=True)
    print("==============================================================", flush=True)
    print(f"Total (model, class) pairs processed: {len(all_comparison_results)}/75", flush=True)
    print(f"Total tensor pairs saved: {len(saved_tensor_pairs)}/75 (150 .pt files)", flush=True)
    print(f"SHA-256 verified identical: {len([r for r in hash_verification_records if r['status'] == 'MATCH'])}/{len(manifest)} models", flush=True)
    print(f"Total wall-clock time: {total_time:.2f}s ({total_time/60:.2f} minutes)", flush=True)
    print(f"Tensors saved in: {TRIGGERS_DIR}", flush=True)
    print("==============================================================", flush=True)


if __name__ == "__main__":
    main()
