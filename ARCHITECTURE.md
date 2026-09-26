# SentinelVision — Architecture & Governance Layer Specification

**Problem Statement (SIH PS 26228):** Trustworthy Computer Vision Integrity Assurance for Data, Models and Inference Outputs in Multi-Contributor Pipelines.

---

## 1. High-Level Architecture Overview

SentinelVision provides end-to-end evidence-based integrity assurance across the computer vision lifecycle: training datasets, model weights, live execution inferences, and real-world distribution drift.

The **Governance & Assurance Reporting Layer** unifies these disparate verification modules into a coherent, verifiable, and tamper-evident pipeline:

```text
                                  ┌──────────────────────────────┐
                                  │      Assessment Request      │
                                  │  (CLI / Scheduled / Pipeline)│
                                  └──────────────┬───────────────┘
                                                 │
                   ┌─────────────────────────────┼────────────────────────────┐
                   │                             │                            │
                   ▼                             ▼                            ▼
        ┌──────────────────────┐      ┌──────────────────────┐     ┌──────────────────────┐
        │    Data Integrity    │      │   Model Integrity    │     │ Inference Provenance │
        │                      │      │                      │     │                      │
        │ • Cosine Duplicates  │      │ • Neural Cleanse Inv │     │ • sealed_predict()   │
        │ • Trimmed Mahalanobis│      │ • MAD Anomaly Scorer │     │ • RFC-8785 Hashing   │
        │ • Cleanlab Confident │      │ • STRIP Entropy Test │     │ • Ed25519 Signatures │
        │ • Trigger Residuals  │      │ • White-Box Checks   │     │ • Nonce Replay Guard │
        └──────────┬───────────┘      └──────────┬───────────┘     └──────────┬───────────┘
                   │                             │                            │
                   └─────────────────────────────┼────────────────────────────┘
                                                 │
                                                 ▼
                                      ┌──────────────────────┐
                                      │   Drift Monitoring   │
                                      │                      │
                                      │ • MMD (RBF Kernel)   │
                                      │ • Reference Battery  │
                                      │ • Permutation Tests  │
                                      │ • Rolling Windows    │
                                      └──────────┬───────────┘
                                                 │
                                                 ▼
                               ┌────────────────────────────────────┐
                               │         Governance Engine          │
                               │                                    │
                               │ • Asset Registration & Inventory   │
                               │ • Finding & Evidence Normalization │
                               │ • Decoupled Confidence & Severity  │
                               │ • Coverage & Attack-Class Matrix   │
                               │ • Deterministic Overall Assessment │
                               │ • Actionable Recommendations       │
                               │ • Tamper-Evident SHA-256 Hash Chain│
                               └─────────────────┬──────────────────┘
                                                 │
                               ┌─────────────────┴──────────────────┐
                               │                                    │
                               ▼                                    ▼
                ┌──────────────────────────────┐     ┌──────────────────────────────┐
                │   Machine-Readable Report    │     │    Analyst-Readable Report   │
                │    assurance_report.json     │     │     assurance_report.html    │
                │  (Ed25519 Signed Digest)     │     │     assurance_report.md      │
                └──────────────────────────────┘     └──────────────────────────────┘
```

---

## 2. Core Governance Modules

### 2.1 Central Governance Engine (`governance.engine.GovernanceEngine`)
- **Role**: Coordinates the assessment lifecycle.
- **Functions**:
  - Registers evaluated assets (`datasets`, `models`, `inference_records`, `reference_batteries`).
  - Records operational assumptions and access profiles (`WHITE_BOX`, `SEALED_RECORDS`, `REFERENCE_BATTERY`).
  - Executes or ingests findings from each underlying integrity module.
  - Normalizes heterogeneous module findings into canonical structures (`governance.schema.CanonicalFinding`).
  - Aggregates overall pipeline disposition deterministically.
  - Manages the SHA-256 chained audit trail (`governance.audit.AuditTrail`).

