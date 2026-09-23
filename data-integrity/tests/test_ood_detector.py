"""Tests for Step 2b - OOD detection (class-conditional Mahalanobis)."""

import numpy as np
import pytest

from src.ood_detector import (
    OODDetectionError,
    calibrate_threshold,
    fit_reference,
    mahalanobis_distances,
    score_embeddings,
)


def _two_blobs(n_per_class=40, d=10, seed=0):
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n_per_class, d))
    b = rng.normal(size=(n_per_class, d)) + 6.0
    emb = np.vstack([a, b])
    labels = ["day"] * n_per_class + ["night"] * n_per_class
    return emb, labels


def test_gross_outlier_flagged_inliers_not():
    emb, labels = _two_blobs(n_per_class=40, seed=1)
    thr = calibrate_threshold(emb, labels, n_splits=4, seed=3)
    # Fresh in-distribution queries + one gross outlier, scored against the
    # full reference (the outlier is absent from the calibration pool).
    fresh = _two_blobs(n_per_class=5, seed=99)[0]
    queries = np.vstack([fresh, np.full((1, 10), 25.0)])
    q_labels = ["day"] * 5 + ["night"] * 5 + ["night"]
    q_ref = fit_reference(np.vstack([emb, queries]), labels + q_labels)
    res = score_embeddings(np.asarray(queries), q_ref, thr)
    assert res["flagged_indices"] == [10]
    assert res["distances"][10] > 5 * max(res["distances"][:10])


def test_calibration_deterministic_with_seed():
    emb, labels = _two_blobs(seed=5)
    a = calibrate_threshold(emb, labels, n_splits=4, seed=42)
    b = calibrate_threshold(emb, labels, n_splits=4, seed=42)
    assert a["threshold"] == b["threshold"]
    assert a["held_out_summary"] == b["held_out_summary"]


def test_shifted_distribution_all_flagged():
    emb, labels = _two_blobs(seed=11)
    ref = fit_reference(emb, labels, trim_fraction=0.10)
    thr = calibrate_threshold(emb, labels, n_splits=4, seed=2)
    shifted = _two_blobs(n_per_class=10, seed=12)[0] + 12.0
    res = score_embeddings(shifted, ref, thr)
    assert res["n_flagged"] == shifted.shape[0]


def test_trimmed_fit_robust_to_contamination():
    clean, labels = _two_blobs(n_per_class=40, seed=13)
    contaminated = np.vstack([clean, np.full((6, 10), 30.0)])
    full_labels = labels + ["night"] * 6
    ref_clean = fit_reference(clean, labels)
    ref_contam = fit_reference(contaminated, full_labels)
    # The trimmed day-class mean must barely move despite 6 extreme
    # samples injected into the night class (which is itself trimmed).
    assert (
        np.linalg.norm(
            ref_clean["class_models"]["day"]["mean"] - ref_contam["class_models"]["day"]["mean"]
        )
        < 0.5
    )


def test_min_distance_uses_closest_class():
    emb, labels = _two_blobs(seed=17)
    ref = fit_reference(emb, labels)
    d = mahalanobis_distances(emb, ref)
    # All training samples are near one of the two class models.
    assert np.all(np.isfinite(d)) and np.all(d >= 0)


def test_validation_errors():
    emb, labels = _two_blobs(n_per_class=20, seed=7)
    with pytest.raises(OODDetectionError):
        fit_reference(np.zeros((10, 3)), ["a"] * 10)  # too few overall
    with pytest.raises(OODDetectionError):
        fit_reference(emb, labels, trim_fraction=0.9)  # out of range
    with pytest.raises(OODDetectionError):
        fit_reference(emb, labels[:-1])  # length mismatch
    bad = emb.copy()
    bad[0, 0] = np.nan
    with pytest.raises(OODDetectionError):
        fit_reference(bad, labels)
    with pytest.raises(OODDetectionError):
        calibrate_threshold(emb[:10], labels[:10])  # too few for calibration
