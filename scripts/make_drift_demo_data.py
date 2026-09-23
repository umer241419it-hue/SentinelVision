#!/usr/bin/env python3
"""
SentinelVision - Drift demo data generator.

Creates deterministic synthetic image sets used to build the reference
battery and to demonstrate the five drift scenarios (task.md section 16):

    data/reference-battery/            120 known-good "scene" images
    data/scenario1-normal/             100 fresh images, same generator params
    data/scenario2-lighting-shift/     100 images, brightness/color shifted
    data/scenario3-source-change/      100 images, different "camera" profile
    data/scenario4-unexplained/        100 images, embedding-level-only shift
    data/scenario5-mixed/              100 images (80 normal + 20 unexplained)

Everything is seeded; regenerating reproduces byte-identical datasets
(same PNG bytes), which keeps reference digests stable.

The "scene" model: a textured ground plane + a bright sky + a small dark
object; per-image parameters (texture phase, object position, sky gradient)
vary within a fixed range so the reference is a DISTRIBUTION, not one image.

Usage:
    python scripts/make_drift_demo_data.py            # from SentinelVision-Malad/
"""

import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

SIZE = (96, 64)  # (width, height) - small for fast tests; statistics are what matter
SEED = 2026


def _draw_scene(draw: ImageDraw.ImageDraw, rng: np.random.Generator, profile: str) -> None:
    """Paint one deterministic synthetic 'surveillance scene'."""
    w, h = SIZE
    horizon = int(h * 0.55)

    # Sky: light vertical gradient.
    sky_top = int(rng.integers(150, 175))
    for y in range(horizon):
        v = sky_top - int(30 * y / horizon)
        draw.line([(0, y), (w, y)], fill=(v, v, min(255, v + 20)))

    # Ground: base tone + deterministic 'texture' speckle rows.
    ground_base = int(rng.integers(70, 90))
    phase = float(rng.uniform(0, 2 * np.pi))
    freq = float(rng.uniform(0.15, 0.35))
    for y in range(horizon, h):
        ripple = int(8 * np.sin(freq * y + phase))
        v = ground_base + ripple
        draw.line([(0, y), (w, y)], fill=(v, v, int(v * 0.9)))

    # Speckle stones on the ground.
    for _ in range(60):
        x = int(rng.integers(0, w))
        y = int(rng.integers(horizon, h))
        s = int(rng.integers(1, 3))
        v = int(rng.integers(ground_base - 25, ground_base + 25))
        draw.rectangle([x, y, x + s, y + s], fill=(v, v, v))

    # A dark 'object' (vehicle-ish rectangle) at a random ground position.
    ox = int(rng.integers(8, w - 40))
    oy = int(rng.integers(horizon + 4, h - 18))
    ow, oh = int(rng.integers(18, 30)), int(rng.integers(8, 13))
    if profile == "object_moved":
        ox = max(0, w - 44) if ox < w // 2 else 6
    draw.rectangle([ox, oy, ox + ow, oy + oh], fill=(25, 25, 30))
    draw.rectangle([ox + 3, oy + 2, ox + ow - 3, oy + oh // 2], fill=(60, 65, 75))

    # A few sky 'clouds'.
    for _ in range(3):
        cx, cy = int(rng.integers(0, w)), int(rng.integers(4, horizon - 8))
        cw = int(rng.integers(10, 25))
        draw.ellipse([cx, cy, cx + cw, cy + 6], fill=(235, 235, 240))


def _apply_profile(arr: np.ndarray, profile: str) -> np.ndarray:
    """Post-processing shifts that emulate operational/sensor changes."""
    if profile == "normal" or profile == "object_moved":
        return arr
    if profile == "lighting_shift":
        # Dusk: darker, warmer, slightly washed (lower contrast).
        arr = arr * 0.62 + np.array([18.0, 6.0, -6.0])
        mean = arr.mean()
        arr = mean + (arr - mean) * 0.82
        return arr
    if profile == "source_change":
        # Different 'camera': cooler white balance + strong noise + slight blur.
        arr = arr * np.array([0.92, 0.97, 1.12])
        noise = np.random.default_rng(7).normal(0, 9.0, arr.shape)
        arr = arr + noise
        return arr
    if profile == "unexplained":
        # A shift the operational diagnostics cannot explain: zero-sum
        # alternating row stripes (+/- 25 levels) confined to a horizontal
        # band covering 25% of rows. Global brightness and per-channel color
        # means are unchanged (the stripe sums to zero), aggregate contrast
        # moves only ~5% (LOW), yet ~15% of the pixelstat embedding dims
        # (band-cell std/P90 features) shift strongly, so the embedding
        # distribution moves measurably.
        h = arr.shape[0]
        band0, band1 = int(h * 0.25), int(h * 0.50)
        stripe = np.zeros((h, 1, 1))
        stripe[band0:band1:2, 0, 0] = 1.0
        stripe[band0 + 1:band1:2, 0, 0] = -1.0
        return arr + 25.0 * stripe
    return arr


def generate_set(out_dir: str, count: int, profile: str, start_index: int = 0,
                 seed_offset: int = 0, prefix: str = "img") -> None:
    os.makedirs(out_dir, exist_ok=True)
    for i in range(count):
        rng = np.random.default_rng(SEED + seed_offset + i)
        img = Image.new("RGB", SIZE)
        draw = ImageDraw.Draw(img)
        _draw_scene(draw, rng, profile)
        arr = np.asarray(img, dtype=np.float64)
        arr = _apply_profile(arr, profile)
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        out = Image.fromarray(arr, mode="RGB")
        out.save(os.path.join(out_dir, f"{prefix}_{i + start_index:04d}.png"), format="PNG")


def main() -> None:
    specs = [
        ("reference-battery", 120, "normal", 1000, 0, "ref"),
        ("scenario1-normal", 100, "normal", 2000, 500, "live"),
        ("scenario2-lighting-shift", 100, "lighting_shift", 3000, 900, "live"),
        ("scenario3-source-change", 100, "source_change", 4000, 1300, "live"),
        ("scenario4-unexplained", 100, "unexplained", 5000, 1700, "live"),
        ("scenario5-mixed", 100, "mixed_lighting", 6000, 2100, "live"),
    ]
    for name, count, profile, seed_offset, start, prefix in specs:
        out = os.path.join(DATA_DIR, name)
        if profile == "mixed_lighting":
            # Scenario 5: 80 normal + 20 dusk/lighting-shifted images,
            # interleaved (every 5th image is shifted) - a minority subset
            # inside an otherwise normal stream.
            tmp_norm = os.path.join(DATA_DIR, "_tmp_mixed_normal")
            tmp_shift = os.path.join(DATA_DIR, "_tmp_mixed_shift")
            generate_set(tmp_norm, 80, "normal", start_index=start, seed_offset=seed_offset, prefix="live")
            generate_set(tmp_shift, 20, "lighting_shift", start_index=start + 80, seed_offset=seed_offset + 31, prefix="live")
            os.makedirs(out, exist_ok=True)
            idx = 0
            # Interleave: every 5th image is from the shifted subset.
            shift_files = sorted(os.listdir(tmp_shift))
            norm_files = sorted(os.listdir(tmp_norm))
            si = 0
            for i in range(100):
                if (i + 1) % 5 == 0 and si < len(shift_files):
                    name_f = shift_files[si]
                    si += 1
                else:
                    name_f = norm_files[idx]
                    idx += 1
                os.replace(os.path.join(tmp_shift if name_f in shift_files and (i + 1) % 5 == 0 else tmp_norm, name_f),
                           os.path.join(out, f"live_{i:04d}.png"))
            os.rmdir(tmp_norm)
            os.rmdir(tmp_shift)
        else:
            generate_set(out, count, profile, start_index=start, seed_offset=seed_offset, prefix=prefix)
        print(f"[OK] {out} ({count} images, profile={profile})")
    print("[DONE] demo data ready under", DATA_DIR)


if __name__ == "__main__":
    main()
