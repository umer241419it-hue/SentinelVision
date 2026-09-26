"""
Unit tests - shared frozen embedding extractor (task.md 15.1).
"""

import os

import numpy as np
import pytest

from conftest import make_image

from shared.embeddings.embedding_extractor import (
    EmbeddingError,
    PixelStatExtractor,
    create_extractor,
    load_image,
)


@pytest.fixture(scope="module")
def extractor():
    return PixelStatExtractor({})


def test_fixed_dimension_recorded(extractor):
    meta = extractor.metadata()
    assert meta["embedding_dim"] == extractor.embedding_dim
    assert meta["backbone"] == "pixelstat"
    assert meta["frozen"] is True
    assert meta["preprocessing_version"]


def test_deterministic_output(extractor):
    img = make_image("normal", 123)
    e1 = extractor.extract(img)
    e2 = extractor.extract(img)
    np.testing.assert_allclose(e1, e2, rtol=0, atol=0)  # exactly identical


def test_batch_single_consistency(extractor):
    imgs = [make_image("normal", 200 + i) for i in range(5)]
    batch = extractor.extract_batch(imgs)
    assert batch.shape == (5, extractor.embedding_dim)
    for i, img in enumerate(imgs):
        single = extractor.extract(img)
        np.testing.assert_allclose(single, batch[i], rtol=1e-12, atol=1e-12)


def test_unknown_backbone_fails_clearly():
    with pytest.raises(EmbeddingError, match="Unknown backbone"):
        create_extractor({"backbone": "no-such-backbone"})


def test_invalid_image_array_rejected(extractor):
    with pytest.raises(EmbeddingError):
        extractor.extract_batch([np.zeros((4, 4), dtype=np.uint8)])  # not RGB
    with pytest.raises(EmbeddingError):
        extractor.extract_batch([])


def test_load_image_missing_file(tmp_path):
    with pytest.raises(EmbeddingError, match="not found"):
        load_image(str(tmp_path / "missing.png"))


def test_load_image_corrupt_file(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not-an-image")
    with pytest.raises(EmbeddingError, match="Failed to load image"):
        load_image(str(bad))


def test_load_image_rgb_conversion(tmp_path, extractor):
    from PIL import Image

    p = tmp_path / "gray.png"
    Image.new("L", (16, 16), 128).save(p)
    img = load_image(str(p))
    assert img.mode == "RGB"
    emb = extractor.extract(img)
    assert emb.shape == (extractor.embedding_dim,)
    assert np.all(np.isfinite(emb))


def test_preprocessing_metadata_matches_config(extractor):
    meta = extractor.metadata()
    assert meta["preprocessing"]["resize"] == [64, 64]
    assert meta["preprocessing"]["color"] == "RGB"


def test_resnet50_missing_weights_fails_closed():
    """resnet50 without torch/weights must fail with an explicit error, never
    attempt a network download."""
    from shared.embeddings.embedding_extractor import TORCH_AVAILABLE, TorchResNet50Extractor

    if TORCH_AVAILABLE:
        pytest.skip("torch installed; covered by local-weights resolution instead")
    with pytest.raises(EmbeddingError) as excinfo:
        create_extractor({"backbone": "resnet50"})
    assert "torch" in str(excinfo.value).lower() or "weights" in str(excinfo.value).lower()


def test_extractor_shim_reexports_shared():
    from src.embedding_extractor import PixelStatExtractor as ShimExtractor

    assert ShimExtractor is PixelStatExtractor
