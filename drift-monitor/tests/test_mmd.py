"""
Unit tests - MMD implementation (task.md 15.2).

Synthetic controlled cases:
  A: identical distributions       -> low MMD / no significant shift
  B: mean shift  N(0,1) vs N(3,1)  -> significant shift
  C: variance shift N(0,1) vs N(0,3) -> significant shift
  D: invalid inputs                -> explicit validation errors (fail closed)
"""

import numpy as np
import pytest

from src.mmd import MMDValidationError, mmd, select_bandwidth


def _synthetic(n: int, m: int, seed: int):
    rng = np.random.default_rng(seed)
    return rng.normal(0, 1, (n, 8)), rng.normal(0, 1, (m, 8))


def test_case_a_identical_distribution_low_mmd():
    ref, live = _synthetic(120, 120, seed=1)
    res = mmd(ref, live, {"kernel": "rbf", "bandwidth": "auto"})
    assert res.mmd < 0.05, f"expected low MMD, got {res.mmd}"


def test_case_b_mean_shift_significant():
    rng = np.random.default_rng(2)
    ref = rng.normal(0, 1, (120, 8))
    live = rng.normal(3, 1, (120, 8))
    res = mmd(ref, live, {"kernel": "rbf", "bandwidth": "auto"})
    assert res.mmd > 0.3, f"expected large MMD, got {res.mmd}"


def test_case_c_variance_shift_significant():
    rng = np.random.default_rng(3)
    ref = rng.normal(0, 1, (120, 8))
    live = rng.normal(0, 3, (120, 8))
    res = mmd(ref, live, {"kernel": "rbf", "bandwidth": "auto"})
    assert res.mmd > 0.1, f"expected material MMD, got {res.mmd}"


def test_shifted_much_larger_than_same():
    ref, live_same = _synthetic(150, 150, seed=4)
    rng = np.random.default_rng(5)
    live_shift = rng.normal(2.5, 1, (150, 8))
    mmd_same = mmd(ref, live_same, {}).mmd
    mmd_shift = mmd(ref, live_shift, {}).mmd
    assert mmd_shift > 5 * max(mmd_same, 1e-6)


def test_case_d_dimension_mismatch():
    ref = np.zeros((10, 8))
    live = np.zeros((10, 9))
    with pytest.raises(MMDValidationError, match="Dimension mismatch"):
        mmd(ref, live, {})


def test_case_d_nan_embeddings_rejected():
    ref, live = _synthetic(20, 20, seed=6)
    live[3, 2] = np.nan
    with pytest.raises(MMDValidationError, match="NaN/Inf"):
        mmd(ref, live, {})


def test_case_d_empty_inputs_rejected():
    with pytest.raises(MMDValidationError):
        mmd(np.zeros((0, 8)), np.zeros((5, 8)), {})
    ref, live = _synthetic(20, 20, seed=7)
    with pytest.raises(MMDValidationError, match="Insufficient live samples"):
        mmd(ref, live[:1], {})


def test_case_d_non_2d_rejected():
    with pytest.raises(MMDValidationError, match="2-D"):
        mmd(np.zeros(10), np.zeros((5, 8)), {})


def test_unsupported_kernel_rejected():
    ref, live = _synthetic(20, 20, seed=8)
    with pytest.raises(MMDValidationError, match="kernel"):
        mmd(ref, live, {"kernel": "laplace"})


def test_mmd_non_negative_and_result_fields():
    ref, live = _synthetic(60, 60, seed=9)
    res = mmd(ref, live, {"kernel": "rbf", "bandwidth": "auto"})
    d = res.to_dict()
    assert d["mmd"] >= 0.0
    assert d["kernel"] == "rbf"
    assert "bandwidth" in d["kernel_parameters"]
    assert d["reference_count"] == 60 and d["live_count"] == 60
    assert d["bandwidth_source"].startswith("heuristic:")


def test_numeric_bandwidth_is_explicit_and_recorded():
    ref, live = _synthetic(40, 40, seed=10)
    res = mmd(ref, live, {"kernel": "rbf", "bandwidth": 1.5})
    assert res.bandwidth == 1.5
    assert res.bandwidth_source == "config:explicit"


def test_bandwidth_auto_degenerate_fallback():
    ref = np.ones((10, 4))  # all identical points -> zero median distance
    live = np.ones((10, 4))
    bw, source = select_bandwidth(ref, live, "auto")
    assert bw == 1.0 and source.endswith("degenerate_fallback")


def test_permutation_test_deterministic_and_reported():
    ref, live_same = _synthetic(80, 80, seed=11)
    cfg = {"kernel": "rbf", "bandwidth": "auto", "permutations": 50, "seed": 42}
    r1 = mmd(ref, live_same, cfg)
    r2 = mmd(ref, live_same, cfg)
    assert r1.p_value == r2.p_value
    assert r1.permutation_count == 50 and r1.seed == 42
    assert r1.null_distribution is not None
    assert 0.0 <= r1.p_value <= 1.0

    rng = np.random.default_rng(12)
    live_shift = rng.normal(3, 1, (80, 8))
    shifted = mmd(ref, live_shift, cfg)
    assert shifted.p_value < r1.p_value


def test_permutations_require_seed():
    ref, live = _synthetic(20, 20, seed=13)
    with pytest.raises(MMDValidationError, match="seed"):
        mmd(ref, live, {"permutations": 10})
