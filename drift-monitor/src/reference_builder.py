#!/usr/bin/env python3
"""
SentinelVision - Phase 2: Reference Battery Builder
===================================================

Builds the definition of "normal" for the Drift Monitor:

1. Ingests the explicitly declared reference battery images (a stable,
   known-good dataset directory). Live data is NEVER mixed in here.
2. Embeds every battery image with the shared frozen extractor.
3. Persists embeddings to reference/embeddings.npy.
4. Writes reference/reference_manifest.json with SHA-256 digests:

   - source_digest  : SHA-256 over the canonical list of
                      "relative/image/path.jpg:<filesize>:<sha256(file bytes)>"
                      entries (sorted by relative path). This pins the exact
                      source images.
   - embedding_digest : SHA-256 over the raw embeddings.npy bytes.
   - manifest_digest  : SHA-256 over the canonical manifest JSON *before*
                        the manifest_digest field is added.

The manifest is the identity of "normal": any change to the battery images,
the backbone or the preprocessing changes the digests, so the reference
cannot be silently replaced.

Usage:
    python -m src.reference_builder --config config.json
"""

import argparse
import json
import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np

from . import ensure_shared_importable  # noqa: F401  (path bootstrap)

from shared.embeddings.embedding_extractor import (
    EmbeddingError,
    create_extractor,
    load_image,
)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def canonical_json_bytes(obj: Any) -> bytes:
    """Same canonicalization as Model Integrity evidence: sorted keys, compact separators."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS


def discover_images(input_dir: str) -> List[str]:
    """Deterministically list image files under input_dir (sorted relative paths)."""
    if not os.path.isdir(input_dir):
        raise EmbeddingError(f"Reference image directory not found: {input_dir}")
    found: List[str] = []
    for root, _dirs, files in os.walk(input_dir):
        for name in files:
            path = os.path.join(root, name)
            if _is_image(path):
                rel = os.path.relpath(path, input_dir).replace(os.sep, "/")
                found.append(rel)
    return sorted(found)


def compute_source_digest(input_dir: str, rel_paths: List[str]) -> str:
    """SHA-256 over the canonical per-image 'relpath:size:filehash' list."""
    parts: List[str] = []
    for rel in rel_paths:
        abspath = os.path.join(input_dir, rel)
        with open(abspath, "rb") as f:
            data = f.read()
        parts.append(f"{rel}:{len(data)}:{sha256_bytes(data)}")
    return sha256_bytes(canonical_json_bytes(parts))


def build_reference(config: Dict[str, Any], base_dir: str = BASE_DIR) -> Dict[str, Any]:
    """Build reference embeddings + manifest from config. Returns the manifest."""
    embedding_cfg = config.get("embedding", {})
    ref_cfg = config.get("reference", {})
    input_dir = ref_cfg.get("input_dir", "")
    if not input_dir:
        raise EmbeddingError(
            "config.reference.input_dir is required (directory of known-good battery images)."
        )
    if not os.path.isabs(input_dir):
        input_dir = os.path.abspath(os.path.join(base_dir, input_dir))

    reference_id = ref_cfg.get("reference_id", "reference-v1")
    reference_dir = os.path.join(base_dir, "reference")
    os.makedirs(reference_dir, exist_ok=True)

    extractor = create_extractor(embedding_cfg)
    meta = extractor.metadata()

    rel_paths = discover_images(input_dir)
    if not rel_paths:
        raise EmbeddingError(f"No images found under {input_dir}")

    batch_size = int(embedding_cfg.get("batch_size", 32))
    embeddings: List[np.ndarray] = []
    for start in range(0, len(rel_paths), batch_size):
        batch_paths = rel_paths[start:start + batch_size]
        images = [load_image(os.path.join(input_dir, p)) for p in batch_paths]
        embeddings.append(extractor.extract_batch(images))
    emb = np.concatenate(embeddings, axis=0) if embeddings else np.zeros((0, 0))
    if emb.ndim != 2 or emb.shape[0] != len(rel_paths):
        raise EmbeddingError("Reference embedding batch assembly failed.")

    embeddings_path = os.path.join(reference_dir, "embeddings.npy")
    np.save(embeddings_path, emb)

    source_digest = compute_source_digest(input_dir, rel_paths)
    with open(embeddings_path, "rb") as f:
        embedding_digest = sha256_bytes(f.read())

    manifest: Dict[str, Any] = {
        "reference_id": reference_id,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "backbone": meta["backbone"],
        "backbone_metadata": meta,
        "embedding_dim": int(emb.shape[1]),
        "preprocessing": meta.get("preprocessing", {}),
        "preprocessing_version": meta.get("preprocessing_version"),
        "image_count": int(emb.shape[0]),
        "source": os.path.relpath(input_dir, base_dir).replace(os.sep, "/"),
        "image_paths": rel_paths,
        "source_digest": source_digest,
        "embedding_digest": embedding_digest,
        "storage": {
            "embeddings_file": "reference/embeddings.npy",
            "dtype": str(emb.dtype),
        },
    }
    manifest["manifest_digest"] = sha256_bytes(canonical_json_bytes(manifest))

    manifest_path = os.path.join(reference_dir, "reference_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(
        f"[OK] reference battery built: {manifest['image_count']} images, "
        f"backbone={manifest['backbone']}, dim={manifest['embedding_dim']}"
    )
    print(f"[OK] manifest: {manifest_path} (digest {manifest['manifest_digest'][:16]}...)")
    return manifest


def load_reference(base_dir: str = BASE_DIR) -> Dict[str, Any]:
    """Load the built reference: {'manifest': ..., 'embeddings': np.ndarray}.

    Validates that embeddings.npy still matches the manifest's
    embedding_digest so the reference cannot be silently swapped.
    """
    manifest_path = os.path.join(base_dir, "reference", "reference_manifest.json")
    embeddings_path = os.path.join(base_dir, "reference", "embeddings.npy")
    if not os.path.isfile(manifest_path) or not os.path.isfile(embeddings_path):
        raise EmbeddingError(
            "Reference battery not found. Build it first: python -m src.reference_builder --config config.json"
        )
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    emb = np.load(embeddings_path)
    if emb.ndim != 2 or emb.shape[0] != manifest.get("image_count"):
        raise EmbeddingError(
            f"Reference embeddings shape {emb.shape} does not match manifest image_count "
            f"{manifest.get('image_count')}. Rebuild the reference battery."
        )
    if emb.shape[1] != manifest.get("embedding_dim"):
        raise EmbeddingError("Reference embedding_dim mismatch vs manifest.")
    with open(embeddings_path, "rb") as f:
        digest = sha256_bytes(f.read())
    if digest != manifest.get("embedding_digest"):
        raise EmbeddingError(
            "embeddings.npy does not match reference_manifest.embedding_digest; "
            "the reference artifact was modified. Rebuild the reference battery."
        )
    return {"manifest": manifest, "embeddings": emb}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the drift reference battery")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    args = parser.parse_args()

    config_path = os.path.abspath(args.config)
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    build_reference(config, base_dir=os.path.dirname(config_path))


if __name__ == "__main__":
    main()
