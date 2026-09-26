"""
Unit tests for Provenance Aggregator and Systematic Mislabelling Detector.
"""

from src.provenance_aggregator import ProvenanceAggregator


def test_aggregator_missing_metadata_limitations():
    aggregator = ProvenanceAggregator()
    # Call with empty provenance records
    sample_findings = [{"sample_id": "voc2012_001", "reason": "Label flip detected"}]
    res = aggregator.aggregate(sample_findings=sample_findings, provenance_records={})

    assert len(res["group_findings"]) == 0
    assert any("Contributor attribution unavailable" in lim for lim in res["limitations"])
    assert any("Source attribution unavailable" in lim for lim in res["limitations"])
    assert any("Batch attribution unavailable" in lim for lim in res["limitations"])


def test_aggregator_systematic_mislabel_detection():
    aggregator = ProvenanceAggregator(
        anomaly_rate_threshold=0.15,
        min_group_size=5,
        min_anomaly_count=3,
        z_score_threshold=1.5,
    )

    # 10 samples from contributor_07, 4 of which have car -> bus confusion
    prov = {
        f"voc2012_{i:03d}": {
            "contributor_id": "contributor_07",
            "source_id": "sensor_01",
            "batch_id": "batch_05",
            "collection_id": "collection_A",
        }
        for i in range(10)
    }

    # Add 20 clean samples from contributor_01 to form a baseline
    for i in range(10, 30):
        prov[f"voc2012_{i:03d}"] = {
            "contributor_id": "contributor_01",
            "source_id": "sensor_02",
            "batch_id": "batch_01",
            "collection_id": "collection_A",
        }

    sample_findings = [
        {
            "sample_id": f"voc2012_{i:03d}",
            "anomaly_type": "label_anomaly",
            "reason": "Class confusion detected",
            "details": {"original_label": "car", "predicted_label": "bus"},
            "confidence": 0.85,
            "severity": "MEDIUM",
        }
        for i in range(4)
    ]

    res = aggregator.aggregate(sample_findings=sample_findings, provenance_records=prov)

    # Contributor_07 should be flagged for systematic anomaly
    c7_findings = [gf for gf in res["group_findings"] if gf["group_id"] == "contributor_07"]
    assert len(c7_findings) == 1
    c7 = c7_findings[0]
    assert c7["affected_samples"] == 4
    assert c7["total_samples"] == 10
    assert c7["affected_fraction"] == 0.40
    assert "car -> bus" in c7["dominant_confusion"]
    assert c7["severity"] in ("MEDIUM", "HIGH")
    assert c7["disposition"] == "REVIEW"
    assert "anomal" in c7["finding"].lower() or "risk" in c7["finding"].lower()


def test_aggregator_decoupled_confidence_and_severity():
    aggregator = ProvenanceAggregator(min_group_size=3, min_anomaly_count=2, anomaly_rate_threshold=0.1)
    prov = {
        f"voc2012_{i:02d}": {
            "contributor_id": "c1",
            "source_id": "s1",
            "batch_id": "b1",
            "collection_id": "coll1",
        }
        for i in range(5)
    }
    sample_findings = [
        {"sample_id": "voc2012_00", "anomaly_type": "trigger_anomaly", "reason": "Trigger patch"},
        {"sample_id": "voc2012_01", "anomaly_type": "trigger_anomaly", "reason": "Trigger patch"},
    ]
    res = aggregator.aggregate(sample_findings=sample_findings, provenance_records=prov)
    assert len(res["group_findings"]) >= 1
    gf = res["group_findings"][0]
    # Trigger presence escalates severity to HIGH
    assert gf["severity"] == "HIGH"
    # Confidence is a float within [0.6, 0.95]
    assert 0.60 <= gf["confidence"] <= 0.95
