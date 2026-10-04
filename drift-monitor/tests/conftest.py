"""
Shared fixtures for the drift-monitor test suite.

Generates deterministic synthetic image sets (reusing the demo generator's
scene model) and builds a full reference + calibration environment in a temp
directory so end-to-end tests exercise the real pipeline offline.
"""

import json
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRIFT_ROOT = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(DRIFT_ROOT)

for _p in (DRIFT_ROOT, PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PIL import Image, ImageDraw  # noqa: E402

from scripts.generate_drift_test_data import SIZE, _apply_profile, _draw_scene  # noqa: E402


def make_image(profile: str, seed: int):
    rng = np.random.default_rng(seed)
    img = Image.new("RGB", SIZE)
    draw = ImageDraw.Draw(img)
    _draw_scene(draw, rng, profile)
    arr = np.asarray(img, dtype=np.float64)
    arr = _apply_profile(arr, profile)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")


def write_image_set(directory: str, count: int, profile: str, seed_start: int) -> str:
    os.makedirs(directory, exist_ok=True)
    for i in range(count):
        make_image(profile, seed_start + i).save(
            os.path.join(directory, f"img_{i:04d}.png"), format="PNG"
        )
    return directory


def make_config(base_dir: str, ref_dir: str) -> dict:
    return {
        "mode": "offline",
        "embedding": {"backbone": "pixelstat", "weights_path": None, "device": "auto", "batch_size": 16},
        "reference": {"reference_id": "reference-test-v1", "input_dir": os.path.relpath(ref_dir, base_dir)},
        "window": {"size": 12, "step": 6, "minimum_samples": 12},
        "mmd": {"kernel": "rbf", "bandwidth": "auto", "permutation_test": True,
                "permutations": 30, "seed": 42, "minimum_live_samples": 2},
        "calibration": {"method": "reference_null", "quantile": 0.99, "seed": 7,
                        "sample_count": 40, "split_size": 0},
        "diagnostics": {"enabled": True},
        "policy": {"insufficient_severity": "LOW"},
        "output": {"evidence_store": "evidence_store", "results": "results/drift_results.json"},
    }


@pytest.fixture(scope="session")
def env(tmp_path_factory):
    """Full offline environment: reference battery + calibration in a temp base."""
    base = tmp_path_factory.mktemp("drift_base")
    ref_dir = write_image_set(str(base / "ref-images"), 40, "normal", 9000)

    sys.path.insert(0, DRIFT_ROOT)
    from src.reference_builder import build_reference, load_reference
    from src.threshold_calibrator import calibrate

    config = make_config(str(base), ref_dir)
    manifest = build_reference(config, base_dir=str(base))
    reference = load_reference(str(base))
    cal = calibrate(reference, config, base_dir=str(base), write_manifest=True)

    return {
        "base_dir": str(base),
        "config": config,
        "manifest": manifest,
        "reference": reference,
        "calibration": cal,
        "ref_dir": ref_dir,
    }
