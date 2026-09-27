import json
import os
import sys
import torch
import numpy as np

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, WORKSPACE_ROOT)
sys.path.insert(0, os.path.join(WORKSPACE_ROOT, "data-integrity"))

from src.voc_adapter import VOC2012Adapter
from src.dataset import build_dataset
from src.label_flip_detector import _require_cleanlab

def evaluate_ground_truth(flagged_ids, manifest_path):
    with open(manifest_path) as f:
        data = json.load(f)
    attacks = {a["sample_id"] for a in data.get("attacks", []) if a.get("scenario") == "label_flip"}
    if not attacks:
        attacks = {a["sample_id"] for a in data.get("attacks", [])}
        
    flagged_normalized = set()
    for sid in flagged_ids:
        raw = os.path.splitext(sid)[0]
        flagged_normalized.add(f"voc2012_{raw}")
        
    tp = len(flagged_normalized.intersection(attacks))
    fp = len(flagged_normalized.difference(attacks))
    fn = len(attacks.difference(flagged_normalized))
    
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return {"injected": len(attacks), "tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec, "f1": f1}

def get_gpu_oof_predictions(ds, labels_dict, device, weighted=False):
    raw_emb = ds.embeddings()
    labels_list = [labels_dict[f] for f in ds.image_ids]
    classes = sorted(set(labels_list))
    class_to_int = {c: i for i, c in enumerate(classes)}
    label_ints = np.array([class_to_int[c] for c in labels_list], dtype=np.int64)
    
    emb_t = torch.as_tensor(raw_emb, dtype=torch.float32, device=device)
    labels_t = torch.as_tensor(label_ints, dtype=torch.int64, device=device)
    assert emb_t.is_cuda
    
    mu = emb_t.mean(dim=0, keepdim=True)
    sd = torch.clamp(emb_t.std(dim=0, keepdim=True), min=1e-9)
    emb_std = (emb_t - mu) / sd
    
    from sklearn.model_selection import StratifiedKFold
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    pred_probs = torch.zeros((len(label_ints), len(classes)), dtype=torch.float32, device=device)
    
    n_neighbors = 5
    for train_idx, test_idx in skf.split(raw_emb, label_ints):
        train_idx_t = torch.as_tensor(train_idx, device=device)
        test_idx_t = torch.as_tensor(test_idx, device=device)
        X_tr = emb_std[train_idx_t]
        y_tr = labels_t[train_idx_t]
        X_te = emb_std[test_idx_t]
        
        dists = torch.cdist(X_te, X_tr, p=2.0)
        assert dists.is_cuda
        topk_dists, topk_idx = torch.topk(dists, k=min(n_neighbors, len(train_idx)), largest=False, dim=1)
        topk_labels = y_tr[topk_idx]
        
        one_hot = torch.zeros((X_te.size(0), topk_labels.size(1), len(classes)), device=device)
        one_hot.scatter_(2, topk_labels.unsqueeze(-1), 1.0)
        
        if weighted:
            weights = 1.0 / (topk_dists + 1e-5)
            weights = weights / weights.sum(dim=1, keepdim=True)
            fold_probs = (one_hot * weights.unsqueeze(-1)).sum(dim=1)
        else:
            fold_probs = one_hot.mean(dim=1)
            
        fold_probs = (fold_probs + 1e-4) / (fold_probs + 1e-4).sum(dim=1, keepdim=True)
        pred_probs[test_idx_t] = fold_probs
        
    find_issues = _require_cleanlab()
    pred_probs_cpu = pred_probs.detach().cpu().numpy()
    cleanlab_both = find_issues(labels=label_ints, pred_probs=pred_probs_cpu, filter_by="both")
    
    return {
        "pred_probs": pred_probs,
        "classes": classes,
        "label_ints": label_ints,
        "labels_t": labels_t,
        "cleanlab_both": cleanlab_both,
    }

def filter_candidates(ds, oof_data, multi_dict, min_gap, min_p_alt, min_odds):
    pred_probs = oof_data["pred_probs"]
    classes = oof_data["classes"]
    labels_t = oof_data["labels_t"]
    cleanlab_both = oof_data["cleanlab_both"]
    
    top1_prob, top1_class = pred_probs.max(dim=1)
    given_prob = pred_probs[torch.arange(len(labels_t)), labels_t]
    conf_gap = top1_prob - given_prob
    odds_ratio = top1_prob / (given_prob + 1e-4)
    
    flagged = []
    for i in range(len(labels_t)):
        if not cleanlab_both[i]:
            continue
        if top1_class[i] == labels_t[i]:
            continue
        img_id = ds.image_ids[i]
        pred_c = classes[top1_class[i].item()]
        # Multi-object gate
        if pred_c in multi_dict.get(img_id, []):
            continue
        if conf_gap[i].item() < min_gap:
            continue
        if top1_prob[i].item() < min_p_alt:
            continue
        if odds_ratio[i].item() < min_odds:
            continue
        flagged.append(img_id)
    return flagged

def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}, GPU: {torch.cuda.get_device_name(0)}")
    
    # 1. CLEAN CONTROL
    clean_dir = "datasets/sentinelvision_voc2012/clean"
    adapter_clean = VOC2012Adapter(clean_dir)
    clean_files = sorted([f for f in os.listdir(os.path.join(clean_dir, "JPEGImages")) if f.lower().endswith(('.jpg', '.png'))])
    clean_single = {}
    clean_multi = {}
    for f in clean_files:
        sid = os.path.splitext(f)[0]
        s = adapter_clean.get_sample(sid)
        clean_single[f] = s.objects[0].class_name if s and s.objects else "background"
        clean_multi[f] = [o.class_name for o in s.objects] if s and s.objects else ["background"]
    tmp_clean = os.path.join(clean_dir, "labels_temp.json")
    with open(tmp_clean, "w") as fp:
        json.dump(clean_single, fp)
    ds_clean, _ = build_dataset(os.path.join(clean_dir, "JPEGImages"), tmp_clean, {"backbone": "resnet50", "device": "cuda"}, os.path.join(clean_dir, "resnet50_cache.npz"))
    
    # 2. LABEL FLIP BENCHMARK
    flip_dir = "datasets/sentinelvision_voc2012/label_flip"
    adapter_flip = VOC2012Adapter(flip_dir)
    flip_files = sorted([f for f in os.listdir(os.path.join(flip_dir, "JPEGImages")) if f.lower().endswith(('.jpg', '.png'))])
    flip_single = {}
    flip_multi = {}
    for f in flip_files:
        sid = os.path.splitext(f)[0]
        s = adapter_flip.get_sample(sid)
        flip_single[f] = s.objects[0].class_name if s and s.objects else "background"
        flip_multi[f] = [o.class_name for o in s.objects] if s and s.objects else ["background"]
    tmp_flip = os.path.join(flip_dir, "labels_temp.json")
    with open(tmp_flip, "w") as fp:
        json.dump(flip_single, fp)
    ds_flip, _ = build_dataset(os.path.join(flip_dir, "JPEGImages"), tmp_flip, {"backbone": "resnet50", "device": "cuda"}, os.path.join(flip_dir, "resnet50_cache.npz"))
    manifest_path = "datasets/sentinelvision_voc2012/metadata/attack_manifest.json"
    
    for weighted in [False, True]:
        w_str = "Weighted" if weighted else "Uniform"
        print(f"\nComputing GPU OOF predictions for {w_str} kNN...")
        oof_clean = get_gpu_oof_predictions(ds_clean, clean_single, device, weighted=weighted)
        oof_flip = get_gpu_oof_predictions(ds_flip, flip_single, device, weighted=weighted)
        
        print(f"--- Results for {w_str} kNN ---")
        for min_gap in [0.20, 0.25, 0.30, 0.35]:
            for min_p_alt in [0.35, 0.40, 0.50]:
                for min_odds in [1.5, 2.0]:
                    clean_flagged = filter_candidates(ds_clean, oof_clean, clean_multi, min_gap, min_p_alt, min_odds)
                    clean_fpr = len(clean_flagged) / 500.0 * 100.0
                    
                    flip_flagged = filter_candidates(ds_flip, oof_flip, flip_multi, min_gap, min_p_alt, min_odds)
                    metrics = evaluate_ground_truth(flip_flagged, manifest_path)
                    
                    print(f"gap={min_gap:.2f}, p_alt={min_p_alt:.2f}, odds={min_odds:.1f} | Clean FP: {len(clean_flagged):2d}/500 ({clean_fpr:4.1f}%) | LabelFlip TP: {metrics['tp']:2d}/{metrics['injected']}, FP: {metrics['fp']:2d}, P: {metrics['precision']:.3f}, R: {metrics['recall']:.3f}, F1: {metrics['f1']:.3f}")

if __name__ == "__main__":
    main()
