#!/usr/bin/env python3
"""
SentinelVision - Stage 6 self-poisoned test-set generator (Data Integrity).

Builds a small, fully synthetic, LABELED two-class dataset ("day" scene vs
"night" scene, reusing the shared drift-demo scene model), then deliberately
corrupts a KNOWN subset exactly the way the Stage 6 build order requires:

  1. label flips   - default 10% of images get the wrong class label
  2. duplicates    - exact byte copies of a random sample of existing images
                     (filenames differ; pixels are identical)
  3. OOD insertions- images from a completely different visual domain
                     (coarse random noise blobs) that do not belong to the
                     day/night scene distribution

Because this script did the corrupting, it writes data/label_key.json - the
ground-truth answer key the validation runner is scored against:

    {
      "image_id": {"true_label": "day", "given_label": "night",
                    "corruption": "clean|label_flip|duplicate|ood",
                    "duplicate_of": "img_0007.png" | null,
                    "true_duplicate_of": "img_0007.png" | null}
    }

Everything is seeded: regenerating reproduces byte-identical datasets.

Usage (from SentinelVision-Malad/):
    python scripts/make_data_integrity_dataset.py
"""

import json
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "integrity-test")

# Reuse the drift demo scene model so both modules share one visual world.
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from generate_drift_test_data import SIZE  # noqa: E402

SEED = 4242
N_IMAGES = 100          # clean labeled images before poisoning
N_DUPLICATES = 10       # exact copies inserted
N_OOD = 10              # out-of-distribution images inserted
LABEL_FLIP_FRACTION = 0.10  # of the N_IMAGES clean images


