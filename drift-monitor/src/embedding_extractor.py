#!/usr/bin/env python3
"""
SentinelVision - Drift Monitor embedding extractor (shared implementation).

Phase 1 of the drift module uses the SINGLE shared embedding pipeline at
`shared/embeddings/embedding_extractor.py` so the future Data Integrity
module compares the exact same representation. This module re-exports it
for convenient in-package imports; do not add drift-specific embedding
logic here.
"""

from shared.embeddings.embedding_extractor import (  # noqa: F401
    EmbeddingError,
    MissingWeightsError,
    PixelStatExtractor,
    TorchResNet50Extractor,
    create_extractor,
    load_image,
    metadata_json,
    register_backbone,
)
