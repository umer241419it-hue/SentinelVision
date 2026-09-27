#!/usr/bin/env python3
"""
SentinelVision - Stage 4 Step 5: STRIP (STRong Intentional Perturbation) Detector
Validated production version ? mask-preserving overlay (trigger region kept at full
strength, blend applied only outside the mask) ? superseding two earlier rejected
attempts now archived in experiments/ (uniform 50/50 blend, and uniform 85/15 blend),
both kept for the record with their own results intact.
Following Section 10 file structure (model-integrity/src/strip_detector.py).

Protocol Constraints:
- Zero ground truth data leakage: never open ground_truth.csv or METADATA.csv.
- Model treated as QUERY-ONLY: model(x) evaluated under torch.no_grad() and model.eval().
- Real live SHA-256 weight hashes verified before and after each model.
- Base queries constructed from donor images of non-target classes.
- Real-trigger condition uses reconstructed (mask, pattern) from model-integrity/triggers/.
- Random-control condition uses reproducible uniform random pattern with real mask.
- 10 unrelated overlay images superimposed at 50/50 blend per base query.
- Shannon entropy computed on mean softmax probability vectors across variants.
- Entropy deficit reported as: mean_entropy_random_control - mean_entropy_real_trigger.
"""

import os
import sys
import json
import time
import hashlib
from typing import List, Dict, Any, Tuple
import numpy as np
import pandas as pd
from PIL import Image
import torch
import torch.nn as nn

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from calibrate_channel_order import patch_model


