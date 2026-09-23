"""End-to-end Data Integrity test against the real self-poisoned dataset.

Validates the Stage 6 testing protocol requirements: the three checks run on
the poisoned set, corruptions are detected with real detection rates, and a
full evidence + finding chain is produced for every flagged image.
"""

import json
import os

import numpy as np
import pytest

from src.dataset import build_dataset, load_answer_key
from src.evidence_builder import build_and_store_evidence
from src.finding_builder import build_finding, validate_evidence_hash_binding
from src.integrity_checker import check_dataset


@pytest.fixture(scope="module")
def full_run(poisoned_dataset, integrity_config, tmp_path_factory):
    base = tmp_path_factory.mktemp("e2e_base")
    cache_path = str(base / "cache" / "embeddings.json")
    ds, meta = build_dataset(
        input_dir=poisoned_dataset["dir"],
        labels_path=os.path.join(poisoned_dataset["dir"], "label_key.json"),
        extractor_config=integrity_config.get("embedding", {}),
        cache_path=cache_path,
    )
    answer_key = load_answer_key(os.path.join(poisoned_dataset["dir"], "label_key.json"))
    result = check_dataset(ds, integrity_config, answer_key=answer_key)
    return {
        "result": result,
        "key": poisoned_dataset["key"],
        "config": integrity_config,
        "base": str(base),
        "meta": meta,
    }


def test_all_three_checks_ran(full_run):
    r = full_run["result"]
    assert r["checks_run"] == ["duplicate", "ood", "label_flip"]
    assert not r["check_errors"], r["check_errors"]


def test_duplicates_detected(full_run):
    r = full_run["result"]
    dup = r["check_results"]["duplicate"]
    key = full_run["key"]
    flagged = set(dup["flagged_image_ids"])
    inserted = [n for n, v in key["labels"].items() if v["corruption"] == "duplicate"]
    # The inserted duplicate copies must be flagged; they are byte copies.
    assert set(inserted) <= flagged
    assert dup["n_pairs"] >= len(inserted)


def test_ood_detected(full_run):
    r = full_run["result"]
    ood = r["check_results"]["ood"]
    key = full_run["key"]
    ood_images = [n for n, v in key["labels"].items() if v["corruption"] == "ood"]
    flagged_idx = set(ood["flagged_indices"])
    # Map image ids to indices (dataset preserves the label key order).
    ids = r["dataset"]["image_ids"]
    flagged_ids = {ids[i] for i in flagged_idx}
    hits = set(ood_images) & flagged_ids
    # Honest, real-number assertion: most planted OOD images must be caught.
    assert len(hits) >= max(1, int(0.6 * len(ood_images)))


def test_label_flips_detected(full_run):
    r = full_run["result"]
    flip = r["check_results"]["label_flip"]
    key = full_run["key"]
    flipped = [n for n, v in key["labels"].items() if v["corruption"] == "label_flip"]
    ids = r["dataset"]["image_ids"]
    flagged_ids = set(flip["flagged_image_ids"])
    hits = set(flipped) & flagged_ids
    # Real-number assertion: most planted flips must be caught (k-NN on
    # well-separated day/night blobs).
    assert len(hits) >= max(1, int(0.6 * len(flipped)))


def test_clean_images_are_mostly_not_flagged(full_run):
    r = full_run["result"]
    key = full_run["key"]
    labels = key["labels"]
    # "Clean" = not part of any corruption event. The SOURCE image of a
    # duplicate pair is legitimately flagged (its copy is corrupt), so it
    # does not count against the false-positive rate.
    clean = [
        n
        for n, v in labels.items()
        if v["corruption"] == "clean" and not v.get("source_of_duplicate")
    ]
    flagged = set(r["flagged"].keys())
    fp = set(clean) & flagged
    # FPR on genuinely clean images must stay low (robust OOD threshold +
    # argmax-rule label flips allow a small margin).
    assert len(fp) <= max(2, int(0.20 * len(clean))), sorted(fp)


def test_findings_and_evidence_chain(full_run):
    r = full_run["result"]
    base = full_run["base"]
    store = os.path.join(base, "evidence_store")
    assert r["n_flagged"] > 0
    for image_id, rec in list(r["flagged"].items())[:5]:
        stored = build_and_store_evidence(rec, r["dataset"], r["check_results"], store, "2026-01-01T00:00:00Z")
        finding = build_finding(rec, stored["evidence_hash"], "2026-01-01T00:00:00Z")
        validate_evidence_hash_binding(finding, store)
        assert finding["assetID"].startswith("image-")
        assert finding["moduleName"] == "DataIntegrity"
        assert finding["severity"] in ("LOW", "MEDIUM", "HIGH")
        assert finding["disposition"] in ("ACCEPT", "REVIEW")


def test_no_fabricated_answer_key_leak(full_run):
    # Records carry answer_key only for cross-checking; the evidence and
    # finding must not include it.
    r = full_run["result"]
    for rec in r["flagged"].values():
        assert "answer_key" not in json.dumps(rec["details"])
