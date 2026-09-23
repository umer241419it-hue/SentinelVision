"""
Unit tests - operational diagnostics (task.md 15.5).

Synthetic brightness/contrast changes must be reflected in the relevant
statistics; missing metadata yields NOT_AVAILABLE, never a crash.
"""

import numpy as np
import pytest

from conftest import make_image
from src.diagnostics import (
    LEVEL_HIGH,
    LEVEL_LOW,
    LEVEL_NA,
    build_assessment,
    compare_image_stats,
    compare_metadata,
    compute_image_stats,
)


def test_brightness_shift_detected():
    """Darkening live images must move the brightness diagnostic."""
    ref_imgs = [make_image("normal", 300 + i) for i in range(6)]
    live_imgs = [make_image("lighting_shift", 400 + i) for i in range(6)]

    ref_stats = compute_image_stats(ref_imgs)
    live_stats = compute_image_stats(live_imgs)
    assert ref_stats["brightness"]["status"] == "ok"

    ref_brightness = ref_stats["brightness"]["mean"]
    live_brightness = live_stats["brightness"]["mean"]
    assert live_brightness < ref_brightness * 0.8  # dusk profile is much darker

    diag = compare_image_stats(ref_stats, live_stats)
    assert diag["levels"]["brightness"] == LEVEL_HIGH


def test_contrast_shift_detected():
    ref_imgs = [make_image("normal", 500 + i) for i in range(6)]
    live_imgs = [make_image("lighting_shift", 600 + i) for i in range(6)]
    diag = compare_image_stats(compute_image_stats(ref_imgs), compute_image_stats(live_imgs))
    # washed-out profile lowers contrast materially
    assert diag["levels"]["contrast"] in (LEVEL_HIGH, "MEDIUM")


def test_color_shift_detected():
    ref_imgs = [make_image("normal", 700 + i) for i in range(6)]
    live_imgs = [make_image("source_change", 800 + i) for i in range(6)]
    diag = compare_image_stats(compute_image_stats(ref_imgs), compute_image_stats(live_imgs))
    assert diag["levels"]["color"] in (LEVEL_HIGH, "MEDIUM")
    per_channel = diag["details"]["color"]["per_channel"]
    assert per_channel["B"]["relative_change"] is not None


def test_no_shift_levels_low():
    ref_imgs = [make_image("normal", 900 + i) for i in range(8)]
    live_imgs = [make_image("normal", 950 + i) for i in range(8)]
    diag = compare_image_stats(compute_image_stats(ref_imgs), compute_image_stats(live_imgs))
    for key in ("brightness", "contrast", "color", "edge_density"):
        assert diag["levels"][key] == LEVEL_LOW, f"{key} = {diag['levels'][key]}"


def test_unloadable_images_degrade_not_crash():
    stats = compute_image_stats([None, 12345, "nope"])
    assert stats["image_count"] == 0
    assert stats["brightness"]["status"] == LEVEL_NA
    diag = compare_image_stats(stats, stats)
    for key in ("brightness", "contrast", "color", "edge_density", "dimensions"):
        assert diag["levels"][key] == LEVEL_NA


def test_missing_metadata_never_crashes():
    meta = compare_metadata(None, [])
    assert meta["source_ids"]["level"] == LEVEL_NA
    assert meta["modality"]["level"] == LEVEL_NA

    # Live entries without any metadata keys also fine.
    meta2 = compare_metadata({}, [{} for _ in range(5)])
    assert meta2["source_ids"]["changed"] is None


def test_source_change_metadata_detected():
    ref_meta = {"source_ids": ["camA"], "modalities": ["rgb"]}
    live_meta = [{"source_id": "camB"} for _ in range(4)]
    meta = compare_metadata(ref_meta, live_meta)
    assert meta["source_ids"]["changed"] is True
    assert meta["source_ids"]["level"] == LEVEL_HIGH


def test_source_unchanged_metadata_low():
    ref_meta = {"source_ids": ["camA"]}
    live_meta = [{"source_id": "camA"} for _ in range(4)]
    meta = compare_metadata(ref_meta, live_meta)
    assert meta["source_ids"]["changed"] is False
    assert meta["source_ids"]["level"] == LEVEL_LOW


def test_assessment_vocabulary():
    # No significant MMD shift -> NO_SIGNIFICANT_SHIFT regardless of diagnostics.
    res = build_assessment(False, {"levels": {"brightness": LEVEL_HIGH}})
    assert res["assessment"] == "NO_SIGNIFICANT_SHIFT"

    # Significant shift + operational changes -> OPERATIONAL_SHIFT_LIKELY.
    res = build_assessment(True, {"levels": {
        "brightness": LEVEL_HIGH, "contrast": LEVEL_LOW, "color": LEVEL_HIGH,
        "edge_density": LEVEL_LOW, "dimensions": LEVEL_LOW}})
    assert res["assessment"] == "OPERATIONAL_SHIFT_LIKELY"

    # Significant shift + source metadata change -> OPERATIONAL_SHIFT_LIKELY.
    res = build_assessment(True, {"levels": {
        "brightness": LEVEL_LOW, "contrast": LEVEL_LOW, "color": LEVEL_LOW,
        "edge_density": LEVEL_LOW, "dimensions": LEVEL_LOW}},
        {"source_ids": {"level": LEVEL_HIGH}})
    assert res["assessment"] == "OPERATIONAL_SHIFT_LIKELY"

    # Significant shift + nothing measurable -> INSUFFICIENT_EVIDENCE.
    res = build_assessment(True, {"levels": {
        "brightness": LEVEL_NA, "contrast": LEVEL_NA, "color": LEVEL_NA,
        "edge_density": LEVEL_NA, "dimensions": LEVEL_NA}})
    assert res["assessment"] == "INSUFFICIENT_EVIDENCE"

    # Significant shift + measured-but-unchanged -> UNEXPLAINED_SHIFT.
    res = build_assessment(True, {"levels": {
        "brightness": LEVEL_LOW, "contrast": LEVEL_LOW, "color": LEVEL_LOW,
        "edge_density": LEVEL_LOW, "dimensions": LEVEL_LOW}})
    assert res["assessment"] == "UNEXPLAINED_SHIFT"
    assert res["explanation"]["operational_explains_shift"] is False


def test_never_labels_attack():
    """The output must never contain attacker-attribution language."""
    res = build_assessment(True, {"levels": {
        "brightness": LEVEL_LOW, "contrast": LEVEL_LOW, "color": LEVEL_LOW,
        "edge_density": LEVEL_LOW, "dimensions": LEVEL_LOW}})
    text = str(res).lower()
    assert "attack" not in text
    assert "attacker" not in text
