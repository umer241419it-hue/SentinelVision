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

single = {}
multi = {}
for f in all_files:
    sid = os.path.splitext(f)[0]
    s = adapter.get_sample(sid)
    single[f] = s.objects[0].class_name if s and s.objects else "background"
    multi[f] = [o.class_name for o in s.objects] if s and s.objects else ["background"]

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
mu = emb_t.mean(dim=0, keepdim=True)
sd = torch.clamp(emb_t.std(dim=0, keepdim=True), min=1e-9)
emb_std = (emb_t - mu) / sd

# Compute class centroids
centroids = torch.zeros((len(classes), emb_std.size(1)), device=device)
for c in range(len(classes)):
    mask = (y_t == c)
    centroids[c] = emb_std[mask].mean(dim=0) if mask.any() else emb_std.mean(dim=0)
centroid_dists = torch.cdist(emb_std, centroids, p=2.0)

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
pred_probs = torch.zeros((len(labels), len(classes)), device=device)

for tr, te in skf.split(raw_emb, labels):
    dists = torch.cdist(emb_std[te], emb_std[tr], p=2.0)
    topk_d, topk_i = torch.topk(dists, k=5, largest=False, dim=1)
    topk_l = y_t[tr][topk_i]
    oh = torch.zeros((len(te), 5, len(classes)), device=device).scatter_(2, topk_l.unsqueeze(-1), 1.0)
    pred_probs[te] = (oh.mean(dim=1) + 1e-4) / (oh.mean(dim=1) + 1e-4).sum(dim=1, keepdim=True)

p_cpu = pred_probs.cpu().numpy()
cd_cpu = centroid_dists.cpu().numpy()

print(f"\n{'='*30} INSPECTING 13 INJECTED FLIPS {'='*30}")
for a in flips:
    sid = a["sample_id"].replace("voc2012_", "") + ".jpg"
    idx = ds.image_ids.index(sid)
    orig = a["original_state"]["label"]
    mut = a["modified_state"]["label"]
    pred_idx = np.argmax(p_cpu[idx])
    pred_class = classes[pred_idx]
    pred_p = p_cpu[idx, pred_idx]
    given_idx = labels[idx]
    given_p = p_cpu[idx, given_idx]
    gap = pred_p - given_p
    
    # Centroid distance
    dist_given = cd_cpu[idx, given_idx]
    dist_pred = cd_cpu[idx, pred_idx]
    dist_ratio = dist_given / (dist_pred + 1e-6)
    
    current_objs = multi[sid]
    is_multi = len(current_objs) > 1
    multi_str = f"objs={current_objs}" if is_multi else "single_obj"
    
    match_orig = (pred_class == orig)
    print(f"{sid} ({multi_str}): orig={orig} -> given={mut}")
    print(f"   pred={pred_class} (p={pred_p:.2f}) [matches_orig={match_orig}], given_p={given_p:.2f}, gap={gap:.2f}, dist_ratio={dist_ratio:.2f}")
