# SentinelVision — Data Integrity Module (Stage 6, capability area a)

Algorithm-only module for **SentinelVision PS26228** that answers:

> **"Can I trust the training data itself?"** — duplicate images, statistically out-of-distribution images, and mislabeled samples are found and reported as evidence-backed findings.

It is the **Data Integrity half of Stage 6** and runs on the **single shared frozen embedding pipeline** (`shared/embeddings/embedding_extractor.py`) — the exact same representation the Drift Monitor uses. No second embedding implementation exists.

## Layout

```text
data-integrity/
├── config.json                     # single configuration file
├── run_validation.py               # Stage 6 validation runner (real numbers)
├── src/
│   ├── dataset.py                  # labeled loader + sha256-validated embedding cache
│   ├── duplicate_detector.py       # Step 2a: cosine similarity
│   ├── ood_detector.py             # Step 2b: class-conditional Mahalanobis
│   ├── label_flip_detector.py      # Step 2c: cleanlab confident learning
│   ├── integrity_checker.py        # merges flags into ONE record per image
│   ├── evidence_builder.py         # evidence JSON + SHA-256 (shared pattern)
│   ├── finding_builder.py          # existing 8-field finding schema
│   ├── bridge_client.py            # POST /findings + GET round-trip check
│   └── run_data_integrity.py       # CLI runner
├── tests/                          # unit + end-to-end + live (opt-in) tests
├── evidence_store/                 # <evidenceHash>.json artifacts (generated)
├── results/                        # integrity_results.json, validation_report.json
└── cache/                          # embedding cache (validated by file sha256)
```

## The three checks

| Check | Method | Default operating point |
|---|---|---|
| Duplicate detection | pairwise **cosine similarity** on standardized embeddings | flag at ≥ **0.99** (guide start 0.98, tuned from the measured separation: byte-copies 1.000 vs most-similar non-duplicate 0.980) |
| OOD detection | **class-conditional trimmed Mahalanobis** (min over per-class LedoitWolf Gaussians) | held-out robust threshold = median + **5·1.4826·MAD** |
| Label-flip detection | **cleanlab** `find_label_issues` on out-of-sample k-NN probabilities (5-fold StratifiedKFold) | `filter_by="predicted_neq_given"` |

Why standardization: raw cosine on layout-dominated embeddings is degenerate (everything ~0.9999); per-dimension z-scores (computed over the checked dataset, recorded in every evidence artifact) restore separation while keeping exact duplicates at 1.0.

Why class-conditional OOD: a single pooled Gaussian is blind to outliers when the clean data is bimodal (day/night) — between-class spread swamps within-class scatter.

Why median+MAD calibration: the calibration pool contains the planted outliers themselves; a raw 99th-percentile is inflated by them (measured: p99 = 132.9 vs robust threshold = 51.2 on the same pool). MAD has a 50% breakdown point.

## Quick start (offline)

```bash
cd SentinelVision-Malad

# 0. (once) generate the self-poisoned labeled test set + answer key
python scripts/make_data_integrity_dataset.py

# 1. run the module end-to-end
cd data-integrity
python -m src.run_data_integrity --config config.json \
    --input ../data/integrity-test \
    --labels ../data/integrity-test/label_key.json \
    --answer-key ../data/integrity-test/label_key.json

# 2. full validation with real numbers
python run_validation.py
```

### Submit findings through the existing bridge (Fabric)

```bash
# terminal 1 (bridge + Fabric test network must be up)
cd ../bridge && npm start

# terminal 2
cd ../data-integrity
python -m src.run_data_integrity --config config.json \
    --input ../data/integrity-test \
    --labels ../data/integrity-test/label_key.json \
    --submit --bridge-url http://localhost:3000
```

Findings are POSTed to the existing `POST /findings` and read back via `GET /findings/:id`. One finding **per flagged image** (never one per check); reasons from multiple checks are combined into the single finding. Raw embeddings and evidence JSON are **never** sent to Fabric — only the 8 fields plus the `evidenceHash` relationship.

**Stage 5 / Fabric chaincode v1.4 note:** Findings require cryptographic signing with the Ed25519 key registered under `"DataIntegrity"`. The 8 original fields are signed and the resulting 128-character hex signature is attached as the 9th field (`signature`). All unsigned findings are rejected by the bridge and chaincode v1.4.

## Finding shape (8-field schema)

```json
{
  "assetID": "image-img_0017.png",
  "moduleName": "DataIntegrity",
  "reason": "near-duplicate of dup_0000_of_img_0017.png (standardized cosine 1.000 >= threshold 0.99); likely mislabeled: given 'day', model predicts 'night' (confidence 0.98, out-of-sample)",
  "evidenceHash": "<sha256 of evidence JSON>",
  "confidence": "0.75",
  "severity": "HIGH",
  "disposition": "REVIEW",
  "timestamp": "<ISO-8601 UTC>"
}
```

Policy: confidence = 0.60 + 0.15 per additional independent flag (cap 0.95); severity = worst per-check severity (escalated to HIGH when ≥2 checks agree); disposition = REVIEW — **no automatic quarantine, ever** (human-in-the-loop, Stage 6 Constraint 5).

## Measured validation results

Self-poisoned set: 100 clean + 10 label flips + 10 byte-identical duplicates + 10 OOD noise images (seed 4242, deterministic; regenerate byte-identical with the script above). Ground truth comes from the generator's answer key.

```text
=== DATA INTEGRITY: per-check performance ===
duplicate    detection_rate=1.0    false_positive_rate=0.0     (caught=10/10 events)
ood          detection_rate=0.9    false_positive_rate=0.0     (caught=9/10 events)
label_flip   detection_rate=1.0    false_positive_rate=0.0818  (caught=10/10 events)
OVERALL      detection_rate=0.9667 false_positive_rate=0.037   (events 29/30)

=== DISTRIBUTION-SHIFT (same script proves the drift module both ways) ===
normal_window   n=100  mmd=0.005972  alert=no    [OK]
shifted_window  n=100  mmd=0.710175  alert=YES   [OK]
both directions correct: [OK] YES
```

`run_validation.py` prints the full per-image verdict table (image_id → flagged/not → which checks → confidence → verdict TP/FP/FN/clean) so a human can cross-check every row against the answer key — the verification discipline the Stage 6 build order requires.

## Honest scope statement

State plainly: the three checks above ran on the self-poisoned synthetic set described here. The perturbations tested are label flips between the two real classes, byte-identical duplicate insertion, and random-noise-blob OOD insertion. Distribution shift was validated with brightness/color-shifted synthetic windows (drift-monitor scenarios).

**Not covered:** subtle semantic near-duplicates below the 0.99 threshold; small-magnitude OOD samples below the calibrated threshold (one planted OOD image was not caught); label errors indistinguishable from clean data in embedding space; confident learning depends on the auxiliary classifier, which was not extensively tuned. No check establishes intent or identifies an attacker. One finding per flagged asset goes to human REVIEW; nothing is quarantined automatically.

## Tests

```bash
cd data-integrity
python -m pytest tests -q
```

Covers: duplicate detection (identical/distinct/standardization/validation), OOD (outlier flagged, inliers not, calibration determinism, contamination robustness, validation errors), label flips (clean data quiet, planted flips caught, per-image reasons), dataset cache (round-trip, invalidation on file change and backbone change), evidence canonicalization/hashing/binding, 8-field finding schema validation, CLI end-to-end on the real poisoned set, and the validation runner (opt-in live bridge test: `SENTINELVISION_LIVE_BRIDGE=1`).