def compute_sha256(filepath: str) -> str:
    """Computes SHA-256 hash of a file for integrity verification."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return h.hexdigest()


def load_image_tensor(path: str, channel_order: str = "BGR") -> torch.Tensor:
    """Loads image, normalizes to [0,1], applies channel ordering, returns 3xHxW tensor."""
    img = Image.open(path).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    if channel_order == "BGR":
        arr = arr[:, :, ::-1].copy()
    return torch.from_numpy(arr).permute(2, 0, 1)


def stratify_donors(images_by_class: Dict[int, List[Tuple[str, torch.Tensor]]],
                    target_class: int,
                    target_count: int = 10) -> List[Tuple[str, torch.Tensor]]:
    """
    Selects target_count donor images from all other classes, stratified evenly.
    Returns: list of (filename, tensor) tuples.
    """
    num_classes = len(images_by_class)
    other_classes = [c for c in range(num_classes) if c != target_class]
    m_others = len(other_classes)
    
    base_per_class = target_count // m_others
    remainder = target_count % m_others
    
    selected_donors = []
    for idx, c in enumerate(other_classes):
        quota = base_per_class + (1 if idx < remainder else 0)
        c_imgs = images_by_class[c]
        selected_donors.extend(c_imgs[:quota])
        
    return selected_donors


def compute_shannon_entropy(mean_prob: torch.Tensor) -> float:
    """
    Computes Shannon entropy H = -sum(p_i * log(p_i)) over classes.
    Uses 1e-12 clamp to prevent log(0).
    """
    p = mean_prob.clamp(min=1e-12)
    ent = -(p * torch.log(p)).sum().item()
    return float(ent)


def evaluate_model_strip(model_id: str,
                         manifest_entry: Dict[str, Any],
                         data_base_dir: str,
                         triggers_base_dir: str,
                         device: torch.device,
                         model_path_override: str = None) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """
    Executes STRIP evaluation for all classes of a single model.
    Treats model as QUERY-ONLY (no gradients, model.eval(), torch.no_grad()).
    Returns:
        hash_pair: {"before": sha_before, "after": sha_after}
        results_rows: list of dicts for each class
    """
    model_dir = os.path.join(data_base_dir, model_id)
    model_path = os.path.abspath(model_path_override) if model_path_override else os.path.join(model_dir, "model.pt")
    ex_data_dir = os.path.join(model_dir, "example_data")
    csv_path = os.path.join(ex_data_dir, "data.csv")
    channel_order = manifest_entry.get("chosen_channel_order", "BGR")
    
    # 1. SHA-256 Before
    sha_before = compute_sha256(model_path)
    
    # 2. Load model in query-only mode
    model = torch.load(model_path, map_location=device, weights_only=False)
    patch_model(model)
    model = model.to(device)
    model.eval()
    for param in model.parameters():
        param.requires_grad = False
        
    # 3. Load all example images and organize by class
    df = pd.read_csv(csv_path)
    all_images_pool = []
    images_by_class = {}
    
    for _, row in df.iterrows():
        fname = row["file"]
        c = int(row["true_label"])
        img_p = os.path.join(ex_data_dir, fname)
        t = load_image_tensor(img_p, channel_order=channel_order)
        item = (fname, t)
        all_images_pool.append(item)
        if c not in images_by_class:
            images_by_class[c] = []
        images_by_class[c].append(item)
        
    num_classes = len(images_by_class)
    
    model_rows = []
    
    # 4. Evaluate each class
    for c in range(num_classes):
        mask_path = os.path.join(triggers_base_dir, f"{model_id}_class{c}_mask.pt")
        pattern_path = os.path.join(triggers_base_dir, f"{model_id}_class{c}_pattern.pt")
        
        mask = torch.load(mask_path, map_location=device)
        real_pattern = torch.load(pattern_path, map_location=device)
        
        # Build reproducible random pattern for control condition
        ctrl_seed = int(hashlib.sha256(f"{model_id}_{c}_strip".encode("utf-8")).hexdigest()[:8], 16) % (2**31)
        gen = torch.Generator(device="cpu").manual_seed(ctrl_seed)
        random_pattern = torch.rand(real_pattern.shape, generator=gen, dtype=torch.float32).to(device)
        
        # Select 10 base donor images from other classes (stratified)
        donors = stratify_donors(images_by_class, c, target_count=10)
        
        entropies_real = []
        entropies_ctrl = []
        
        for k, (donor_fname, donor_tensor) in enumerate(donors):
            donor_t = donor_tensor.unsqueeze(0).to(device) # (1, 3, H, W)
            
            # Sample 10 random unrelated overlay images excluding donor_fname
            candidate_overlays = [item for item in all_images_pool if item[0] != donor_fname]
            overlay_seed = int(hashlib.sha256(f"{model_id}_{c}_base{k}_overlay".encode("utf-8")).hexdigest()[:8], 16) % (2**31)
            rng = np.random.RandomState(overlay_seed)
            chosen_indices = rng.choice(len(candidate_overlays), size=10, replace=False)
            overlay_tensors = [candidate_overlays[idx][1] for idx in chosen_indices]
            overlay_batch = torch.stack(overlay_tensors).to(device) # (10, 3, H, W)
            
            # Mask-preserving overlay: mask untouched, 50/50 donor/overlay blend only on (1-mask) region
            blended_bg = torch.clamp(0.5 * donor_t + 0.5 * overlay_batch, 0.0, 1.0)
            variants_real = torch.clamp(mask * real_pattern + (1.0 - mask) * blended_bg, 0.0, 1.0)
            variants_ctrl = torch.clamp(mask * random_pattern + (1.0 - mask) * blended_bg, 0.0, 1.0)
            
            # Query model (batched forward pass)
            with torch.no_grad():
                out_real = model(variants_real)
                if hasattr(out_real, "logits"):
                    out_real = out_real.logits
                probs_real = torch.softmax(out_real, dim=1)
                mean_p_real = probs_real.mean(dim=0)
                ent_real = compute_shannon_entropy(mean_p_real)
                entropies_real.append(ent_real)
                
                out_ctrl = model(variants_ctrl)
                if hasattr(out_ctrl, "logits"):
                    out_ctrl = out_ctrl.logits
                probs_ctrl = torch.softmax(out_ctrl, dim=1)
                mean_p_ctrl = probs_ctrl.mean(dim=0)
                ent_ctrl = compute_shannon_entropy(mean_p_ctrl)
                entropies_ctrl.append(ent_ctrl)
                
        mean_ent_real = float(np.mean(entropies_real))
        mean_ent_ctrl = float(np.mean(entropies_ctrl))
        entropy_deficit = mean_ent_ctrl - mean_ent_real
        
        row = {
            "model_id": model_id,
            "class": c,
            "mean_entropy_real_trigger": round(mean_ent_real, 4),
            "mean_entropy_random_control": round(mean_ent_ctrl, 4),
            "entropy_deficit": round(entropy_deficit, 4)
        }
        model_rows.append(row)
        
    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()
        
    # 5. SHA-256 After
    sha_after = compute_sha256(model_path)
    if sha_before != sha_after:
        raise RuntimeError(f"FATAL: SHA-256 hash mismatch for {model_id}!\nBefore: {sha_before}\nAfter:  {sha_after}")
        
    return {"before": sha_before, "after": sha_after}, model_rows


def main():
    import argparse
    parser = argparse.ArgumentParser(description="SentinelVision STRIP model-integrity detector")
    parser.add_argument("--model-path", default=None, help="Evaluate one selected .pt model instead of the calibration manifest")
    parser.add_argument("--model-id", default=None, help="Model ID used to locate calibration/triggers/example data")
    parser.add_argument("--data-dir", default=None, help="Directory containing model example-data directories")
    parser.add_argument("--triggers-dir", default=None, help="Directory containing reconstructed trigger tensors")
    parser.add_argument("--manifest", default=None, help="Calibration manifest JSON")
    parser.add_argument("--output", default=None, help="Output strip_results.json path")
    parser.add_argument("--hashes-output", default=None, help="Output strip_hashes.json path")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Executing STRIP detector on device: {device}")
    
    data_dir = os.path.abspath(args.data_dir or os.path.join(BASE_DIR, "data", "trojai_sample"))
    triggers_dir = os.path.abspath(args.triggers_dir or os.path.join(BASE_DIR, "triggers"))
    manifest_path = os.path.abspath(args.manifest or os.path.join(BASE_DIR, "calibration_manifest.json"))
    output_json_path = os.path.abspath(args.output or os.path.join(BASE_DIR, "strip_results.json"))
    hashes_json_path = os.path.abspath(args.hashes_output or os.path.join(BASE_DIR, "strip_hashes.json"))

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if args.model_path:
        model_path = os.path.abspath(args.model_path)
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"Selected model file not found: {model_path}")
        mid = args.model_id or os.path.splitext(os.path.basename(model_path))[0]
        entry = next((x for x in manifest if str(x.get("model_id")) == str(mid)), None)
        if entry is None:
            raise RuntimeError(
                f"No calibration_manifest entry exists for selected model '{mid}'. "
                "The current STRIP protocol is calibrated only for registered model IDs; "
                "it will not silently analyze a different model."
            )
        registered_model_dir = os.path.join(data_dir, mid)
        if not os.path.isdir(os.path.join(registered_model_dir, "example_data")):
            raise RuntimeError(f"Registered STRIP assets for '{mid}' are incomplete: example_data is missing.")
        print(f"[1/1] Evaluating selected model {mid}...")
        hashes, rows = evaluate_model_strip(
            mid, entry, data_dir, triggers_dir, device, model_path_override=model_path
        )
        all_table_rows = rows
        all_hash_pairs = {mid: hashes}
        print(f"  -> Completed {len(rows)} class evaluations. SHA-256 verified: {hashes['after'][:16]}...")
    else:
        all_table_rows = []
        all_hash_pairs = {}
        t_start = time.time()
        for idx, entry in enumerate(manifest, 1):
            mid = entry["model_id"]
            print(f"[{idx}/{len(manifest)}] Evaluating {mid}...")
            hashes, rows = evaluate_model_strip(mid, entry, data_dir, triggers_dir, device)
            all_hash_pairs[mid] = hashes
            all_table_rows.extend(rows)
            print(f"  -> Completed {len(rows)} class evaluations. SHA-256 verified identical: {hashes['after'][:16]}...")
        total_elapsed = time.time() - t_start
        print(f"\nAll {len(manifest)} calibrated models completed in {total_elapsed:.2f}s ({total_elapsed/60:.2f}m).\n")

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(all_table_rows, f, indent=2)
    print(f"Saved full results to {output_json_path}")

    with open(hashes_json_path, "w", encoding="utf-8") as f:
        json.dump(all_hash_pairs, f, indent=2)
    print(f"Saved live hash pairs to {hashes_json_path}")


if __name__ == "__main__":
    main()