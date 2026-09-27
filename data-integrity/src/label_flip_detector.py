"""
SentinelVision - Data Integrity Step 2c: GPU-Accelerated Label-Flip Detection.

Permitted auxiliary analysis (Stage 6 Constraint 2): an out-of-fold detection
model runs on top of the shared frozen embeddings.

GPU-First Architecture:
  1. Transfer embeddings & labels to CUDA tensor representations.
  2. Stratified k-fold cross-validation over the given labels: every sample
     receives an OUT-OF-SAMPLE predicted class probability from a model that
     never saw it. Pairwise distances and k-NN selection run via torch.cdist
     and torch.topk on CUDA.
  3. Class-conditional feature analysis (class centroids and Euclidean/cosine
     distances) computed on CUDA.
  4. Multi-evidence scoring (predictive disagreement, confidence gap, odds ratio,
     local neighborhood agreement, and centroid distance ratio) computed on CUDA.
  5. cleanlab.filter.find_label_issues(labels, pred_probs, filter_by=...) identifies
     statistically anomalous label noise.
  6. Multi-evidence gating with multi-object co-occurrence check eliminates clean
     control false positives while catching genuine label corruptions.

Offline only: zero external network access, fully reproducible.
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    TORCH_AVAILABLE = False

LABEL_FLIP_DEFAULT_N_SPLITS = 5
LABEL_FLIP_DEFAULT_NEIGHBORS = 5
# Default filter_by preserves backward compatibility with unit tests.
# The VOC pipeline passes stricter settings (filter_by="both", higher
# gap/prob/odds thresholds, and multi-object labels) via benchmark config.
LABEL_FLIP_DEFAULT_FILTER_BY = "predicted_neq_given"
LABEL_FLIP_DEFAULT_MIN_GAP = 0.10
LABEL_FLIP_DEFAULT_MIN_ALT_PROB = 0.20
LABEL_FLIP_DEFAULT_MIN_ODDS = 1.2
LABEL_FLIP_DISTANCE_BATCH_SIZE = 256

_VALID_CLASSIFIERS = ("knn", "logreg")


class LabelFlipError(ValueError):
    """Raised for invalid label-flip inputs (fail closed)."""


class CleanlabUnavailableError(RuntimeError):
    """Raised when cleanlab is required but not installed."""


def _require_cleanlab():
    try:
        import cleanlab  # noqa: F401
        from cleanlab.filter import find_label_issues  # noqa: F401

        return find_label_issues
    except ImportError as exc:  # pragma: no cover - depends on env
        raise CleanlabUnavailableError(
            "label_flip.enabled=true requires the 'cleanlab' package. Install it "
            "locally with: pip install cleanlab (or set label_flip.enabled=false "
            "to run with duplicate + OOD only)."
        ) from exc


def _resolve_device(requested_device: Optional[str] = None) -> Tuple[Any, str, str]:
    """
    Central GPU device policy: defaults to CUDA whenever available.
    Returns (torch.device, device_str, gpu_name).
    """
    if not TORCH_AVAILABLE:
        return None, "cpu", "None (torch unavailable)"

    if requested_device is None or requested_device == "auto":
        dev_str = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        dev_str = requested_device

    device = torch.device(dev_str)
    if dev_str.startswith("cuda") and not torch.cuda.is_available():
        raise LabelFlipError(f"CUDA device requested ('{dev_str}') but CUDA is not available.")

    gpu_name = torch.cuda.get_device_name(0) if dev_str.startswith("cuda") else "CPU"
    return device, dev_str, gpu_name


def _gpu_oof_pred_probs(
    emb_t: Any,
    labels_t: Any,
    classifier: str,
    n_splits: int,
    seed: int,
    n_neighbors: int,
    device: Any,
) -> Any:
    """
    Compute out-of-fold predicted class probabilities entirely on GPU using PyTorch.
    Ensures strict fold independence with no OOF leakage.
    """
    from sklearn.model_selection import StratifiedKFold

    n_samples, n_features = emb_t.shape
    num_classes = int(labels_t.max().item()) + 1

    labels_cpu = labels_t.cpu().numpy()
    min_per_class = min((labels_cpu == c).sum() for c in range(num_classes))
    n_splits = max(2, min(int(n_splits), int(min_per_class)))
    if n_splits < 2:
        raise LabelFlipError("Each class needs >= 2 samples for cross-validated confident learning.")

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    pred_probs = torch.zeros((n_samples, num_classes), dtype=torch.float32, device=device)

    for train_idx, test_idx in skf.split(labels_cpu, labels_cpu):
        train_idx_t = torch.as_tensor(train_idx, dtype=torch.int64, device=device)
        test_idx_t = torch.as_tensor(test_idx, dtype=torch.int64, device=device)

        X_train = emb_t[train_idx_t]
        y_train = labels_t[train_idx_t]
        X_test = emb_t[test_idx_t]

        if classifier == "knn":
            # GPU pairwise Euclidean distance
            dists = torch.cdist(X_test, X_train, p=2.0)
            if device.type == "cuda":
                assert dists.is_cuda, "Pairwise distances must execute on CUDA."

            k = min(n_neighbors, len(train_idx))
            topk_dists, topk_idx = torch.topk(dists, k=k, largest=False, dim=1)
            neighbor_labels = y_train[topk_idx]

            # Distance-weighted soft voting on GPU
            weights = 1.0 / (topk_dists + 1e-5)
            weights = weights / weights.sum(dim=1, keepdim=True)

            one_hot = torch.zeros((X_test.size(0), k, num_classes), dtype=torch.float32, device=device)
            one_hot.scatter_(2, neighbor_labels.unsqueeze(-1), 1.0)
            fold_probs = (one_hot * weights.unsqueeze(-1)).sum(dim=1)

        elif classifier == "logreg":
            # Closed-form regularized ridge / linear classifier on GPU
            Y_oh = torch.zeros((X_train.size(0), num_classes), dtype=torch.float32, device=device)
            Y_oh.scatter_(1, y_train.unsqueeze(-1), 1.0)
            lambda_reg = 1e-2
            XtX = torch.mm(X_train.t(), X_train) + lambda_reg * torch.eye(n_features, device=device)
            XtY = torch.mm(X_train.t(), Y_oh)
            weights = torch.linalg.solve(XtX, XtY)
            logits = torch.mm(X_test, weights)
            fold_probs = torch.softmax(logits, dim=-1)

        else:
            raise LabelFlipError(f"Unknown classifier '{classifier}'. Valid: {sorted(_VALID_CLASSIFIERS)}.")

        # Laplace smoothing & normalization
        fold_probs = (fold_probs + 1e-4) / (fold_probs + 1e-4).sum(dim=1, keepdim=True)
        pred_probs[test_idx_t] = fold_probs

    if device.type == "cuda":
        assert pred_probs.is_cuda, "OOF probabilities must reside on CUDA."

    return pred_probs


def find_label_flips(
    emb: np.ndarray,
    labels: List[str],
    classifier: str = "knn",
    n_splits: int = LABEL_FLIP_DEFAULT_N_SPLITS,
    seed: int = 42,
    n_neighbors: int = LABEL_FLIP_DEFAULT_NEIGHBORS,
    image_ids: Optional[List[str]] = None,
    standardization: Optional[Any] = None,
    filter_by: str = LABEL_FLIP_DEFAULT_FILTER_BY,
    multi_labels: Optional[Dict[str, List[str]]] = None,
    min_confidence_gap: float = LABEL_FLIP_DEFAULT_MIN_GAP,
    min_alt_prob: float = LABEL_FLIP_DEFAULT_MIN_ALT_PROB,
    min_odds_ratio: float = LABEL_FLIP_DEFAULT_MIN_ODDS,
    min_centroid_ratio: float = 0.0,
    device: Optional[str] = None,
    batch_size: int = LABEL_FLIP_DISTANCE_BATCH_SIZE,
) -> Dict[str, Any]:
    """
    GPU-accelerated confident learning label-flip detector with multi-evidence gating.

    Args:
        emb: (n, d) visual embeddings array.
        labels: list of supplied string class labels.
        classifier: 'knn' (default) or 'logreg'.
        n_splits: number of stratified folds for out-of-fold inference.
        seed: master random seed.
        n_neighbors: k nearest neighbors.
        image_ids: optional list of string image filenames.
        standardization: optional (mu, sd) tuple for feature standardization, or 'l2_norm'.
        filter_by: cleanlab filter rule ('both', 'predicted_neq_given', 'prune_by_noise_rate').
        multi_labels: optional mapping {image_id: [class1, class2, ...]} for multi-object datasets.
        min_confidence_gap: minimum probability margin between top predicted class and given class.
        min_alt_prob: minimum absolute probability required for the alternative predicted class.
        min_odds_ratio: minimum odds ratio P(alt) / P(given).
        min_centroid_ratio: minimum ratio dist(sample, given_centroid) / dist(sample, alt_centroid).
        device: 'cuda', 'cpu', or 'auto' (default).
    """
    if classifier not in _VALID_CLASSIFIERS:
        raise LabelFlipError(f"Unknown classifier '{classifier}'. Valid: {sorted(_VALID_CLASSIFIERS)}.")

    emb_arr = np.asarray(emb, dtype=np.float32)
    if emb_arr.ndim != 2:
        raise LabelFlipError(f"Embeddings must be 2-D, got {emb_arr.shape}.")

    label_arr = np.asarray(labels)
    if label_arr.shape[0] != emb_arr.shape[0]:
        raise LabelFlipError(f"labels length {label_arr.shape[0]} != embeddings rows {emb_arr.shape[0]}.")

    classes = sorted(set(str(c) for c in label_arr))
    if len(classes) < 2:
        raise LabelFlipError(f"Confident learning needs >= 2 distinct labels; got {classes}.")

    class_to_int = {c: i for i, c in enumerate(classes)}
    label_ints = np.asarray([class_to_int[str(c)] for c in label_arr], dtype=np.int64)

    find_label_issues = _require_cleanlab()
    torch_dev, dev_str, gpu_name = _resolve_device(device)

    # Convert to GPU tensors
    emb_t = torch.as_tensor(emb_arr, dtype=torch.float32, device=torch_dev)
    labels_t = torch.as_tensor(label_ints, dtype=torch.int64, device=torch_dev)
    if torch_dev.type == "cuda":
        assert emb_t.is_cuda, "Feature embeddings must reside on CUDA."
        assert labels_t.is_cuda, "Labels tensor must reside on CUDA."

    # Standardization & Geometry on GPU
    # Deep features (d >= 64) benefit from hyperspherical normalization (cosine space)
    if standardization == "l2_norm" or (standardization is None and emb_t.size(1) >= 64):
        emb_std = torch.nn.functional.normalize(emb_t, p=2.0, dim=1)
        use_cosine = True
    elif standardization is not None and isinstance(standardization, (tuple, list)):
        mu, sd = standardization
        mu_t = torch.as_tensor(mu, dtype=torch.float32, device=torch_dev)
        sd_t = torch.clamp(torch.as_tensor(sd, dtype=torch.float32, device=torch_dev), min=1e-9)
        emb_std = (emb_t - mu_t) / sd_t
        use_cosine = False
    else:
        mu_t = emb_t.mean(dim=0, keepdim=True)
        sd_t = torch.clamp(emb_t.std(dim=0, keepdim=True), min=1e-9)
        emb_std = (emb_t - mu_t) / sd_t
        use_cosine = False

    # Compute GPU out-of-fold predicted probabilities
    pred_probs = _gpu_oof_pred_probs(
        emb_std, labels_t, classifier, n_splits, seed, n_neighbors, torch_dev
    )

    # Class centroids & feature-space distances on GPU
    num_classes = len(classes)
    centroids = torch.zeros((num_classes, emb_std.size(1)), dtype=torch.float32, device=torch_dev)
    for c in range(num_classes):
        mask = (labels_t == c)
        if mask.any():
            centroids[c] = emb_std[mask].mean(dim=0)
        else:
            centroids[c] = emb_std.mean(dim=0)

    if use_cosine:
        centroids = torch.nn.functional.normalize(centroids, p=2.0, dim=1)
        centroid_dists = 1.0 - torch.mm(emb_std, centroids.t())
    else:
        centroid_dists = torch.cdist(emb_std, centroids, p=2.0)

    if torch_dev.type == "cuda":
        assert centroid_dists.is_cuda, "Centroid distances must execute on CUDA."

    n_samples = emb_arr.shape[0]
    sample_indices = torch.arange(n_samples, device=torch_dev)
    dist_given = centroid_dists[sample_indices, labels_t]

    alt_dists = centroid_dists.clone()
    alt_dists[sample_indices, labels_t] = float("inf")
    min_alt_dist, _ = alt_dists.min(dim=1)
    centroid_dist_ratio = (dist_given + 1e-4) / (min_alt_dist + 1e-4)

    # Multi-evidence tensor metrics on GPU
    top1_prob, top1_class = pred_probs.max(dim=1)
    given_prob = pred_probs[sample_indices, labels_t]
    conf_gap = top1_prob - given_prob
    odds_ratio = top1_prob / (given_prob + 1e-4)
    discordant = (top1_class != labels_t)

    # Global neighborhood consensus on GPU (batched to prevent full N×N distance matrix allocation)
    k_eval = min(n_neighbors, n_samples - 1)
    if k_eval <= 0:
        topk_i = torch.empty((n_samples, 0), dtype=torch.int64, device=torch_dev)
    else:
        topk_batches = []
        for start in range(0, n_samples, batch_size):
            end = min(start + batch_size, n_samples)
            query_emb = emb_std[start:end]
            batch_dists = torch.cdist(query_emb, emb_std, p=2.0)

            # Exclude each query sample from being its own neighbor (equivalent to fill_diagonal_(inf))
            b_len = end - start
            r_idx = torch.arange(b_len, device=torch_dev)
            batch_dists[r_idx, start + r_idx] = float("inf")

            _, b_topk = torch.topk(batch_dists, k=k_eval, largest=False, dim=1)
            topk_batches.append(b_topk)
            del batch_dists

        topk_i = torch.cat(topk_batches, dim=0)

    neighbor_labels = labels_t[topk_i]
    if k_eval > 0:
        given_neighbor_agreement = (neighbor_labels == labels_t.unsqueeze(1)).float().mean(dim=1)
        alt_neighbor_agreement = (neighbor_labels == top1_class.unsqueeze(1)).float().mean(dim=1)
    else:
        given_neighbor_agreement = torch.zeros(n_samples, dtype=torch.float32, device=torch_dev)
        alt_neighbor_agreement = torch.zeros(n_samples, dtype=torch.float32, device=torch_dev)

    # Multi-evidence suspiciousness score on GPU
    suspiciousness = (
        0.35 * conf_gap
        + 0.25 * torch.clamp((centroid_dist_ratio - 1.0) / 2.0, 0.0, 1.0)
        + 0.20 * alt_neighbor_agreement
        + 0.20 * (1.0 - given_neighbor_agreement)
    )
    if torch_dev.type == "cuda":
        assert suspiciousness.is_cuda, "Suspiciousness scoring must execute on CUDA."

    # Cleanlab confident learning noise filtering (in-process with n_jobs=1)
    pred_probs_cpu = pred_probs.detach().cpu().numpy().astype(np.float64)
    pred_probs_cpu = np.clip(pred_probs_cpu, 1e-7, 1.0)
    pred_probs_cpu = pred_probs_cpu / pred_probs_cpu.sum(axis=1, keepdims=True)

    cleanlab_candidates = find_label_issues(
        labels=label_ints,
        pred_probs=pred_probs_cpu,
        filter_by=filter_by,
        n_jobs=1,
    )

    # Transfer multi-evidence vectors to CPU for candidate filtration
    conf_gap_cpu = conf_gap.detach().cpu().numpy()
    top1_prob_cpu = top1_prob.detach().cpu().numpy()
    odds_ratio_cpu = odds_ratio.detach().cpu().numpy()
    discordant_cpu = discordant.detach().cpu().numpy()
    top1_class_cpu = top1_class.detach().cpu().numpy()
    suspiciousness_cpu = suspiciousness.detach().cpu().numpy()
    dist_ratio_cpu = centroid_dist_ratio.detach().cpu().numpy()
    given_agr_cpu = given_neighbor_agreement.detach().cpu().numpy()
    alt_agr_cpu = alt_neighbor_agreement.detach().cpu().numpy()

    flagged_indices: List[int] = []
    per_image: List[Dict[str, Any]] = []

    for i in range(n_samples):
        # 1. Base discordance: top predicted class differs from given label
        if not discordant_cpu[i]:
            continue

        # 2. Cleanlab statistical noise filter
        if not cleanlab_candidates[i]:
            continue

        img_id = image_ids[i] if image_ids is not None else str(i)
        pred_class_name = classes[top1_class_cpu[i]]
        given_class_name = str(label_arr[i])

        # 3. Multi-object gate: if predicted class is another real object in this image, pass
        if multi_labels is not None and img_id in multi_labels:
            if pred_class_name in multi_labels[img_id]:
                continue

        # 4. Multi-evidence margin and confidence gating
        if conf_gap_cpu[i] < min_confidence_gap:
            continue
        if top1_prob_cpu[i] < min_alt_prob:
            continue
        if odds_ratio_cpu[i] < min_odds_ratio:
            continue
        if min_centroid_ratio > 0.0 and dist_ratio_cpu[i] < min_centroid_ratio:
            continue

        flagged_indices.append(i)
        per_image.append(
            {
                "index": i,
                "image_id": img_id,
                "given_label": given_class_name,
                "predicted_label": pred_class_name,
                "confidence_label_wrong": round(float(1.0 - given_prob[i].item()), 6),
                "confidence_gap": round(float(conf_gap_cpu[i]), 4),
                "alt_class_probability": round(float(top1_prob_cpu[i]), 4),
                "odds_ratio": round(float(odds_ratio_cpu[i]), 2),
                "suspiciousness_score": round(float(suspiciousness_cpu[i]), 4),
                "centroid_dist_ratio": round(float(dist_ratio_cpu[i]), 2),
                "neighbor_agreement": {
                    "given_label": round(float(given_agr_cpu[i]), 2),
                    "predicted_label": round(float(alt_agr_cpu[i]), 2),
                },
            }
        )

    per_image.sort(key=lambda r: (-r["suspiciousness_score"], r["image_id"]))

    return {
        "classifier": classifier,
        "n_splits": int(n_splits),
        "seed": int(seed),
        "filter_by": str(filter_by),
        "n_images": int(emb_arr.shape[0]),
        "classes": classes,
        "flagged_indices": [int(r["index"]) for r in per_image],
        "flagged_image_ids": [r["image_id"] for r in per_image],
        "n_flagged": len(per_image),
        "per_image": per_image,
        "device": dev_str,
        "gpu_model": gpu_name,
        "gpu_verified": (torch_dev.type == "cuda"),
        "method": (
            f"PyTorch CUDA OOF inference ({classifier}) + Cleanlab ({filter_by}) "
            "with multi-evidence margin & multi-object gating"
        ),
    }
