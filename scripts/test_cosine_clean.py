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
from src.label_flip_detector import _require_cleanlab

clean_dir = "datasets/sentinelvision_voc2012/clean"
adapter_clean = VOC2012Adapter(clean_dir)
clean_files = sorted([f for f in os.listdir(os.path.join(clean_dir, "JPEGImages")) if f.lower().endswith(('.jpg', '.png'))])

single = {}
multi = {}
for f in clean_files:
    sid = os.path.splitext(f)[0]
    s = adapter_clean.get_sample(sid)
    single[f] = s.objects[0].class_name if s and s.objects else "background"
    multi[f] = [o.class_name for o in s.objects] if s and s.objects else ["background"]

tmp = os.path.join(clean_dir, "labels_temp.json")
with open(tmp, "w") as fp:
    json.dump(single, fp)

ds, _ = build_dataset(os.path.join(clean_dir, "JPEGImages"), tmp, {"backbone": "resnet50", "device": "cuda"}, os.path.join(clean_dir, "resnet50_cache.npz"))
raw_emb = ds.embeddings()
classes = sorted(set(single.values()))
c2i = {c: i for i, c in enumerate(classes)}
labels = np.array([c2i[single[f]] for f in ds.image_ids])

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
emb_t = torch.as_tensor(raw_emb, dtype=torch.float32, device=device)
y_t = torch.as_tensor(labels, dtype=torch.int64, device=device)
emb_norm = torch.nn.functional.normalize(emb_t, p=2, dim=1)

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
pred_probs_cos = torch.zeros((len(labels), len(classes)), device=device)

for tr, te in skf.split(raw_emb, labels):
    sims = torch.mm(emb_norm[te], emb_norm[tr].t())
    topk_sims, topk_i = torch.topk(sims, k=5, largest=True, dim=1)
    topk_l = y_t[tr][topk_i]
    weights = torch.softmax(topk_sims * 10.0, dim=1)
    oh = torch.zeros((len(te), 5, len(classes)), device=device).scatter_(2, topk_l.unsqueeze(-1), 1.0)
    pred_probs_cos[te] = (oh * weights.unsqueeze(-1)).sum(dim=1)

p_cos = pred_probs_cos.cpu().numpy()
find_issues = _require_cleanlab()

def main():
    cleanlab_issues = find_issues(labels=labels, pred_probs=p_cos, filter_by="both", n_jobs=1)

    top1_p = np.max(p_cos, axis=1)
    top1_c = np.argmax(p_cos, axis=1)
    given_p = p_cos[np.arange(len(labels)), labels]
    gaps = top1_p - given_p

    print(f"Total clean samples: {len(labels)}")
    print(f"Cleanlab 'both' flagged: {np.sum(cleanlab_issues)} / {len(labels)}")

    for min_gap in [0.25, 0.30, 0.35, 0.40]:
        for min_p in [0.40, 0.50]:
            flagged = []
            for i in range(len(labels)):
                if not cleanlab_issues[i]:
                    continue
                if top1_c[i] == labels[i]:
                    continue
                if gaps[i] < min_gap or top1_p[i] < min_p:
                    continue
                pred_c = classes[top1_c[i]]
                img_id = ds.image_ids[i]
                if pred_c in multi[img_id]:
                    continue
                flagged.append(img_id)
            print(f"min_gap={min_gap:.2f}, min_p={min_p:.2f} (with multi-object gate) -> Clean FP: {len(flagged)} / {len(labels)} ({len(flagged)/len(labels)*100:.2f}%)")

if __name__ == "__main__":
    main()
