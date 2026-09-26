# SentinelVision — Governance & Assurance Operations Guide

**Trustworthy Computer Vision Integrity Assurance for Data, Models and Inference Outputs in Multi-Contributor Pipelines**

---

## 1. Governance Principles & Philosophy

The SentinelVision Governance Layer is an **evidence-based assurance aggregator**, not a generic vulnerability scanner or opaque risk dashboard.

### Core Tenets:
1. **Evidence Precedes Assessment**: An anomaly flag is never presented without stable references to empirical metrics (cosine similarities, Mahalanobis distances, MMD test statistics, or cryptographic digests).
2. **Decoupled Evaluation**: Detection signals are strictly separated from automated confidence, severity, and analyst disposition.
3. **No Presumption of Malice**: Statistical distribution shifts, label inconsistencies, or near-duplicates are flagged as anomalies requiring human review, not as conclusive proof of an adversary.
4. **Honest Coverage Boundaries**: Capabilities with known limitations (e.g. white-box trigger inversion limited to patch triggers) are explicitly declared as `PARTIALLY_SUPPORTED`. Unassessed assets are tagged as `NOT_ASSESSED` and can never silently pass.
5. **Tamper-Evident Non-Repudiation**: Assessments are bound by sequential SHA-256 audit chaining and signed with Ed25519 digital signatures.

---

## 2. The 10 Governance Invariants

Every SentinelVision Assurance Report directly answers the 10 core governance questions:

| # | Invariant Question | Governance Answer Mechanism |
| :---: | :--- | :--- |
| **1** | **What assets were assessed?** | `assets` inventory cataloging datasets, model weights, inference seals, and reference batteries with hashes. |
| **2** | **What checks were performed?** | `checks` table recording each check's module, execution timestamp, parameters, and status (`COMPLETED` or `NOT_ASSESSED`). |
| **3** | **What findings were generated?** | `findings` list adhering to the canonical 16-attribute schema. |
| **4** | **What evidence supports each finding?** | `evidence` list with typed references: model digest, input tensor hash, MMD $p$-value, or `evidenceHash`. |
| **5** | **How confident is the system?** | `confidence` block detailing categorical level (`HIGH`/`MEDIUM`/`LOW`), numerical score, empirical basis, and limitations. |
| **6** | **What are known limitations & access assumptions?** | `access_profile` (`WHITE_BOX`, `SEALED_RECORDS`) and finding-specific `limitations`. |
| **7** | **Which attack classes are covered?** | `coverage.attack_classes` with declared `SUPPORTED` and `PARTIALLY_SUPPORTED` mappings. |
| **8** | **Which attack classes are NOT covered?** | Explicit declarations of `UNSUPPORTED` threat vectors (e.g. physical evasion patches, model stealing). |
| **9** | **What should an analyst do next?** | `recommendation` specifying disposition (`ACCEPT`, `REVIEW`, `QUARANTINE`) and step-by-step guidance. |
| **10** | **Can another analyst reproduce / audit the assessment?** | `reproducibility` configuration metadata and verifiable sequential `audit` hash chain. |

---

## 3. Governance Dispositions

| Disposition | Operational Criteria | Mandatory Action |
| :--- | :--- | :--- |
| **`ACCEPT`** | All executed checks completed with status `PASS`. No cryptographic mismatches, no statistical anomalies exceeding calibrated thresholds. | Cleared for automated deployment within declared operational envelope. |
| **`REVIEW`** | Statistical anomalies detected (e.g. operational lighting shift, near-duplicate concentration, uncorroborated backdoor flag), or checks marked `NOT_ASSESSED`. | Hold deployment. Domain analyst must inspect evidence and provenance before clearing asset. |
| **`QUARANTINE`** | Integrity failure (`FAIL`), cryptographic seal invalid, model digest substitution, or high-confidence corroborated backdoor trojan. | Immediate isolation of asset. Block inference consumption and trigger forensic audit. |

---

## 4. Analyst Drill-Down Workflow

When inspecting a finding, the analyst should follow this standard operating procedure:

```text
1. Inspect Status & Severity
   ├── CRITICAL / FAIL ────► Immediate Quarantine Protocol
   ├── MEDIUM / REVIEW ───► Anomaly Investigation Protocol
   └── PASS ──────────────► Cleared
          │
2. Review Supporting Evidence
   ├── Check raw metrics: Mahalanobis distance, MMD statistic, p-value
   └── Verify cryptographic hashes: inputHash, modelDigest, signature
          │
3. Check Access Assumptions & Limitations
   ├── Was access white-box or black-box?
   └── Are triggers limited to localized patch perturbations?
          │
4. Review Suggested Analyst Action
   └── Execute recommended action (e.g., inspect contributor batch)
```

---

## 5. Independent Audit & Verification

An external auditor can verify any generated assurance report offline:

```bash
# 1. Verify report content integrity and Ed25519 signature
./cv-assurance verify-report --report reports/assurance_report.json

# 2. Verify chronological hash chain of assessment audit trail
./cv-assurance verify-audit --report reports/assurance_report.json
```

Output:
```text
Verification Verdict: VALID
Content Hash Valid:   True
Signature Valid:      True
Audit Chain Valid:    True
Chained Events:       9
[SUCCESS] Report is authentic and untampered.
```
