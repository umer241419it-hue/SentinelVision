#!/usr/bin/env python3
"""
SentinelVision - Step 0: Preprocessing Calibration
Evaluates channel ordering (RGB vs BGR) per model across Tier A, B, C, D label sources.
Includes self-tests for Tier B and Tier C using temporary synthetic copies of id-00000028.
"""

import os
import re
import shutil
import tempfile
import torch
import torch.nn as nn
import pandas as pd
import numpy as np
from PIL import Image

BASE = "data/trojai_sample"


def load_image(path):
    img = Image.open(path).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0  # HWC, RGB, [0,1]
    return arr


def patch_model(model):
    """
    Ensures compatibility for models trained on older torchvision versions
    (e.g., Inception3 where submodules were refactored into nn.Module fields).
    """
    if type(model).__name__ == "Inception3":
        if not hasattr(model, "maxpool1"):
            model.maxpool1 = nn.MaxPool2d(kernel_size=3, stride=2)
        if not hasattr(model, "maxpool2"):
            model.maxpool2 = nn.MaxPool2d(kernel_size=3, stride=2)
        if not hasattr(model, "avgpool"):
            model.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        if not hasattr(model, "dropout"):
            model.dropout = nn.Dropout(p=0.5)
        if not hasattr(model, "AuxLogits"):
            model.AuxLogits = getattr(model, "aux_logits", None)
            if model.AuxLogits is False:
                model.AuxLogits = None


def infer_label_from_name(path):
    """
    Tier B heuristic: Infer class label from parent folder or filename.
    Matches patterns like class_0, class-0, or class_0_example_3.png.
    """
    fname = os.path.basename(path)
    parent = os.path.basename(os.path.dirname(path))

    # 1. Filename pattern
    m = re.search(r"class[_-]?(\d+)", fname, re.IGNORECASE)
    if m:
        return int(m.group(1))

    # 2. Parent directory pattern
    m = re.search(r"class[_-]?(\d+)", parent, re.IGNORECASE)
    if m:
        return int(m.group(1))
    if parent.isdigit():
        return int(parent)

    return None


def determine_label_tier_and_data(model_dir, example_dir_override=None):
    """
    Determines whether model data qualifies for Tier A, Tier B, Tier C, or Tier D.
    Returns: (tier, image_data_list)
    where image_data_list contains dicts: {'path': full_path, 'label': label_or_None}
    """
    ex_dir = example_dir_override if example_dir_override else os.path.join(model_dir, "example_data")
    if not os.path.isdir(ex_dir):
        return "TIER_D", []

    # Find all image files
    image_files = []
    for root, _, files in os.walk(ex_dir):
        for f in sorted(files):
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                image_files.append(os.path.join(root, f))

    if not image_files:
        return "TIER_D", []

    # Check Tier A: CSV with true_label
    csv_path = os.path.join(ex_dir, "data.csv")
    if os.path.isfile(csv_path):
        try:
            df = pd.read_csv(csv_path)
            if "true_label" in df.columns:
                file_col = "file" if "file" in df.columns else df.columns[0]
                data_list = []
                for _, row in df.iterrows():
                    img_path = os.path.join(ex_dir, str(row[file_col]))
                    if os.path.isfile(img_path):
                        data_list.append({"path": img_path, "label": int(row["true_label"])})
                if data_list:
                    return "TIER_A", data_list
        except Exception:
            pass

    # Check Tier B: Infer labels from filename or folder structure
    inferred_data = []
    all_inferred = True
    for img_path in image_files:
        lbl = infer_label_from_name(img_path)
        if lbl is None:
            all_inferred = False
            break
        inferred_data.append({"path": img_path, "label": lbl})

    if all_inferred and inferred_data:
        return "TIER_B", inferred_data

    # Tier C: Images exist, but no labels available
    data_list = [{"path": p, "label": None} for p in image_files]
    return "TIER_C", data_list


