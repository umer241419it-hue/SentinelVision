"""Tests for Step 2a - duplicate detection via (standardized) cosine similarity."""

import numpy as np
import pytest

from src.duplicate_detector import (
    DuplicateDetectionError,
    find_duplicates,
    pairwise_cosine_similarity,
    standardization_stats,
)


def test_identical_vectors_flagged():
    emb = np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    res = find_duplicates(emb, ["a", "a_copy", "b"], threshold=0.98)
    assert res["n_pairs"] == 1
    pair = res["pairs"][0]
    assert {pair["image_a"], pair["image_b"]} == {"a", "a_copy"}
    assert pair["similarity"] > 0.999
    assert res["flagged_image_ids"] == ["a", "a_copy"]


def test_distinct_vectors_not_flagged():
    emb = np.array([[1.0, 0.0], [0.0, 1.0], [0.0, -1.0]])
    res = find_duplicates(emb, ["x", "y", "z"], threshold=0.98)
    assert res["n_pairs"] == 0
    assert res["flagged_image_ids"] == []


def test_near_duplicate_below_one():
    # 10-degree rotation keeps cosine well above 0.98 threshold? cos(10deg)=0.985
    v1 = np.array([1.0, 0.0])
    theta = np.deg2rad(2)
    v2 = np.array([np.cos(theta), np.sin(theta)])
    res = find_duplicates(np.vstack([v1, v2]), ["p", "q"], threshold=0.98)
    assert res["n_pairs"] == 1
    assert 0.98 <= res["pairs"][0]["similarity"] <= 1.0


def test_threshold_higher_fewer_pairs():
    rng = np.random.default_rng(0)
    base = rng.normal(size=(10, 16))
    noisy = base + rng.normal(scale=0.05, size=(10, 16))
    strict = find_duplicates(noisy, [f"i{i}" for i in range(10)], threshold=0.999999)
    loose = find_duplicates(noisy, [f"i{i}" for i in range(10)], threshold=0.90)
    assert strict["n_pairs"] <= loose["n_pairs"]


def test_zero_norm_embedding_rejected():
    emb = np.array([[1.0, 0.0], [0.0, 0.0]])
    with pytest.raises(DuplicateDetectionError):
        pairwise_cosine_similarity(emb)


def test_length_mismatch_rejected():
    emb = np.eye(3)
    with pytest.raises(DuplicateDetectionError):
        find_duplicates(emb, ["a", "b"], threshold=0.98)


def test_invalid_threshold_rejected():
    emb = np.eye(2)
    with pytest.raises(DuplicateDetectionError):
        find_duplicates(emb, ["a", "b"], threshold=1.5)


def test_standardization_separates_shared_layout():
    # A shared dominant layout (large constant component) makes raw cosine
    # degenerate; standardization must restore separation while keeping
    # exact duplicates at 1.0.
    rng = np.random.default_rng(0)
    layout = np.full(16, 10.0)
    scene_a = rng.normal(scale=0.1, size=16)
    scene_b = rng.normal(scale=0.1, size=16)
    emb = np.vstack([layout + scene_a, layout + scene_a, layout + scene_b])
    mu, sd = standardization_stats(emb)
    res = find_duplicates(emb, ["a", "a_copy", "b"], threshold=0.99, standardization=(mu, sd))
    assert res["scoring"] == "standardized_cosine"
    assert res["n_pairs"] == 1
    assert {res["pairs"][0]["image_a"], res["pairs"][0]["image_b"]} == {"a", "a_copy"}


def test_standardized_identical_rows_still_one():
    rng = np.random.default_rng(1)
    emb = rng.normal(size=(6, 8))
    emb[3] = emb[1]  # exact duplicate
    mu, sd = standardization_stats(emb)
    res = find_duplicates(emb, [f"i{i}" for i in range(6)], threshold=0.99, standardization=(mu, sd))
    dup_pairs = [p for p in res["pairs"] if {p["image_a"], p["image_b"]} == {"i1", "i3"}]
    assert dup_pairs and dup_pairs[0]["similarity"] == 1.0
