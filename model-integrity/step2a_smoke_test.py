#!/usr/bin/env python3
"""
SentinelVision - Stage 4 Step 2a: Neural Cleanse Smoke Test
Model: id-00000028 ONLY
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

from calibrate_channel_order import patch_model

warnings.filterwarnings("ignore")

MODEL_ID = "id-00000028"
BASE_DIR = f"/home/anyone/projects/SentinelVision/model-integrity/data/trojai_sample/{MODEL_ID}"
MANIFEST_PATH = "/home/anyone/projects/SentinelVision/model-integrity/calibration_manifest.json"
MODEL_PATH = os.path.join(BASE_DIR, "model.pt")
EXAMPLE_DATA_DIR = os.path.join(BASE_DIR, "example_data")
CSV_PATH = os.path.join(EXAMPLE_DATA_DIR, "data.csv")


def compute_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return f"{h.hexdigest()}  {filepath}"


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
    raise ValueError("Could not determine output dimension of final classification layer from model architecture")


def load_image(path, channel_order="BGR"):
    img = Image.open(path).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0  # HWC, [0, 1]
    if channel_order == "BGR":
        arr = arr[:, :, ::-1].copy()
    return torch.from_numpy(arr).permute(2, 0, 1)  # CHW


def main():
    print("==================================================")
    print(f"Starting Neural Cleanse Smoke Test for {MODEL_ID}")
    print("==================================================")

    start_wall_clock = time.time()

    # Step 5 checkpoint (before)
    sha256_before = compute_sha256(MODEL_PATH)
    print(f"[CHECKPOINT] sha256sum before:\n{sha256_before}\n")

    # 1. Device & Model Loading
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    device_str = "GPU (cuda)" if device.type == "cuda" else "CPU"
    print(f"[1] Execution Device: {device_str}")

    model = torch.load(MODEL_PATH, map_location=device, weights_only=False)
    patch_model(model)
    model = model.to(device)
    model.eval()

    num_classes, det_method = get_num_classes(model)
    print(f"[1] Detected {num_classes} classes via: {det_method}")

    # 2. Manifest & Data Loading
    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)
    model_entry = next((item for item in manifest if item["model_id"] == MODEL_ID), None)
    if not model_entry:
        raise ValueError(f"Model {MODEL_ID} not found in calibration manifest")
    channel_order = model_entry.get("chosen_channel_order", "BGR")
    print(f"[2] Calibration manifest channel order: {channel_order}")

    df = pd.read_csv(CSV_PATH)
    print(f"[2] Loaded data.csv: {len(df)} records")

    # Preload images grouped by true_label
    images_by_class = {}
    for c in range(num_classes):
        class_df = df[df["true_label"] == c]
        images_by_class[c] = []
        for _, row in class_df.iterrows():
            img_p = os.path.join(EXAMPLE_DATA_DIR, row["file"])
            images_by_class[c].append(load_image(img_p, channel_order=channel_order))
        print(f"    Class {c}: {len(images_by_class[c])} images loaded")

    # 3. Freeze all target model parameters
    for param in model.parameters():
        param.requires_grad = False
    print("\n[3] All target model parameters frozen (requires_grad = False)\n")

    # 4. Loop over each output class c
    reg_lambda = 0.01
    print("[4] Optimization config: Adam lr=0.1, 300 steps per class")
    print(f"    Regularization lambda = {reg_lambda} (fixed starting value, not yet calibrated per Section 6 Step 3's later guidance)\n")

    results = []

    for c in range(num_classes):
        print(f"--- Processing Target Class {c} ---")
        
        # 4a. Select batch of example images whose true_label != c (spanning other classes)
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
        print(f"    Selected batch size: {batch_size} images spanning classes {other_classes}")

        # 4b. Initialize mask and pattern tensors with requires_grad=True
        # Sigmoid-parameterized underlying tensors
        mask_param = torch.zeros(1, 1, H, W, device=device, requires_grad=True)
        pattern_param = torch.zeros(1, 3, H, W, device=device, requires_grad=True)

        # 4e. Optimizer: Adam on mask/pattern only
        optimizer = torch.optim.Adam([mask_param, pattern_param], lr=0.1)

        loss_0 = None
        loss_150 = None
        loss_300 = None

        for step in range(301):
            optimizer.zero_grad()

            # 4b/c. Sigmoid constraints and composite
            mask = torch.sigmoid(mask_param)
            pattern = torch.sigmoid(pattern_param)
            x_masked = (1.0 - mask) * x + mask * pattern

            # 4d. Forward and loss
            out = model(x_masked)
            if hasattr(out, "logits"):
                out = out.logits

            ce_loss = F.cross_entropy(out, target_tensor)
            reg_loss = reg_lambda * mask.sum()
            loss = ce_loss + reg_loss

            if step == 0:
                loss_0 = loss.item()
                ce_0 = ce_loss.item()
                norm_0 = mask.sum().item()
                print(f"    Step   0: Loss={loss_0:.4f} (CE={ce_0:.4f}, Reg={reg_loss.item():.4f}, ||mask||_1={norm_0:.2f})")

            if step == 150:
                loss_150 = loss.item()
                ce_150 = ce_loss.item()
                norm_150 = mask.sum().item()
                print(f"    Step 150: Loss={loss_150:.4f} (CE={ce_150:.4f}, Reg={reg_loss.item():.4f}, ||mask||_1={norm_150:.2f})")

            if step == 300:
                loss_300 = loss.item()
                ce_300 = ce_loss.item()
                norm_300 = mask.sum().item()
                print(f"    Step 300: Loss={loss_300:.4f} (CE={ce_300:.4f}, Reg={reg_loss.item():.4f}, ||mask||_1={norm_300:.2f})")
                break

            loss.backward()
            optimizer.step()

        final_mask_norm = mask.sum().item()
        results.append({
            "class": c,
            "loss_0": loss_0,
            "loss_150": loss_150,
            "loss_300": loss_300,
            "final_mask_norm": final_mask_norm
        })
        print(f"    Class {c} completed: final ||mask||_1 = {final_mask_norm:.4f}\n")

    # 5. Verification checkpoint (after)
    sha256_after = compute_sha256(MODEL_PATH)
    print(f"[CHECKPOINT] sha256sum after:\n{sha256_after}\n")

    if sha256_before != sha256_after:
        print("FATAL ERROR: sha256sum mismatch before and after optimization!", file=sys.stderr)
        sys.exit(1)
    else:
        print("[CHECKPOINT] sha256sum verification: PASSED (model.pt is identical and unmodified)\n")

    total_wall_clock = time.time() - start_wall_clock

    print("==================================================")
    print(f"SUMMARY REPORT FOR {MODEL_ID}")
    print("==================================================")
    print(f"1. Number of classes detected: {num_classes} (determined via {det_method})")
    print("2. Per-class loss progression and final ||mask||_1:")
    for r in results:
        print(f"   Class {r['class']}: Step 0 = {r['loss_0']:.4f} | Step 150 = {r['loss_150']:.4f} | Step 300 = {r['loss_300']:.4f} | Final ||mask||_1 = {r['final_mask_norm']:.4f}")
    print("3. Raw sha256sum output:")
    print(f"   Before: {sha256_before}")
    print(f"   After:  {sha256_after}")
    print(f"4. Total wall-clock time: {total_wall_clock:.2f}s ({total_wall_clock/60:.2f} minutes) on {device_str}")
    print("==================================================")


if __name__ == "__main__":
    main()