def eval_accuracy(model, data_list, channel_order="RGB"):
    correct, failed = 0, 0
    for item in data_list:
        try:
            arr = load_image(item["path"])
        except Exception:
            failed += 1
            continue
        if channel_order == "BGR":
            arr = arr[:, :, ::-1].copy()
        x = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)
        with torch.no_grad():
            out = model(x)
            if hasattr(out, "logits"):
                out = out.logits
            pred = out.argmax(dim=1).item()
        correct += (pred == item["label"])

    total = len(data_list) - failed
    acc = (correct / total * 100) if total > 0 else float("nan")
    return acc, failed, total


def eval_entropy(model, data_list, channel_order="RGB"):
    entropies = []
    preds = []
    failed = 0
    for item in data_list:
        try:
            arr = load_image(item["path"])
        except Exception:
            failed += 1
            continue
        if channel_order == "BGR":
            arr = arr[:, :, ::-1].copy()
        x = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)
        with torch.no_grad():
            out = model(x)
            if hasattr(out, "logits"):
                out = out.logits
            prob = torch.softmax(out, dim=1).squeeze(0)
            pred = prob.argmax().item()
            ent = -(prob * torch.log(prob + 1e-12)).sum().item()
        preds.append(pred)
        entropies.append(ent)

    if not entropies:
        return float("nan"), 0, failed

    avg_entropy = float(np.mean(entropies))
    distinct_classes = len(set(preds))
    return avg_entropy, distinct_classes, failed


def calibrate_model(model_dir, example_dir_override=None):
    model_path = os.path.join(model_dir, "model.pt")
    if not os.path.isfile(model_path):
        return {
            "tier": "TIER_D",
            "rgb_metric": "N/A",
            "bgr_metric": "N/A",
            "chosen_order": "N/A",
            "status": "CALIBRATION_IMPOSSIBLE"
        }

    tier, data_list = determine_label_tier_and_data(model_dir, example_dir_override)

    if tier == "TIER_D" or not data_list:
        return {
            "tier": "TIER_D",
            "rgb_metric": "N/A",
            "bgr_metric": "N/A",
            "chosen_order": "N/A",
            "status": "CALIBRATION_IMPOSSIBLE"
        }

    model = torch.load(model_path, map_location="cpu", weights_only=False)
    patch_model(model)
    model.eval()

    if tier in ("TIER_A", "TIER_B"):
        acc_rgb, _, _ = eval_accuracy(model, data_list, "RGB")
        acc_bgr, _, _ = eval_accuracy(model, data_list, "BGR")

        rgb_metric = f"{acc_rgb:.2f}%"
        bgr_metric = f"{acc_bgr:.2f}%"

        if max(acc_rgb, acc_bgr) < 70.0:
            status = "CALIBRATION_FAILED"
            chosen_order = "BGR" if acc_bgr > acc_rgb else ("RGB" if acc_rgb > acc_bgr else "UNCERTAIN")
        else:
            status = "OK"
            chosen_order = "BGR" if acc_bgr > acc_rgb else "RGB"

        return {
            "tier": tier,
            "rgb_metric": rgb_metric,
            "bgr_metric": bgr_metric,
            "chosen_order": chosen_order,
            "status": status,
            "acc_rgb": acc_rgb,
            "acc_bgr": acc_bgr
        }

    elif tier == "TIER_C":
        ent_rgb, k_rgb, _ = eval_entropy(model, data_list, "RGB")
        ent_bgr, k_bgr, _ = eval_entropy(model, data_list, "BGR")

        rgb_metric = f"H={ent_rgb:.4f} (k={k_rgb})"
        bgr_metric = f"H={ent_bgr:.4f} (k={k_bgr})"

        if k_rgb <= 1 and k_bgr <= 1:
            status = "CALIBRATION_UNCERTAIN"
            chosen_order = "UNCERTAIN"
        elif k_rgb > 1 and k_bgr <= 1:
            status = "OK"
            chosen_order = "RGB"
        elif k_bgr > 1 and k_rgb <= 1:
            status = "OK"
            chosen_order = "BGR"
        else:
            chosen_order = "BGR" if ent_bgr < ent_rgb else "RGB"
            status = "OK"

        return {
            "tier": tier,
            "rgb_metric": rgb_metric,
            "bgr_metric": bgr_metric,
            "chosen_order": chosen_order,
            "status": status,
            "ent_rgb": ent_rgb,
            "ent_bgr": ent_bgr,
            "k_rgb": k_rgb,
            "k_bgr": k_bgr
        }


