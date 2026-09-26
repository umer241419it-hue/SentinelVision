"""Tests for Step 2c - label-flip detection via cleanlab confident learning."""

import numpy as np
import pytest

from src.duplicate_detector import standardization_stats
from src.label_flip_detector import (
    CleanlabUnavailableError,
    LabelFlipError,
    find_label_flips,
)


def _two_blobs(n_per_class=30, d=6, seed=0, separation=6.0):
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n_per_class, d))
    b = rng.normal(size=(n_per_class, d)) + separation
    emb = np.vstack([a, b])
    labels = ["day"] * n_per_class + ["night"] * n_per_class
    return emb, labels


def _standardized(emb):
    mu, sd = standardization_stats(emb)
    return (emb - mu) / sd


def test_clean_labels_produce_few_flags():
    emb, labels = _two_blobs(seed=1)
    res = find_label_flips(_standardized(emb), labels, classifier="knn", n_splits=3, seed=42)
    # With perfectly separated classes and correct labels, almost nothing
    # should be flagged.
    assert res["n_flagged"] <= 2


def test_flipped_labels_are_caught():
    emb, labels = _two_blobs(n_per_class=30, seed=2)
    flipped = [4, 35, 51]
    given = list(labels)
    for i in flipped:
        given[i] = "night" if labels[i] == "day" else "day"
    res = find_label_flips(_standardized(emb), given, classifier="knn", n_splits=3, seed=42)
    caught = set(res["flagged_indices"])
    assert set(flipped) <= caught, f"missed flips: {set(flipped) - caught}"
    assert res["flagged_image_ids"] == [str(i) for i in res["flagged_indices"]]


def test_image_ids_and_reasons_flow_through():
    emb, labels = _two_blobs(n_per_class=20, seed=3)
    ids = [f"img_{i:04d}.png" for i in range(len(labels))]
    res = find_label_flips(emb, labels, classifier="knn", n_splits=3, seed=42, image_ids=ids)
    for row in res["per_image"]:
        assert row["image_id"].startswith("img_")
        assert row["given_label"] in ("day", "night")
        assert row["predicted_label"] in ("day", "night")
        assert 0.0 <= row["confidence_label_wrong"] <= 1.0


def test_single_class_rejected():
    emb = np.random.default_rng(0).normal(size=(10, 4))
    with pytest.raises(LabelFlipError):
        find_label_flips(emb, ["day"] * 10)


def test_length_mismatch_rejected():
    emb = np.zeros((5, 3))
    with pytest.raises(LabelFlipError):
        find_label_flips(emb, ["a", "b"])
