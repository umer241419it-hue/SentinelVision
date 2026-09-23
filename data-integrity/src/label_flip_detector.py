"""
SentinelVision - Data Integrity Step 2c: label-flip detection (confident learning).

Permitted auxiliary training (Stage 6 Constraint 2): a SMALL classifier is
trained ON TOP of the shared frozen embeddings - this is a new detection
tool, not a retraining of anyone's contributed model.

Procedure:
  1. k-fold cross-validation over the given labels: every sample receives an
     OUT-OF-SAMPLE predicted class probability from a model that never saw it
     (k-NN by default; logistic regression optional).
  2. cleanlab.filter.find_label_issues(labels, pred_probs) flags indices whose
     given label is probably wrong.

The detector reports the flagged indices plus per-class confidence summaries.
cleanlab is a hard requirement when this check is enabled: an import failure
is an explicit, actionable error (never a silent skip).
"""

from typing import Any, Dict, List, Optional

import numpy as np

LABEL_FLIP_DEFAULT_N_SPLITS = 5
LABEL_FLIP_DEFAULT_NEIGHBORS = 5
# cleanlab filtering rule. 'predicted_neq_given' flags samples whose given
# label differs from the out-of-sample predicted argmax - the semantics of
# "label flip". cleanlab 2.9's default rule (prune_by_noise_rate) only flags
# extreme-confidence cases for k-NN probabilities; measured against the
# self-poisoned set, predicted_neq_given catches 10/10 planted flips with a
# ~3% clean false-positive rate (see run_validation.py).
LABEL_FLIP_DEFAULT_FILTER_BY = "predicted_neq_given"

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
            "locally with: pip install cleanlab  (or set label_flip.enabled=false "
            "to run with cosine + Mahalanobis only)."
        ) from exc


def _out_of_sample_pred_probs(
    emb: np.ndarray, labels: np.ndarray, classifier: str, n_splits: int, seed: int,
    n_neighbors: int,
) -> np.ndarray:
    """Cross-validated out-of-sample predicted probabilities (n, n_classes)."""
    from sklearn.model_selection import StratifiedKFold

    classes = np.unique(labels)
    if classes.shape[0] < 2:
        raise LabelFlipError(
            "Confident learning needs >= 2 distinct labels; got "
            f"{sorted(str(c) for c in classes)}."
        )
    # Every class needs enough samples for stratified k-fold.
    min_per_class = min((labels == c).sum() for c in classes)
    n_splits = max(2, min(int(n_splits), int(min_per_class)))
    if n_splits < 2:
        raise LabelFlipError(
            "Each class needs >= 2 samples for cross-validated confident learning."
        )

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    pred_probs = np.zeros((emb.shape[0], classes.shape[0]), dtype=np.float64)

    for train_idx, test_idx in skf.split(emb, labels):
        if classifier == "knn":
            from sklearn.neighbors import KNeighborsClassifier

            model = KNeighborsClassifier(n_neighbors=min(n_neighbors, train_idx.shape[0]))
        elif classifier == "logreg":
            from sklearn.linear_model import LogisticRegression

            model = LogisticRegression(max_iter=2000, random_state=seed)
        else:  # pragma: no cover - guarded by validation
            raise LabelFlipError(f"Unknown classifier '{classifier}'.")
        model.fit(emb[train_idx], labels[train_idx])
        proba = model.predict_proba(emb[test_idx])
        # Map model's internal class order into our fixed class order.
        model_classes = np.asarray(model.classes_)
        for local_j, cls in enumerate(model_classes):
            pred_probs[test_idx, int(np.where(classes == cls)[0][0])] = proba[:, local_j]

    row_sums = pred_probs.sum(axis=1, keepdims=True)
    if np.any(row_sums <= 0):
        raise LabelFlipError("Cross-validation produced zero-probability rows.")
    return pred_probs / row_sums


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
) -> Dict[str, Any]:
    """Flag likely mislabeled samples with cleanlab (out-of-sample pred_probs).

    standardization: optional (mu, sd). Distance-based classifiers (k-NN)
    need standardized embeddings - raw layout-dominated descriptors make
    neighbors meaningless. Standardization statistics must come from the
    dataset itself (or a trusted reference) and are recorded in the result.

    Returns flagged indices/ids, per-image confidence that the given label is
    wrong (1 - self-confidence), and the class mapping used.
    """
    if classifier not in _VALID_CLASSIFIERS:
        raise LabelFlipError(
            f"Unknown classifier '{classifier}'. Valid: {sorted(_VALID_CLASSIFIERS)}."
        )
    emb = np.asarray(emb, dtype=np.float64)
    if emb.ndim != 2:
        raise LabelFlipError(f"Embeddings must be 2-D, got {emb.shape}.")
    if standardization is not None:
        mu, sd = standardization
        emb = (emb - mu) / sd
    label_arr = np.asarray(labels)
    if label_arr.shape[0] != emb.shape[0]:
        raise LabelFlipError(
            f"labels length {label_arr.shape[0]} != embeddings rows {emb.shape[0]}."
        )

    find_label_issues = _require_cleanlab()

    classes = sorted(set(str(c) for c in label_arr))
    class_to_int = {c: i for i, c in enumerate(classes)}
    label_ints = np.asarray([class_to_int[str(c)] for c in label_arr], dtype=np.int64)

    pred_probs = _out_of_sample_pred_probs(
        emb, label_ints, classifier, n_splits, seed, n_neighbors
    )
    issues = find_label_issues(labels=label_ints, pred_probs=pred_probs, filter_by=filter_by)
    flagged_indices = [int(i) for i in np.where(issues)[0]]

    # Confidence that the GIVEN label is wrong: 1 - P(given | x), out-of-sample.
    self_conf = pred_probs[np.arange(len(label_ints)), label_ints]
    wrongness = 1.0 - self_conf

    per_image = [
        {
            "index": i,
            "image_id": (image_ids[i] if image_ids is not None else str(i)),
            "given_label": str(label_arr[i]),
            "predicted_label": classes[int(np.argmax(pred_probs[i]))],
            "confidence_label_wrong": round(float(wrongness[i]), 6),
        }
        for i in flagged_indices
    ]
    per_image.sort(key=lambda r: (-r["confidence_label_wrong"], r["image_id"]))

    return {
        "classifier": classifier,
        "n_splits": int(n_splits),
        "seed": int(seed),
        "filter_by": str(filter_by),
        "n_images": int(emb.shape[0]),
        "classes": classes,
        "flagged_indices": flagged_indices,
        "flagged_image_ids": [r["image_id"] for r in per_image],
        "n_flagged": len(flagged_indices),
        "per_image": per_image,
        "method": (
            f"cleanlab.find_label_issues(filter_by={filter_by}, out-of-sample "
            "pred_probs via StratifiedKFold)"
        ),
    }
