"""
Shared fixtures and test configuration for SentinelVision Governance test suite.
"""

import json
import os
from pathlib import Path
import sys
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
GOV_ROOT = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(GOV_ROOT)

for p in (PROJECT_ROOT, os.path.join(PROJECT_ROOT, "crypto-utils"), os.path.join(PROJECT_ROOT, "inference-provenance", "src")):
    if p not in sys.path:
        sys.path.insert(0, p)


import hashlib
from canonical import canonical_json
from sign import sign_fields


@pytest.fixture
def sample_valid_seal():
    """Returns a valid signed inference seal generated with the registered key."""
    fields = {
        "sealID": "seal-test-fixture-001",
        "modelAssetID": "model-id-00000028",
        "inputHash": "f0252f29c40ffb13c7b4b8985d4b2b960f10d0755680249beb3ac33ea711c237",
        "modelDigest": "cd88076498c5c79fce68bffef38102f3394ef5c9f6691dc2f0efc48bf51f3e0b",
        "config": {"channel_order": "BGR", "device": "cpu"},
        "nonce": "1f340a714f4a0231da4865cb9ece14c0",
        "timestamp": "2026-09-22T11:19:10Z",
        "outputSummary": {"confidence": 1.0, "predicted_class": 0},
        "signerModule": "InferenceProvenance",
    }
    content_hash = hashlib.sha256(canonical_json(fields).encode("utf-8")).hexdigest()
    sig = sign_fields("InferenceProvenance", fields)
    record = dict(fields)
    record["contentHash"] = content_hash
    record["signature"] = sig
    return record
