"""
Unit tests for Training-Data Trigger Injection Detector.
"""

import numpy as np
from PIL import Image
import pytest

from src.trigger_detector import (
    TriggerDetector,
    extract_corner_patches,
    compute_patch_residual,
    normalized_cross_correlation,
    detect_triggers_in_dataset,
)


def _make_dummy_image(seed: int = 42, size=(100, 100)) -> Image.Image:
    rng = np.random.RandomState(seed)
    arr = rng.randint(20, 230, (size[1], size[0], 3), dtype=np.uint8)
    return Image.fromarray(arr, mode="RGB")


def _stamp_patch(img: Image.Image, patch_size=(16, 16)) -> Image.Image:
    img_copy = img.copy()
    w, h = img_copy.size
    pw, ph = patch_size
    arr = np.array(img_copy)
    for r in range(ph):
        for c in range(pw):
            color = [255, 255, 0] if (r // 4 + c // 4) % 2 == 0 else [255, 0, 128]
            arr[h - ph - 2 + r, w - pw - 2 + c] = color
    return Image.fromarray(arr, mode="RGB")


def test_extract_corner_patches():
    img = _make_dummy_image()
    patches = extract_corner_patches(img, patch_size=(32, 32))
    assert "bottom_right" in patches
    assert "top_left" in patches
    assert patches["bottom_right"].shape == (32, 32, 3)
    assert patches["bottom_right"].dtype == np.float32


def test_normalized_cross_correlation():
    p1 = np.ones((16, 16, 3), dtype=np.float32)
    p2 = np.ones((16, 16, 3), dtype=np.float32)
    p1[4:8, 4:8] = 0.0
    p2[4:8, 4:8] = 0.0

    # Identical structured patches -> NCC = 1.0
    ncc_ident = normalized_cross_correlation(p1, p2)
    assert pytest.approx(ncc_ident, 1e-4) == 1.0

    # Inverted patch -> NCC = -1.0
    p3 = 1.0 - p1
    ncc_inv = normalized_cross_correlation(p1, p3)
    assert pytest.approx(ncc_inv, 1e-4) == -1.0


def test_trigger_detector_flags_poisoned_class():
    # 5 natural images in aeroplane
    clean_aeroplanes = [_make_dummy_image(seed=100 + i) for i in range(5)]
    # 3 of them stamped with identical high-contrast checkerboard trigger patch
    pois_aeroplanes = [_stamp_patch(img) for img in clean_aeroplanes[:3]] + clean_aeroplanes[3:]
    # 5 clean images in dog
    clean_dogs = [_make_dummy_image(seed=200 + i) for i in range(5)]

    images_by_class = {
        "aeroplane": pois_aeroplanes,
        "dog": clean_dogs,
    }
    image_ids_by_class = {
        "aeroplane": [f"aero_{i}" for i in range(5)],
        "dog": [f"dog_{i}" for i in range(5)],
    }

    res = detect_triggers_in_dataset(
        images_by_class=images_by_class,
        image_ids_by_class=image_ids_by_class,
        regions=["bottom_right"],
        correlation_threshold=0.75,
        min_cluster_size=2,
    )

    assert "aeroplane" in res["class_summaries"]
    assert res["class_summaries"]["aeroplane"]["status"] == "SUSPICIOUS_TRIGGER_DETECTED"
    assert res["class_summaries"]["dog"]["status"] == "CLEAN"
    assert len(res["flagged_samples"]) >= 2
    for s_id in ["aero_0", "aero_1"]:
        assert s_id in res["flagged_samples"]
        f = res["flagged_samples"][s_id]
        assert f["target_class"] == "aeroplane"
        assert f["severity"] == "HIGH"