### 2.2 Canonical Finding Normalization (`governance.findings`)
Translates native module representations into the 16-attribute canonical finding model:
- Decouples raw detection metrics from automated assessment.
- Retains cryptographic bindings: `evidenceHash` points to persisted JSON in `<module>/evidence_store/<hash>.json`.
- Maps module confidences into transparent interpretations (`HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`) accompanied by clear rationale and documented limitations.

### 2.3 Transparent Confidence & Severity Model (`governance.confidence`)
- **Principle**: Confidence is never an opaque score. Every finding documents:
  - `value`: Numerical float $[0.0, 1.0]$ or `"UNKNOWN"`.
  - `interpretation`: Categorical descriptor (`HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`).
  - `basis`: Exhaustive bulleted list of supporting evidence indicators.
  - `threshold`: Applied decision boundary.
  - `limitations`: Context-specific caveats.

### 2.4 Governance Disposition Engine (`governance.disposition`)
Generates actionable analyst recommendations mapped strictly to evidence:
- **`ACCEPT`**: Check passed cleanly without material anomaly or cryptographic violation.
- **`REVIEW`**: Statistical anomalies, distribution shifts, or uncorroborated detections requiring human inspection.
- **`QUARANTINE`**: Cryptographic binding failure, payload tampering, model substitution, or corroborated high-confidence trojan backdoors.

### 2.5 Tamper-Evident Audit Trail (`governance.audit`)
Maintains a sequential cryptographic hash chain across the assessment:
- Each event includes `event_id`, `sequence_index`, `timestamp`, `event_type`, `actor`, `reference_ids`, `data`, `previous_event_hash`, and `event_hash`.
- `event_hash = sha256(canonical_json(event_payload_without_event_hash))`.
- Genesis event binds to $64$ zeros (`0000...0000`).
- Any insertion, deletion, reordering, or modification of historical events breaks the chain and is detected instantly.

### 2.6 Report Generation & Cryptographic Non-Repudiation (`governance.report`, `governance.verifier`)
- Compiles `assurance_report.json`, `assurance_report.md`, and `assurance_report.html`.
- Signs the canonical report digest using Ed25519 with the `GovernanceEngine` private key registered in `crypto-utils/public_key_registry.json`.
- Provides standalone verification via `cv-assurance verify-report` and `cv-assurance verify-audit`.

---

## 3. Module Integration Interfaces

| Module | Native Source File | Governance Normalizer | Core Cryptographic Primitives |
| :--- | :--- | :--- | :--- |
| **Data Integrity** | `data-integrity/results/integrity_results.json` | `normalize_data_integrity_finding` | SHA-256 evidence hash, Ed25519 finding signature (`DataIntegrity`) |
| **Model Integrity** | `model-integrity/findings.json` | `normalize_model_integrity_finding` | SHA-256 model weights digest, Ed25519 finding signature (`ModelIntegrity`) |
| **Inference Provenance** | `inference-provenance/evidence_store/*.json` | `normalize_inference_seal_finding` | RFC-8785 canonical hash, Ed25519 seal signature (`InferenceProvenance`), 128-bit nonce |
| **Drift Monitoring** | `drift-monitor/results/drift_results.json` | `normalize_drift_finding` | Reference manifest SHA-256 digest, Ed25519 finding signature (`DistributionShift`) |
| **Governance Engine** | `governance/schema.py` | Central Aggregator | SHA-256 audit chaining, Ed25519 report signature (`GovernanceEngine`) |

---

## 4. Air-Gapped & Offline Guarantee

The Governance & Assurance Reporting Layer is designed from the ground up for air-gapped deployment:
- **Zero Remote Dependencies**: No cloud APIs, no external telemetry, no remote package downloads.
- **Local Key Material**: Private keys reside locally in `crypto-utils/keys/` (file mode `0600`).
- **Self-Contained Rendering**: HTML reports contain inline self-contained styles without relying on external CDN fonts or scripts.
- **Deterministic Hashing**: All serialization leverages RFC-8785 / deterministic key-sorted JSON serializers (`canonical_json`).
