#!/usr/bin/env python3
"""
SentinelVision - Stage 4 Step 2c: Neural Cleanse Re-run (1000 Steps)
Diagnostic experiment to test if 300-step masks were under-converged.
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
RESULTS_PATH = os.path.join(BASE_DIR, "neural_cleanse_results_1000steps.json")
LOSS_LOG_PATH = os.path.join(BASE_DIR, "loss_progression_1000steps.json")

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
    print("Starting Step 2c: Neural Cleanse (1000 Steps) across ALL 15 Models on GPU", flush=True)
    print("==============================================================", flush=True)

    total_start_time = time.time()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using execution device: {device} ({torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'})", flush=True)

    if not os.path.exists(MANIFEST_PATH):
        raise FileNotFoundError(f"Calibration manifest not found: {MANIFEST_PATH}")

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    print(f"Loaded calibration manifest with {len(manifest)} models.\n", flush=True)

    reg_lambda = 0.01
    lr = 0.1
    steps = 1000

    all_results = []
    all_loss_records = []
    completed_models = []
    failed_models = []
    hash_verification_records = []

    for idx, entry in enumerate(manifest, 1):
        model_id = entry["model_id"]
        channel_order = entry.get("chosen_channel_order", "BGR")
        model_dir = os.path.join(DATA_DIR, model_id)
        model_path = os.path.join(model_dir, "model.pt")
        example_data_dir = os.path.join(model_dir, "example_data")
        csv_path = os.path.join(example_data_dir, "data.csv")

        print(f"[{idx}/{len(manifest)}] Processing {model_id}...", flush=True)
        print(f"    Channel order from manifest: {channel_order}", flush=True)

        # Check sha256 before
        sha_before = compute_sha256(model_path)
        print(f"    SHA-256 before: {sha_before}", flush=True)

        model_start_time = time.time()

        try:
            # Read model.pt fresh for each model
            model = torch.load(model_path, map_location=device, weights_only=False)
            patch_model(model)
            model = model.to(device)
            model.eval()

            for param in model.parameters():
                param.requires_grad = False

            num_classes, det_desc = get_num_classes(model)
            print(f"    Detected {num_classes} classes via {det_desc}", flush=True)

            df = pd.read_csv(csv_path)
            images_by_class = {}
            for c in range(num_classes):
                class_df = df[df["true_label"] == c]
                images_by_class[c] = []
                for _, row in class_df.iterrows():
                    img_p = os.path.join(example_data_dir, row["file"])
                    images_by_class[c].append(load_image(img_p, channel_order=channel_order))

            model_class_results = []
            model_loss_history = []

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

                loss_0 = None
                loss_300 = None
                loss_600 = None
                loss_1000 = None

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

                    if step == 0:
                        loss_0 = loss.item()
                    elif step == 300:
                        loss_300 = loss.item()
                    elif step == 600:
                        loss_600 = loss.item()
                    elif step == 1000:
                        loss_1000 = loss.item()

                    if step == steps:
                        break

                    loss.backward()
                    optimizer.step()

                final_norm = float(mask.sum().item())
                entry_data = {
                    "model_id": model_id,
                    "class": c,
                    "mask_l1_norm": round(final_norm, 4),
                    "channel_order_used": channel_order,
                    "num_classes_detected": num_classes
                }
                loss_entry = {
                    "model_id": model_id,
                    "class": c,
                    "loss_0": round(loss_0, 4),
                    "loss_300": round(loss_300, 4),
                    "loss_600": round(loss_600, 4),
                    "loss_1000": round(loss_1000, 4),
                    "mask_l1_norm": round(final_norm, 4)
                }
                model_class_results.append(entry_data)
                model_loss_history.append(loss_entry)
                all_results.append(entry_data)
                all_loss_records.append(loss_entry)

                print(f"      Class {c}: step 0={loss_0:.4f} | step 300={loss_300:.4f} | step 600={loss_600:.4f} | step 1000={loss_1000:.4f} | norm={final_norm:.4f}", flush=True)

            # Check sha256 after
            sha_after = compute_sha256(model_path)
            print(f"    SHA-256 after:  {sha_after}", flush=True)

            if sha_before != sha_after:
                print(f"FATAL: SHA-256 mismatch for {model_id}!", file=sys.stderr, flush=True)
                print(f"  Before: {sha_before}", file=sys.stderr, flush=True)
                print(f"  After:  {sha_after}", file=sys.stderr, flush=True)
                failed_models.append((model_id, "SHA-256 hash mismatch"))
                hash_verification_records.append({"model_id": model_id, "status": "FAILED", "before": sha_before, "after": sha_after})
                break
            else:
                print(f"    SHA-256 verified identical: MATCH", flush=True)
                hash_verification_records.append({"model_id": model_id, "status": "MATCH", "sha256": sha_after})

            elapsed = time.time() - model_start_time
            print(f"    Completed {model_id} in {elapsed:.2f}s (~{elapsed/60:.2f}m)\n", flush=True)
            completed_models.append(model_id)

            # Save progress incrementally
            with open(RESULTS_PATH, "w") as f:
                json.dump(all_results, f, indent=2)
            with open(LOSS_LOG_PATH, "w") as f:
                json.dump(all_loss_records, f, indent=2)

            del model
            if device.type == "cuda":
                torch.cuda.empty_cache()

        except Exception as e:
            print(f"ERROR processing {model_id}: {str(e)}", file=sys.stderr, flush=True)
            failed_models.append((model_id, str(e)))
            break

    total_time = time.time() - total_start_time

    print("==============================================================", flush=True)
    print("STEP 2c (1000 STEPS) RUN SUMMARY", flush=True)
    print("==============================================================", flush=True)
    print(f"Models successfully processed: {len(completed_models)}/{len(manifest)}", flush=True)
    print(f"Hash verification: {len([r for r in hash_verification_records if r['status'] == 'MATCH'])}/{len(manifest)} match", flush=True)
    if failed_models:
        print(f"Failed models: {failed_models}", flush=True)
    print(f"Total wall-clock time: {total_time:.2f}s ({total_time/60:.2f} minutes)", flush=True)
    print(f"Results saved to: {RESULTS_PATH}", flush=True)
    print(f"Loss logs saved to: {LOSS_LOG_PATH}", flush=True)
    print("==============================================================", flush=True)


if __name__ == "__main__":
    main()