def _draw_day_night(draw: ImageDraw.ImageDraw, rng: np.random.Generator, label: str) -> None:
    """Paint a 'day' or 'night' variant of the surveillance scene."""
    w, h = SIZE
    horizon = int(h * 0.55)
    if label == "day":
        sky_top = int(rng.integers(150, 175))
        ground_base = int(rng.integers(70, 90))
    else:  # night: dark sky, darker ground, moon instead of clouds
        sky_top = int(rng.integers(28, 44))
        ground_base = int(rng.integers(22, 36))
    for y in range(horizon):
        v = sky_top - int((20 if label == "day" else 10) * y / horizon)
        v = max(0, min(255, v))
        if label == "day":
            fill = (v, v, min(255, v + 20))
        else:
            fill = (v, v, min(255, v + 8))
        draw.line([(0, y), (w, y)], fill=fill)
    for y in range(horizon, h):
        ripple = int(8 * np.sin(float(rng.uniform(0.15, 0.35)) * y))
        v = max(0, min(255, ground_base + ripple))
        draw.line([(0, y), (w, y)], fill=(v, v, int(v * 0.9)))
    for _ in range(60):
        x = int(rng.integers(0, w))
        y = int(rng.integers(horizon, h))
        s = int(rng.integers(1, 3))
        v = int(max(0, min(255, rng.integers(ground_base - 25, ground_base + 25))))
        draw.rectangle([x, y, x + s, y + s], fill=(v, v, v))
    ox = int(rng.integers(8, w - 40))
    oy = int(rng.integers(horizon + 4, h - 18))
    ow, oh = int(rng.integers(18, 30)), int(rng.integers(8, 13))
    draw.rectangle([ox, oy, ox + ow, oy + oh], fill=(25, 25, 30))
    draw.rectangle([ox + 3, oy + 2, ox + ow - 3, oy + oh // 2], fill=(60, 65, 75))
    if label == "day":
        for _ in range(3):
            cx, cy = int(rng.integers(0, w)), int(rng.integers(4, horizon - 8))
            cw = int(rng.integers(10, 25))
            draw.ellipse([cx, cy, cx + cw, cy + 6], fill=(235, 235, 240))
    else:
        cx, cy = int(rng.integers(10, w - 20)), int(rng.integers(5, horizon - 10))
        draw.ellipse([cx, cy, cx + 9, cy + 9], fill=(230, 230, 215))


def _draw_ood(draw: ImageDraw.ImageDraw, rng: np.random.Generator) -> None:
    """A coarse random-noise-blob image: visually unrelated to scenes."""
    w, h = SIZE
    base = tuple(int(v) for v in rng.integers(30, 220, size=3))
    draw.rectangle([0, 0, w, h], fill=base)
    for _ in range(14):
        cx, cy = int(rng.integers(0, w)), int(rng.integers(0, h))
        r = int(rng.integers(4, 16))
        color = tuple(int(v) for v in rng.integers(0, 255, size=3))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)


def main() -> None:
    rng = np.random.default_rng(SEED)
    if os.path.isdir(DATA_DIR):
        shutil.rmtree(DATA_DIR)
    os.makedirs(DATA_DIR, exist_ok=True)

    records = {}
    base_imgs = []  # (filename, true_label)

    # 1. Clean labeled images with a KNOWN true label each.
    for i in range(N_IMAGES):
        true_label = "day" if i % 2 == 0 else "night"
        img = Image.new("RGB", SIZE)
        _draw_day_night(ImageDraw.Draw(img), rng, true_label)
        fname = f"img_{i:04d}.png"
        img.save(os.path.join(DATA_DIR, fname), format="PNG")
        records[fname] = {
            "true_label": true_label,
            "given_label": true_label,
            "corruption": "clean",
            "duplicate_of": None,
            "true_duplicate_of": None,
        }
        base_imgs.append((fname, true_label))

    # 2. Label flips: flip the GIVEN label of a fixed fraction of clean images.
    n_flips = max(1, int(round(LABEL_FLIP_FRACTION * N_IMAGES)))
    flip_candidates = list(range(N_IMAGES))
    rng.shuffle(flip_candidates)
    flipped = sorted(flip_candidates[:n_flips])
    for idx in flipped:
        fname, true_label = base_imgs[idx]
        wrong = "night" if true_label == "day" else "day"
        records[fname]["given_label"] = wrong
        records[fname]["corruption"] = "label_flip"

    # 3. Duplicates: byte-identical copies of a random sample of base images.
    dup_sources = rng.choice(N_IMAGES, size=N_DUPLICATES, replace=False)
    dup_sources = sorted(int(x) for x in dup_sources)
    for j, src_idx in enumerate(dup_sources):
        src_name = f"img_{src_idx:04d}.png"
        dst_name = f"dup_{j:04d}_of_img_{src_idx:04d}.png"
        with open(os.path.join(DATA_DIR, src_name), "rb") as fsrc:
            data = fsrc.read()
        with open(os.path.join(DATA_DIR, dst_name), "wb") as fdst:
            fdst.write(data)
        src_rec = records[src_name]
        records[dst_name] = {
            "true_label": src_rec["true_label"],
            "given_label": src_rec["given_label"],  # inherits any flip of its source
            "corruption": "duplicate",
            "duplicate_of": src_name,
            "true_duplicate_of": src_name,
        }
        # Mark the source as one half of the corrupted pair so scoring can
        # distinguish "member of a corrupt duplicate pair" from a false alarm.
        src_rec["source_of_duplicate"] = dst_name

    # 4. OOD insertions: unrelated noise-blob images with an arbitrary label.
    for k in range(N_OOD):
        img = Image.new("RGB", SIZE)
        _draw_ood(ImageDraw.Draw(img), rng)
        fname = f"ood_{k:04d}.png"
        img.save(os.path.join(DATA_DIR, fname), format="PNG")
        # A wrong arbitrary label: they simply "do not belong".
        given = "day" if k % 2 == 0 else "night"
        records[fname] = {
            "true_label": None,   # not part of either scene class
            "given_label": given,
            "corruption": "ood",
            "duplicate_of": None,
            "true_duplicate_of": None,
        }

    key_path = os.path.join(DATA_DIR, "label_key.json")
    with open(key_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "seed": SEED,
                "n_clean": N_IMAGES,
                "n_label_flips": len(flipped),
                "flipped_images": [base_imgs[i][0] for i in flipped],
                "n_duplicates": N_DUPLICATES,
                "duplicate_sources": [f"img_{i:04d}.png" for i in dup_sources],
                "n_ood": N_OOD,
                "labels": records,
            },
            f,
            indent=2,
            sort_keys=True,
        )
    print(f"[OK] {len(records)} images in {DATA_DIR}")
    print(f"[OK] answer key: {key_path}")
    print(f"[OK] corruption summary: clean={N_IMAGES}, label_flips={len(flipped)}, "
          f"duplicates={N_DUPLICATES}, ood={N_OOD}")


if __name__ == "__main__":
    main()
