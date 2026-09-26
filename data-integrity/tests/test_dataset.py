"""Tests for the dataset loader + embedding cache."""

import json
import os

import numpy as np
import pytest

from src.dataset import DatasetError, build_dataset, discover_images, load_labels


def _make_images(directory, names, size=(24, 18)):
    from PIL import Image

    os.makedirs(directory, exist_ok=True)
    rng = np.random.default_rng(7)
    for name in names:
        arr = rng.integers(0, 255, size=(size[1], size[0], 3), dtype=np.uint8)
        Image.fromarray(arr, mode="RGB").save(os.path.join(directory, name), format="PNG")


def _write_labels(directory, labels):
    path = os.path.join(directory, "labels.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(labels, f)
    return path


def test_discover_images_sorted_and_filtered(tmp_path):
    _make_images(str(tmp_path), ["b.png", "a.png", "c.txt"])
    assert discover_images(str(tmp_path)) == ["a.png", "b.png"]


def test_discover_missing_dir_raises(tmp_path):
    with pytest.raises(DatasetError):
        discover_images(str(tmp_path / "nope"))


def test_load_labels_simple_and_wrapped(tmp_path):
    _make_images(str(tmp_path), ["a.png", "b.png"])
    p1 = _write_labels(str(tmp_path), {"a.png": "day", "b.png": "night"})
    assert load_labels(p1, ["a.png", "b.png"]) == {"a.png": "day", "b.png": "night"}
    p2 = os.path.join(str(tmp_path), "labels2.json")
    with open(p2, "w", encoding="utf-8") as f:
        json.dump({"labels": {"a.png": {"given_label": "day"}, "b.png": {"given_label": "night"}}}, f)
    assert load_labels(p2, ["a.png", "b.png"]) == {"a.png": "day", "b.png": "night"}


def test_load_labels_missing_entry_fails_closed(tmp_path):
    _make_images(str(tmp_path), ["a.png", "b.png"])
    p = _write_labels(str(tmp_path), {"a.png": "day"})
    with pytest.raises(DatasetError):
        load_labels(p, ["a.png", "b.png"])


def test_load_labels_unknown_image_fails_closed(tmp_path):
    _make_images(str(tmp_path), ["a.png"])
    p = _write_labels(str(tmp_path), {"a.png": "day", "ghost.png": "night"})
    with pytest.raises(DatasetError):
        load_labels(p, ["a.png"])


def test_build_dataset_embedding_cache_roundtrip(tmp_path):
    from shared.embeddings.embedding_extractor import PixelStatExtractor

    dim = PixelStatExtractor().embedding_dim
    _make_images(str(tmp_path), ["a.png", "b.png"])
    labels_path = _write_labels(str(tmp_path), {"a.png": "day", "b.png": "night"})
    cache_path = str(tmp_path / "cache" / "embeddings.json")

    cfg = {"backbone": "pixelstat"}
    ds, meta = build_dataset(str(tmp_path), labels_path, cfg, cache_path=cache_path)
    assert meta["image_count"] == 2
    emb1 = ds.embeddings()
    assert emb1.shape == (2, dim)
    assert os.path.isfile(cache_path)
    # Second load must hit the cache and produce identical embeddings.
    ds2, _ = build_dataset(str(tmp_path), labels_path, cfg, cache_path=cache_path)
    emb2 = ds2.embeddings()
    assert np.allclose(emb1, emb2)


def test_cache_invalidated_when_file_changes(tmp_path):
    from PIL import Image

    _make_images(str(tmp_path), ["a.png"])
    labels_path = _write_labels(str(tmp_path), {"a.png": "day"})
    cache_path = str(tmp_path / "cache.json")
    cfg = {"backbone": "pixelstat"}
    ds, _ = build_dataset(str(tmp_path), labels_path, cfg, cache_path=cache_path)
    e1 = ds.embeddings()[0]
    # Modify the file bytes.
    Image.fromarray(np.zeros((18, 24, 3), dtype=np.uint8), mode="RGB").save(
        os.path.join(str(tmp_path), "a.png"), format="PNG"
    )
    ds2, _ = build_dataset(str(tmp_path), labels_path, cfg, cache_path=cache_path)
    e2 = ds2.embeddings()[0]
    assert not np.allclose(e1, e2)


def test_cache_discarded_on_backbone_change(tmp_path):
    _make_images(str(tmp_path), ["a.png"])
    labels_path = _write_labels(str(tmp_path), {"a.png": "day"})
    cache_path = str(tmp_path / "cache.json")
    cfg = {"backbone": "pixelstat"}
    ds, _ = build_dataset(str(tmp_path), labels_path, cfg, cache_path=cache_path)
    ds.embeddings()
    with open(cache_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    raw["backbone"] = "some_other_backbone"
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(raw, f)
    ds2, _ = build_dataset(str(tmp_path), labels_path, cfg, cache_path=cache_path)
    # Cache is ignored; recompute must still work.
    assert ds2.embeddings().shape[0] == 1