def run_self_tests(target_model="id-00000028"):
    orig_dir = os.path.join(BASE, target_model)
    orig_ex = os.path.join(orig_dir, "example_data")
    orig_csv = os.path.join(orig_ex, "data.csv")

    temp_root = tempfile.mkdtemp(prefix="sentinel_selftest_")
    try:
        df = pd.read_csv(orig_csv)

        # (a) Synthetic Tier B: delete data.csv and encode class in filename
        temp_b = os.path.join(temp_root, "tier_b")
        os.makedirs(temp_b, exist_ok=True)
        for i, row in df.iterrows():
            src_f = os.path.join(orig_ex, str(row["file"]))
            lbl = int(row["true_label"])
            dst_f = os.path.join(temp_b, f"class_{lbl}_sample_{i:04d}.png")
            shutil.copy(src_f, dst_f)

        res_b = calibrate_model(orig_dir, example_dir_override=temp_b)

        # (b) Synthetic Tier C: delete data.csv and strip any class-identifying filename/folder info
        temp_c = os.path.join(temp_root, "tier_c")
        os.makedirs(temp_c, exist_ok=True)
        for i, row in df.iterrows():
            src_f = os.path.join(orig_ex, str(row["file"]))
            dst_f = os.path.join(temp_c, f"unlabeled_image_{i:04d}.png")
            shutil.copy(src_f, dst_f)

        res_c = calibrate_model(orig_dir, example_dir_override=temp_c)

        return res_b, res_c
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    # 1. Run Self-Tests
    print("=== SELF-TEST RESULTS (Synthetic Tier B & Tier C on id-00000028) ===")
    res_b, res_c = run_self_tests("id-00000028")

    tier_b_name = res_b["tier"].replace("TIER_", "Tier ")
    print(f"Self-Test (a) [Tier B - Inferred Filename Labels]:")
    print(f"  Detected Tier   : {tier_b_name}")
    print(f"  RGB Accuracy    : {res_b['rgb_metric']}")
    print(f"  BGR Accuracy    : {res_b['bgr_metric']}")
    print(f"  Chosen Order    : {res_b['chosen_order']}")
    print(f"  Status          : {res_b['status']}")

    tier_c_name = res_c["tier"].replace("TIER_", "Tier ")
    print(f"\nSelf-Test (b) [Tier C - Unsupervised Entropy Heuristic]:")
    print(f"  Detected Tier   : {tier_c_name}")
    print(f"  RGB Entropy     : {res_c['rgb_metric']}")
    print(f"  BGR Entropy     : {res_c['bgr_metric']}")
    print(f"  Chosen Order    : {res_c['chosen_order']}")
    print(f"  Status          : {res_c['status']}")
    print("  Temporary synthetic directories cleanly removed.\n")

    # 2. Run on all 15 real models
    print("=== REAL 15-MODEL CALIBRATION TABLE ===")
    model_ids = sorted([d for d in os.listdir(BASE) if os.path.isdir(os.path.join(BASE, d)) and d.startswith("id-")])

    header = f"{'model_id':<15} | {'label_tier':<10} | {'rgb_acc_or_entropy':<20} | {'bgr_acc_or_entropy':<20} | {'chosen_order':<12} | {'status':<22}"
    divider = "-" * len(header)
    print(header)
    print(divider)

    for mid in model_ids:
        mdir = os.path.join(BASE, mid)
        res = calibrate_model(mdir)
        tier_display = res["tier"].replace("TIER_", "Tier ")
        print(f"{mid:<15} | {tier_display:<10} | {res['rgb_metric']:>20} | {res['bgr_metric']:>20} | {res['chosen_order']:^12} | {res['status']:<22}")
