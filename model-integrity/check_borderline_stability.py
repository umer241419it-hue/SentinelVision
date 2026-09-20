#!/usr/bin/env python3
"""
SentinelVision - Borderline Stability Check
Evaluates whether GPU non-determinism affects the 2.0 anomaly threshold verdict
for the 6 borderline models:
  - id-00000173 (Class 2, orig 1.9676)
  - id-00000278 (Class 4, orig 1.8930)
  - id-00000838 (Class 0, orig 1.8392)
  - id-00000621 (Class 0, orig 2.1923)
  - id-00000637 (Class 1, orig 2.2541)
  - id-00000912 (Class 3, orig 2.4258)
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
BASELINE_PATH = os.path.join(BASE_DIR, "neural_cleanse_results.json")
MAD_RESULTS_PATH = os.path.join(BASE_DIR, "mad_results.json")

sys.path.insert(0, BASE_DIR)
from calibrate_channel_order import patch_model

NORMAL_SCALE = 1.4826
THRESHOLD = 2.0

BORDERLINE_CONFIG = [
    {"model_id": "id-00000173", "target_class": 2},
    {"model_id": "id-00000278", "target_class": 4},
    {"model_id": "id-00000838", "target_class": 0},
    {"model_id": "id-00000621", "target_class": 0},
    {"model_id": "id-00000637", "target_class": 1},
    {"model_id": "id-00000912", "target_class": 3},
]


def compute_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return h.hexdigest()


def compute_mad_anomaly_index(mask_norms):
    norms = np.asarray(mask_norms, dtype=np.float64)
    med = float(np.median(norms))
    mad = float(np.median(np.abs(norms - med)))
    if mad == 0.0:
        return [0.0] * len(norms), 0.0, 0
    scale = mad * NORMAL_SCALE
    anom = [float(max(0.0, med - m) / scale) for m in norms]
    max_a = float(max(anom))
    flagged_c = int(np.argmax(anom))
    return anom, max_a, flagged_c


def load_image(path, channel_order="BGR"):
    img = Image.open(path).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    if channel_order == "BGR":
        arr = arr[:, :, ::-1].copy()
    return torch.from_numpy(arr).permute(2, 0, 1)


def main():
    print("==============================================================", flush=True)
    print("Starting Borderline Stability Check (6 Models, 3 Runs Each)", flush=True)
    print("==============================================================\n", flush=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device} ({torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'})\n", flush=True)

    with open(BASELINE_PATH) as f:
        baseline_data = json.load(f)

    with open(MAD_RESULTS_PATH) as f:
        orig_mad_data = {item["model_id"]: item for item in json.load(f)}

    summary_results = []
    hash_records = []

    for item in BORDERLINE_CONFIG:
        model_id = item["model_id"]
        target_c = item["target_class"]

        model_dir = os.path.join(DATA_DIR, model_id)
        model_path = os.path.join(model_dir, "model.pt")
        csv_path = os.path.join(model_dir, "example_data", "data.csv")

        # Get original 5-class norms
        orig_entries = [x for x in baseline_data if x["model_id"] == model_id]
        orig_entries.sort(key=lambda x: x["class"])
        orig_norms = [e["mask_l1_norm"] for e in orig_entries]
        channel_order = orig_entries[0]["channel_order_used"]

        orig_mad_entry = orig_mad_data[model_id]
        orig_anom_val = orig_mad_entry["max_anomaly_index"]
        orig_flagged = orig_mad_entry["flagged"]

        print(f"--- Model: {model_id} (Target Class: {target_c}) ---", flush=True)
        print(f"    Original Norm: {orig_norms[target_c]:.4f} | Anomaly Index: {orig_anom_val:.4f} | Flagged: {orig_flagged}", flush=True)

        sha_before = compute_sha256(model_path)

        model = torch.load(model_path, map_location=device, weights_only=False)
        patch_model(model)
        model = model.to(device).eval()
        for p in model.parameters():
            p.requires_grad = False

        df = pd.read_csv(csv_path)
        images_by_class = {}
        for c in range(5):
            class_df = df[df["true_label"] == c]
            images_by_class[c] = []
            for _, row in class_df.iterrows():
                img_p = os.path.join(model_dir, "example_data", row["file"])
                images_by_class[c].append(load_image(img_p, channel_order=channel_order))

        other_classes = [oc for oc in range(5) if oc != target_c]
        batch_tensors = []
        for oc in other_classes:
            for i in range(2):
                batch_tensors.append(images_by_class[oc][i])

        x = torch.stack(batch_tensors).to(device)
        H, W = x.shape[2], x.shape[3]
        target_tensor = torch.full((x.shape[0],), target_c, dtype=torch.long, device=device)

        new_norms = []
        new_anom_indices = []
        new_flagged_statuses = []

        for run_idx in range(1, 4):
            # Zeros initialization (same as Step 2b / Step 4a)
            mask_param = torch.zeros(1, 1, H, W, device=device, requires_grad=True)
            pattern_param = torch.zeros(1, 3, H, W, device=device, requires_grad=True)
            optimizer = torch.optim.Adam([mask_param, pattern_param], lr=0.1)

            for step in range(301):
                optimizer.zero_grad()
                mask = torch.sigmoid(mask_param)
                pattern = torch.sigmoid(pattern_param)
                x_masked = (1.0 - mask) * x + mask * pattern
                out = model(x_masked)
                if hasattr(out, "logits"):
                    out = out.logits
                ce_loss = F.cross_entropy(out, target_tensor)
                reg_loss = 0.01 * mask.sum()
                loss = ce_loss + reg_loss
                if step == 300:
                    break
                loss.backward()
                optimizer.step()

            repro_norm = float(mask.sum().item())
            new_norms.append(repro_norm)

            # Substitute for target_c in the 5-class norms vector
            substituted_norms = list(orig_norms)
            substituted_norms[target_c] = repro_norm

            per_class_anom, max_anom, fl_class = compute_mad_anomaly_index(substituted_norms)
            target_anom = per_class_anom[target_c]
            is_flagged = bool(target_anom > THRESHOLD)

            new_anom_indices.append(target_anom)
            new_flagged_statuses.append(is_flagged)

            print(f"    Run {run_idx}: Norm={repro_norm:.4f} | Anom Index={target_anom:.4f} | Flagged={is_flagged}", flush=True)

        sha_after = compute_sha256(model_path)
        sha_match = (sha_before == sha_after)
        hash_records.append({"model_id": model_id, "sha256": sha_after, "match": sha_match})

        # Check stability across all 4 versions (orig + 3 new)
        all_flagged = [orig_flagged] + new_flagged_statuses
        is_stable = all(f == orig_flagged for f in all_flagged)
        verdict_str = "STABLE" if is_stable else "UNSTABLE (FLIPPED)"

        print(f"    Verdict: {verdict_str} (SHA-256: {'MATCH' if sha_match else 'FAIL'})\n", flush=True)

        summary_results.append({
            "model_id": model_id,
            "target_class": target_c,
            "orig_norm": orig_norms[target_c],
            "orig_anomaly_index": orig_anom_val,
            "orig_flagged": orig_flagged,
            "new_norms": new_norms,
            "new_anomaly_indices": new_anom_indices,
            "new_flagged_statuses": new_flagged_statuses,
            "is_stable": is_stable,
            "sha_match": sha_match
        })

        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()

    print("==============================================================", flush=True)
    print("BORDERLINE STABILITY SUMMARY", flush=True)
    print("==============================================================", flush=True)
    stable_count = sum(1 for r in summary_results if r["is_stable"])
    print(f"Total Borderline Models Tested: {len(summary_results)}")
    print(f"Stable Models (0 flips): {stable_count}/{len(summary_results)}")
    print(f"Unstable Models (>=1 flip): {len(summary_results) - stable_count}/{len(summary_results)}")
    if stable_count < len(summary_results):
        unstable_models = [r["model_id"] for r in summary_results if not r["is_stable"]]
        print(f"Unstable models: {', '.join(unstable_models)}")
    print("==============================================================", flush=True)


if __name__ == "__main__":
    main()
