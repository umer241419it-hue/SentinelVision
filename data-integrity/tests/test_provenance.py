"""
Unit tests for Synthetic Provenance Metadata Generator.
"""

from src.provenance_generator import ProvenanceGenerator, generate_synthetic_provenance


def test_provenance_generation_complete_fields():
    sample_ids = [f"voc2012_{i:06d}" for i in range(25)]
    prov = generate_synthetic_provenance(
        sample_ids=sample_ids,
        num_contributors=5,
        num_sources=3,
        num_batches=8,
        collection_id="test_coll",
        seed=123,
    )
    assert prov["sample_count"] == 25
    records = prov["provenance_records"]
    assert len(records) == 25

    for sid in sample_ids:
        assert sid in records
        rec = records[sid]
        assert "contributor_id" in rec
        assert "source_id" in rec
        assert "batch_id" in rec
        assert rec["collection_id"] == "test_coll"
        assert rec["contributor_id"].startswith("contributor_")
        assert "SYNTHETIC" in rec["provenance_type"]

    assert "Synthetic benchmark provenance" in prov["provenance_disclaimer"]


def test_provenance_deterministic_reproducibility():
    sample_ids = [f"voc2012_{i:06d}" for i in range(50)]
    gen1 = ProvenanceGenerator(num_contributors=4, seed=42)
    p1 = gen1.generate_provenance(sample_ids)

    gen2 = ProvenanceGenerator(num_contributors=4, seed=42)
    p2 = gen2.generate_provenance(sample_ids)

    assert p1 == p2


def test_provenance_skew_contributor():
    sample_ids = [f"voc2012_{i:06d}" for i in range(100)]
    gen = ProvenanceGenerator(num_contributors=10, seed=42)
    p = gen.generate_provenance(sample_ids, skew_contributor="contributor_01", skew_fraction=0.8)

    c1_count = sum(1 for r in p.values() if r["contributor_id"] == "contributor_01")
    # With 80% skew, contributor_01 should dominate
    assert c1_count > 60
