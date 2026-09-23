#!/usr/bin/env python3
"""
SentinelVision - Stage 4 Step 4b: Activation Clustering Layer (ARCHIVED EXPERIMENT)
Note: Implemented, validated against withheld ground truth by the human operator,
found not to add reliable signal beyond Neural Cleanse + MAD, archived rather than deleted.
Following Section 10 file structure (archived under model-integrity/experiments/).

Protocol Constraints:
- Zero ground truth data leakage: never open ground_truth.csv or METADATA.csv.
- Model integrity: SHA-256 verified before and after forward passes.
- Forward hook on real final classification layer (model.fc or model.classifier).
- Pooled PCA fit once per model across all genuine example images.
- Synthetic-triggered donor pool stratified evenly across all other classes.
- Clustering via KMeans(k=2, n_init>=10) in pooled PCA space.
- Alignment score computed as max(acc, 1-acc) across both cluster assignments.
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
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

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


def get_classification_layer(model: nn.Module) -> Tuple[nn.Module, str]:
    """
    Identifies the final classification layer attribute name and module.
    ResNet / Inception3: model.fc (nn.Linear)
    DenseNet: model.classifier (nn.Linear)
    """
    if hasattr(model, 'fc') and isinstance(model.fc, nn.Linear):
        return model.fc, f"model.fc ({model.fc})"
    if hasattr(model, 'classifier'):
        if isinstance(model.classifier, nn.Linear):
            return model.classifier, f"model.classifier ({model.classifier})"
        elif isinstance(model.classifier, nn.Sequential) and isinstance(model.classifier[-1], nn.Linear):
            return model.classifier[-1], f"model.classifier[-1] ({model.classifier[-1]})"
    for name, module in reversed(list(model.named_modules())):
        if isinstance(module, nn.Linear):
            return module, f"last Linear layer '{name}' ({module})"
    raise ValueError("Could not determine final classification layer")


def load_image_tensor(path: str, channel_order: str = "BGR") -> torch.Tensor:
    """Loads image, normalizes to [0,1], applies channel ordering, returns 3xHxW tensor."""
    img = Image.open(path).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    if channel_order == "BGR":
        arr = arr[:, :, ::-1].copy()
    return torch.from_numpy(arr).permute(2, 0, 1)


def stratify_donors(images_by_class: Dict[int, List[torch.Tensor]],
                    target_class: int,
                    target_count: int) -> Tuple[List[torch.Tensor], int, int]:
    """
    Selects target_count donor images from all other classes, stratified evenly.
    Returns: (selected_donor_tensors, pre_balancing_count, post_balancing_count)
    """
    num_classes = len(images_by_class)
    other_classes = [c for c in range(num_classes) if c != target_class]
    m_others = len(other_classes)
    
    total_available = sum(len(images_by_class[c]) for c in other_classes)
    
    base_per_class = target_count // m_others
    remainder = target_count % m_others
    
    selected_donors = []
    for idx, c in enumerate(other_classes):
        quota = base_per_class + (1 if idx < remainder else 0)
        c_imgs = images_by_class[c]
        selected_donors.extend(c_imgs[:quota])
        
    return selected_donors, total_available, len(selected_donors)


def evaluate_model_activation_clustering(model_id: str,
                                         manifest_entry: Dict[str, Any],
                                         mad_entry: Dict[str, Any],
                                         data_base_dir: str,
                                         triggers_base_dir: str,
                                         device: torch.device) -> Tuple[Dict[str, str], List[Dict[str, Any]], int]:
    """
    Executes Activation Clustering for all classes of a single model.
    Returns:
        hash_pair: {'before': sha_before, 'after': sha_after}
        results_rows: list of dicts for each class
        pca_components: number of PCA components used
    """
    model_dir = os.path.join(data_base_dir, model_id)
    model_path = os.path.join(model_dir, "model.pt")
    ex_data_dir = os.path.join(model_dir, "example_data")
    csv_path = os.path.join(ex_data_dir, "data.csv")
    channel_order = manifest_entry.get("chosen_channel_order", "BGR")
    
    # Hash before
    sha_before = compute_sha256(model_path)
    
    # Load model
    model = torch.load(model_path, map_location=device, weights_only=False)
    patch_model(model)
    model = model.to(device)
    model.eval()
    
    for param in model.parameters():
        param.requires_grad = False
        
    target_layer, layer_desc = get_classification_layer(model)
    
    # Setup pre-hook
    captured_activations = []
    def pre_hook(module, inputs):
        feat = inputs[0].detach()
        if feat.dim() > 2:
            feat = feat.flatten(1)
        captured_activations.append(feat.cpu())
        
    hook_handle = target_layer.register_forward_pre_hook(pre_hook)
    
    # Load genuine images
    df = pd.read_csv(csv_path)
    # Determine class count dynamically from target_layer
    num_classes = target_layer.out_features
    
    images_by_class = {}
    for c in range(num_classes):
        c_df = df[df["true_label"] == c]
        imgs = []
        for _, row in c_df.iterrows():
            img_p = os.path.join(ex_data_dir, row["file"])
            imgs.append(load_image_tensor(img_p, channel_order=channel_order))
        images_by_class[c] = imgs
        
    # Forward pass over all genuine images
    genuine_acts_by_class = {}
    for c in range(num_classes):
        batch = torch.stack(images_by_class[c]).to(device)
        captured_activations.clear()
        with torch.no_grad():
            _ = model(batch)
        # captured_activations has 1 tensor per forward pass
        genuine_acts_by_class[c] = captured_activations[0].numpy()
        
    all_genuine_acts = np.vstack([genuine_acts_by_class[c] for c in range(num_classes)])
    n_samples = all_genuine_acts.shape[0]
    
    # Step 2: Fit Pooled PCA
    # min(10, n_samples-1), floor 4
    pca_comp = max(4, min(10, n_samples - 1))
    pca = PCA(n_components=pca_comp)
    pca.fit(all_genuine_acts)
    
    # Determine per-class MAD flags
    per_class_anom = mad_entry.get("per_class_anomaly_index", [0.0]*num_classes)
    
    model_rows = []
    for c in range(num_classes):
        n_genuine = len(images_by_class[c])
        acts_gen = genuine_acts_by_class[c]
        
        # Load mask and pattern
        mask_path = os.path.join(triggers_base_dir, f"{model_id}_class{c}_mask.pt")
        pattern_path = os.path.join(triggers_base_dir, f"{model_id}_class{c}_pattern.pt")
        mask = torch.load(mask_path, map_location=device)
        pattern = torch.load(pattern_path, map_location=device)
        
        # Stratify donor pool
        donor_imgs, pre_bal_count, post_bal_count = stratify_donors(images_by_class, c, n_genuine)
        donor_tensor = torch.stack(donor_imgs).to(device)
        
        # Synthetic composite: x' = (1-mask)*x + mask*pattern
        synthetic_tensor = (1.0 - mask) * donor_tensor + mask * pattern
        
        captured_activations.clear()
        with torch.no_grad():
            _ = model(synthetic_tensor)
        acts_syn = captured_activations[0].numpy()
        
        # Step 4: Transform to Pooled PCA space
        Z_gen = pca.transform(acts_gen)
        Z_syn = pca.transform(acts_syn)
        
        X_class = np.vstack([Z_gen, Z_syn])
        y_true = np.array([0] * n_genuine + [1] * post_bal_count)
        
        # KMeans(k=2, n_init>=10)
        kmeans = KMeans(n_clusters=2, n_init=10, random_state=42)
        cluster_preds = kmeans.fit_predict(X_class)
        
        sil = float(silhouette_score(X_class, cluster_preds))
        
        # Alignment score: max(acc, 1-acc)
        raw_acc = float(np.mean(cluster_preds == y_true))
        align = float(max(raw_acc, 1.0 - raw_acc))
        
        is_mad_flagged = bool(per_class_anom[c] > 2.0) if c < len(per_class_anom) else False
        
        row = {
            "model_id": model_id,
            "class": c,
            "mad_flagged": is_mad_flagged,
            "n_genuine": n_genuine,
            "n_synthetic_pre_balancing": pre_bal_count,
            "n_synthetic_after_balancing": post_bal_count,
            "silhouette_score": round(sil, 4),
            "alignment_score": round(align, 4),
            "pca_components_used": pca_comp
        }
        model_rows.append(row)
        
    hook_handle.remove()
    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()
        
    # Hash after
    sha_after = compute_sha256(model_path)
    if sha_before != sha_after:
        raise RuntimeError(f"FATAL: SHA-256 hash mismatch for {model_id}!\nBefore: {sha_before}\nAfter:  {sha_after}")
        
    return {"before": sha_before, "after": sha_after}, model_rows, pca_comp


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Executing Activation Clustering on device: {device}")
    
    data_dir = os.path.join(BASE_DIR, "data", "trojai_sample")
    triggers_dir = os.path.join(BASE_DIR, "triggers")
    manifest_path = os.path.join(BASE_DIR, "calibration_manifest.json")
    mad_results_path = os.path.join(BASE_DIR, "mad_results.json")
    output_json_path = os.path.join(CURRENT_DIR, "activation_clustering_results.json")
    hashes_json_path = os.path.join(CURRENT_DIR, "activation_clustering_hashes.json")
    
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
    with open(mad_results_path, "r") as f:
        mad_data = json.load(f)
    mad_dict = {m["model_id"]: m for m in mad_data}
    
    all_table_rows = []
    all_hash_pairs = {}
    pca_counts = {}
    
    t_start = time.time()
    for idx, entry in enumerate(manifest, 1):
        mid = entry["model_id"]
        print(f"[{idx}/{len(manifest)}] Evaluating {mid}...")
        mad_entry = mad_dict.get(mid, {})
        hashes, rows, pca_c = evaluate_model_activation_clustering(
            mid, entry, mad_entry, data_dir, triggers_dir, device
        )
        all_hash_pairs[mid] = hashes
        all_table_rows.extend(rows)
        pca_counts[mid] = pca_c
        print(f"  -> Completed 5 classes. SHA-256 verified identical: {hashes['after'][:16]}...")
        
    total_elapsed = time.time() - t_start
    print(f"\nAll 15 models completed in {total_elapsed:.2f}s ({total_elapsed/60:.2f}m).\n")
    
    with open(output_json_path, "w") as f:
        json.dump(all_table_rows, f, indent=2)
    print(f"Saved full results to {output_json_path}")

    with open(hashes_json_path, "w") as f:
        json.dump(all_hash_pairs, f, indent=2)
    print(f"Saved live hash pairs to {hashes_json_path}")


if __name__ == "__main__":
    main()
