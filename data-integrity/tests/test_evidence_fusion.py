"""
Unit tests for Evidence Fusion Engine.
"""

import pytest
from src.evidence_fusion import EvidenceFusionEngine


def test_fusion_empty_flags():
    engine = EvidenceFusionEngine()
    res = engine.fuse_sample_evidence("sample_001", {})
    assert res is None


def test_fusion_single_flag():
    engine = EvidenceFusionEngine()
    flags = {
        "duplicate": {
            "flagged": True,
            "confidence": 0.70,
            "severity": "LOW",
            "reason": "Cosine similarity 0.992",
            "details": {},
        }
    }
    res = engine.fuse_sample_evidence("sample_001", flags)
    assert res is not None
    assert res["sample_id"] == "sample_001"
    assert res["flags"] == ["duplicate"]
    assert res["confidence"] == 0.70
    assert res["severity"] == "LOW"
    assert res["disposition"] == "REVIEW"


def test_fusion_noisy_or_confidence():
    engine = EvidenceFusionEngine()
    # Two independent flags with confidences 0.70 and 0.80
    # Noisy-OR: 1 - (1 - 0.70) * (1 - 0.80) = 1 - 0.30 * 0.20 = 1 - 0.06 = 0.94
    flags = {
        "duplicate": {"flagged": True, "confidence": 0.70, "severity": "MEDIUM", "reason": "dup"},
        "label_flip": {"flagged": True, "confidence": 0.80, "severity": "MEDIUM", "reason": "flip"},
    }
    res = engine.fuse_sample_evidence("sample_002", flags)
    assert res is not None
    assert res["confidence"] == 0.94
    # Multi-flag consensus escalates severity to HIGH
    assert res["severity"] == "HIGH"
    assert res["disposition"] == "REVIEW"


def test_fusion_trigger_escalates_to_quarantine():
    engine = EvidenceFusionEngine(quarantine_confidence_threshold=0.88)
    flags = {
        "trigger": {
            "flagged": True,
            "confidence": 0.92,
            "severity": "HIGH",
            "reason": "Corner patch trigger",
            "details": {},
        }
    }
    res = engine.fuse_sample_evidence("sample_003", flags)
    assert res is not None
    assert res["severity"] == "CRITICAL"
    assert res["disposition"] == "QUARANTINE"
