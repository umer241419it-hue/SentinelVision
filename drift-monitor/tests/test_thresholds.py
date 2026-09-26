"""
Unit tests - threshold calibration (task.md 15.3).
"""

import numpy as np
import pytest

from src.mmd import mmd
from src.threshold_calibrator import (
    CalibrationUnavailableError,
    _calibration_identity,
    calibrate,
    load_calibration,
)


def _make_reference(n: int, dim: int = 16, seed: int = 100) -> dict:
    rng = np.random.default_rng(seed)
    emb = rng.normal(0, 1, (n, dim))
    manifest = {
        "reference_id": "reference-test",
        "manifest_digest": f"digest-{seed}",
        "source_digest": "src",
        "embedding_digest": "emb",
        "backbone": "pixelstat",
        "embedding_dim": dim,
    }
    return {"manifest": manifest, "embeddings": emb}


def _make_config(**overrides) -> dict:
    cfg = {
        "mmd": {"kernel": "rbf", "bandwidth": "auto"},
        "calibration": {"seed": 42, "sample_count": 60, "quantile": 0.99, "split_size": 0},
    }
    cfg["calibration"].update(overrides)
    return cfg


def test_calibration_same_reference_stays_below_threshold():
    """Deliberately shifted samples must exceed the threshold materially, while
    same-reference splits mostly remain below it."""
    reference = _make_reference(80, seed=101)
    config = _make_config()
    cal = calibrate(reference, config, base_dir="/tmp/x", write_manifest=False)
    thr = cal["threshold"]

    rng = np.random.default_rng(202)
    below = 0
    for _ in range(20):
        perm = rng.permutation(80)
        a = reference["embeddings"][perm[:40]]
        b = reference["embeddings"][perm[40:]]
        if mmd(a, b, {"bandwidth": "auto"}).mmd <= thr:
            below += 1
    assert below >= 18, f"only {below}/20 same-reference splits below threshold"

    shifted = rng.normal(3, 1, (40, 16))
    assert mmd(reference["embeddings"][perm[:40]], shifted, {"bandwidth": "auto"}).mmd > thr


def test_calibration_fixed_seed_reproducible():
    reference = _make_reference(60, seed=102)
    config = _make_config()
    c1 = calibrate(reference, config, base_dir="/tmp/x", write_manifest=False)
    c2 = calibrate(reference, config, base_dir="/tmp/x", write_manifest=False)
    assert c1["threshold"] == c2["threshold"]
    assert c1["calibration_id"] == c2["calibration_id"]
    assert c1["null_summary"] == c2["null_summary"]


def test_calibration_identity_changes_with_reference():
    """Changing reference data must change the calibration identity."""
    config = _make_config()
    r1 = _make_reference(60, seed=103)
    r2 = _make_reference(60, seed=104)
    c1 = calibrate(r1, config, base_dir="/tmp/x", write_manifest=False)
    c2 = calibrate(r2, config, base_dir="/tmp/x", write_manifest=False)
    assert c1["calibration_id"] != c2["calibration_id"]
    assert c1["reference_manifest_digest"] != c2["reference_manifest_digest"]


def test_calibration_manifest_fields_and_versioning():
    reference = _make_reference(60, seed=105)
    cal = calibrate(reference, _make_config(), base_dir="/tmp/x", write_manifest=False)
    for field in ("calibration_id", "method", "reference_id", "threshold", "quantile",
                  "seed", "sample_count", "generated_at", "reference_manifest_digest"):
        assert field in cal, f"missing {field}"
    assert cal["method"] == "reference_null"
    assert cal["threshold"] > 0


def test_load_calibration_fails_closed_when_missing(tmp_path):
    with pytest.raises(CalibrationUnavailableError, match="No threshold calibration"):
        load_calibration(base_dir=str(tmp_path))


def test_load_calibration_rejects_foreign_reference(tmp_path):
    reference = _make_reference(60, seed=106)
    cal = calibrate(reference, _make_config(), base_dir=str(tmp_path), write_manifest=True)
    other = _make_reference(60, seed=107)
    with pytest.raises(CalibrationUnavailableError, match="different reference battery"):
        load_calibration(base_dir=str(tmp_path),
                         reference_manifest_digest=other["manifest"]["manifest_digest"])
    # Matching digest loads fine.
    loaded = load_calibration(base_dir=str(tmp_path),
                              reference_manifest_digest=reference["manifest"]["manifest_digest"])
    assert loaded["calibration_id"] == cal["calibration_id"]


def test_calibration_identity_is_deterministic():
    inputs = {"a": 1, "b": [1, 2]}
    assert _calibration_identity(inputs) == _calibration_identity({"b": [1, 2], "a": 1})
    assert _calibration_identity(inputs).startswith("threshold-")
