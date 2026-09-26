# SentinelVision — Distribution-Shift / Drift Monitoring Module

Algorithm-only module for **SentinelVision PS26228** that answers:

> *"Do recent incoming images still look like the normal/reference data this CV pipeline was expected to see?"*

It detects distribution shift using the **shared frozen image-embedding pipeline** and **Maximum Mean Discrepancy (MMD)** between a reference battery and rolling live windows, then records evidence-backed, conservatively-worded findings through the **existing** SentinelVision evidence → SHA-256 → 9-field signed finding → bridge → Fabric workflow.

## Layout

```text
shared/embeddings/embedding_extractor.py   # ONE shared embedding pipeline (reusable by Data Integrity later)
drift-monitor/
├── config.json                            # single configuration file
├── src/
│   ├── embedding_extractor.py             # thin re-export of the shared extractor
│   ├── reference_builder.py               # Phase 2: reference battery + manifest + digests
│   ├── rolling_window.py                  # Phase 3: deterministic rolling live window
│   ├── mmd.py                             # Phase 4: MMD (RBF kernel, permutation test)
│   ├── threshold_calibrator.py            # Phase 5: reference-vs-reference null calibration
│   ├── diagnostics.py                     # Phase 6: operational drift diagnostics
│   ├── drift_detector.py                  # Phase 7: assessment + confidence/severity/disposition
│   ├── evidence_builder.py                # Phase 8: evidence JSON + SHA-256 (Model Integrity pattern)
│   ├── finding_builder.py                 # Phase 9: existing 9-field signed finding schema
│   └── run_drift_monitor.py               # Phase 10: CLI end-to-end runner (+ bridge submission)
├── tests/                                 # Phase 11: unit/integration/determinism tests
├── reference/      # reference_manifest.json + embeddings.npy   (generated)
├── calibration/    # threshold_manifest.json                   (generated)
├── evidence_store/ # <evidenceHash>.json artifacts             (generated)
└── results/        # drift_results.json                        (generated)
```

## Backbones

| Backbone | Dim | Weights | Notes |
|---|---|---|---|
| `pixelstat` (default) | 350 | none required | Deterministic image-statistics descriptor; fully offline; used for development/tests/demo. |
| `resnet50` | 2048 | local file required | Frozen torchvision ResNet-50 pooling features. **Never downloads weights**; raises `MissingWeightsError` with actionable guidance when absent. |

The backbone registry (`shared/embeddings/embedding_extractor.py`) lets a future backbone (e.g. CLIP) be added without rewriting the drift detector. The later **Data Integrity module must reuse the same shared extractor** — do not fork it.

## Quick start (offline)

```bash
cd drift-monitor

# 0. (once) generate demo data: reference battery + 5 scenario image sets
python ../../scripts/make_drift_demo_data.py

# 1. build reference embeddings + manifest
python -m src.reference_builder --config config.json

# 2. calibrate the drift threshold from reference-vs-reference nulls
python -m src.threshold_calibrator --config config.json

# 3. run the detector on a live directory
python -m src.run_drift_monitor --config config.json --input ../data/scenario1-normal
```

The runner prints `[OK]` startup-validation lines (offline mode, reference battery, calibration manifest) or fails with actionable messages.

### Submit findings through the existing bridge (Fabric)

```bash
# terminal 1 (bridge + Fabric test network must be up)
cd ../bridge && npm start

# terminal 2
python -m src.run_drift_monitor --config config.json \
    --input ../data/scenario2-lighting-shift --submit --bridge-url http://localhost:3000
```

Findings are POSTed to the existing `POST /findings` and read back via `GET /findings/:id`. Raw embeddings and evidence JSON are **never** sent to Fabric — only the 8 fields plus the `evidenceHash` relationship.

**Stage 5 / Fabric chaincode v1.4 note:** Findings require cryptographic signing with the Ed25519 key registered under `"DistributionShift"`. The 8 original fields are signed and the resulting 128-character hex signature is attached as the 9th field (`signature`). All unsigned findings are rejected by the bridge and chaincode v1.4.

## Reproducibility

Every run records module version, reference ID + digests, backbone + preprocessing config, embedding dim, kernel + bandwidth, calibration ID + threshold, window size/step, seeds, permutation count and input identifiers in `results/drift_results.json`.

Byte-identical evidence reruns:

```bash
python -m src.run_drift_monitor --config config.json --input ../data/scenario1-normal \
    --timestamp-fixed 2026-01-01T00:00:00Z
```

Same input + configuration ⇒ same MMD values, same assessments, same evidence hashes (fixed timestamp), same deterministic assetIDs.

## Assessments (conservative vocabulary)

| Assessment | Meaning | Severity | Disposition |
|---|---|---|---|
| `NO_SIGNIFICANT_SHIFT` | MMD within calibrated reference variation | LOW | ACCEPT |
| `OPERATIONAL_SHIFT_LIKELY` | Significant MMD + measurable operational change (brightness/color/contrast/source…) | MEDIUM | REVIEW |
| `UNEXPLAINED_SHIFT` | Significant MMD, nothing measurable explains it | HIGH | REVIEW |
| `INSUFFICIENT_EVIDENCE` | Missing calibration / incompatible inputs / too few samples | LOW (configurable) | REVIEW |

A high drift score means **the live distribution differs from the reference distribution** — never "an attacker caused this". Unexplained shifts are surfaced for human review.

## Demo scenarios (after step 0 above)

| Scenario | Command (`--input`) | Expected |
|---|---|---|
| 1 Normal operation | `../data/scenario1-normal` | `NO_SIGNIFICANT_SHIFT` / ACCEPT |
| 2 Seasonal/lighting shift | `../data/scenario2-lighting-shift` | MMD up, brightness diagnostics HIGH → `OPERATIONAL_SHIFT_LIKELY` |
| 3 Sensor/source change | `../data/scenario3-source-change` | Significant shift, source diagnostics changed |
| 4 Unexplained shift | `../data/scenario4-unexplained` | `UNEXPLAINED_SHIFT` / REVIEW |
| 5 Mixed window | `../data/scenario5-mixed` | Measured result (20% shifted subset) |

## Tests

```bash
pytest drift-monitor/tests -q
```

Covers: embedding determinism/dim/batch consistency/invalid images, MMD synthetic cases (same / mean-shift / variance-shift / invalid), threshold calibration reproducibility + identity change, rolling-window lifecycle, diagnostics (missing metadata ⇒ `NOT_AVAILABLE`, not a crash), evidence canonicalization/hashing, 9-field signed finding schema, and an end-to-end run.

## Known limitations

See `COVERAGE_STATEMENT` / `KNOWN_LIMITATIONS` in `src/evidence_builder.py` (embedded in every evidence artifact): distribution shift alone does not prove malicious manipulation; thresholds are valid only for the declared reference/embedding/window configuration; diagnostics are evidence for review prioritization, not attribution.
