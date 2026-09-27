import json
import os
import sys
import torch
import numpy as np
from sklearn.model_selection import StratifiedKFold

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, WORKSPACE_ROOT)
sys.path.insert(0, os.path.join(WORKSPACE_ROOT, "data-integrity"))

from src.voc_adapter import VOC2012Adapter
from src.dataset import build_dataset

manifest = json.load(open("datasets/sentinelvision_voc2012/metadata/attack_manifest.json"))
flips = [a for a in manifest["attacks"] if a.get("scenario") == "label_flip"]
flip_dir = "datasets/sentinelvision_voc2012/label_flip"
adapter = VOC2012Adapter(flip_dir)
all_files = sorted([f for f in os.listdir(os.path.join(flip_dir, "JPEGImages")) if f.lower().endswith(('.jpg', '.png'))])

single = {f: adapter.get_sample(os.path.splitext(f)[0]).objects[0].class_name for f in all_files}
tmp = os.path.join(flip_dir, "labels_temp.json")
with open(tmp, "w") as fp:
    json.dump(single, fp)

ds, _ = build_dataset(os.path.join(flip_dir, "JPEGImages"), tmp, {"backbone": "resnet50", "device": "cuda"}, os.path.join(flip_dir, "resnet50_cache.npz"))
raw_emb = ds.embeddings()
classes = sorted(set(single.values()))
c2i = {c: i for i, c in enumerate(classes)}
labels = np.array([c2i[single[f]] for f in ds.image_ids])

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
emb_t = torch.as_tensor(raw_emb, dtype=torch.float32, device=device)
y_t = torch.as_tensor(labels, dtype=torch.int64, device=device)

# Normalized embeddings for Cosine similarity
emb_norm = torch.nn.functional.normalize(emb_t, p=2, dim=1)

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
pred_probs_cos = torch.zeros((len(labels), len(classes)), device=device)

# 1. Cosine k-NN
for tr, te in skf.split(raw_emb, labels):
    sims = torch.mm(emb_norm[te], emb_norm[tr].t())
    topk_sims, topk_i = torch.topk(sims, k=5, largest=True, dim=1)
    topk_l = y_t[tr][topk_i]
    # Cosine softmax weights
    weights = torch.softmax(topk_sims * 10.0, dim=1)
    oh = torch.zeros((len(te), 5, len(classes)), device=device).scatter_(2, topk_l.unsqueeze(-1), 1.0)
    pred_probs_cos[te] = (oh * weights.unsqueeze(-1)).sum(dim=1)

p_cos = pred_probs_cos.cpu().numpy()

# 2. Nearest Centroid Classifier on Cosine space
pred_probs_cent = torch.zeros((len(labels), len(classes)), device=device)
for tr, te in skf.split(raw_emb, labels):
    centroids = torch.zeros((len(classes), emb_norm.size(1)), device=device)
    for c in range(len(classes)):
        mask = (y_t[tr] == c)
        if mask.any():
            centroids[c] = emb_norm[tr][mask].mean(dim=0)
            centroids[c] = torch.nn.functional.normalize(centroids[c], p=2, dim=0)
        else:
            centroids[c] = emb_norm[tr].mean(dim=0)
    sims_to_cent = torch.mm(emb_norm[te], centroids.t())
    pred_probs_cent[te] = torch.softmax(sims_to_cent * 15.0, dim=1)

p_cent = pred_probs_cent.cpu().numpy()

print(f"\n{'='*25} COSINE k-NN vs CENTROID ON 13 FLIPS {'='*25}")
cos_hits = 0
cent_hits = 0
for a in flips:
    sid = a["sample_id"].replace("voc2012_", "") + ".jpg"
    idx = ds.image_ids.index(sid)
    orig = a["original_state"]["label"]
    mut = a["modified_state"]["label"]
    
    cos_pred = classes[np.argmax(p_cos[idx])]
    cos_gap = np.max(p_cos[idx]) - p_cos[idx, labels[idx]]
    
    cent_pred = classes[np.argmax(p_cent[idx])]
    cent_gap = np.max(p_cent[idx]) - p_cent[idx, labels[idx]]
    
    if cos_pred == orig: cos_hits += 1
    if cent_pred == orig: cent_hits += 1
    
    print(f"{sid}: orig={orig:10s} -> given={mut:10s} | Cosine: pred={cos_pred:10s} (gap={cos_gap:.2f}) | Centroid: pred={cent_pred:10s} (gap={cent_gap:.2f})")

print(f"\nExact matches to original true label: Cosine k-NN: {cos_hits}/13, Centroid: {cent_hits}/13")
