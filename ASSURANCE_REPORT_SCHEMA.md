# SentinelVision — Canonical Assurance Report Schema Specification

**Schema Version:** `1.0.0`  
**Standard:** SentinelVision Extensible Governance Specification

---

## 1. Top-Level Schema Overview

```json
{
  "schema_version": "1.0.0",
  "assessment_id": "asmt-YYYYMMDD-HHMMSS-xxxxxx",
  "assessment_timestamp": "ISO-8601 UTC timestamp",
  "system": { ... },
  "assets": { ... },
  "access_profile": { ... },
  "checks": [ ... ],
  "findings": [ ... ],
  "overall_assessment": { ... },
  "coverage": { ... },
  "limitations": [ ... ],
  "recommendations": [ ... ],
  "audit": { ... },
  "reproducibility": { ... },
  "report_integrity": { ... }
}
```

---

## 2. Field Specifications

### 2.1 System Metadata (`system`)
- `name` (string): System identifier (e.g. `"SentinelVision"`).
- `version` (string): Core system release version.
- `governance_engine_version` (string): Version of the governance layer.
- `environment` (string): Operational environment (e.g. `"offline/air-gapped"`).
- `node_platform` (string): Host identifier.

### 2.2 Asset Inventory (`assets`)
- `datasets` (array of objects): Catalog of datasets assessed, including `asset_id`, `name`, `sample_count`, and archive hashes (`md5`, `sha1`, `sha256`).
- `models` (array of objects): Catalog of model binaries assessed, including `asset_id`, `architecture`, `digest`, and `access_level`.
- `inference_records` (array of objects): Catalog of inference seals verified, including `seal_id`, `model_asset_id`, `model_digest`, and `input_hash`.
- `reference_batteries` (array of objects): Reference distributions used for distribution-shift checks.

### 2.3 Access Profile (`access_profile`)
- `data_access` (string): Access mode for data (`"LOCAL_FILESYSTEM"`).
- `model_access` (string): Access level for model inspection (`"white-box"`, `"grey-box"`, `"black-box"`).
- `inference_access` (string): Access level for inference verification (`"SEALED_RECORDS"`).
- `drift_access` (string): Access level for drift monitoring (`"REFERENCE_BATTERY_AND_WINDOWS"`).
- `metadata_available` (array of strings): Metadata provided (`"provenance"`, `"calibration"`, etc.).

### 2.4 Checks (`checks`)
Array of check records executed or recorded:
- `check_id` (string): Unique identifier (e.g. `"chk-di-a1b2c3"`).
- `category` (enum): Check category (`"DATA_INTEGRITY"`, `"MODEL_INTEGRITY"`, `"INFERENCE_PROVENANCE"`, `"DISTRIBUTION_SHIFT"`, `"AUDIT"`, `"CONFIGURATION"`, `"COVERAGE"`).
- `name` (string): Descriptive check name.
- `module` (string): Executing module name.
- `description` (string): Operational purpose of check.
- `execution_status` (string): `"COMPLETED"`, `"FAILED"`, `"SKIPPED"`, or `"NOT_ASSESSED"`.
- `timestamp` (string): Execution timestamp.
- `parameters` (object): Execution parameters and configurations.
- `findings_generated` (array of strings): IDs of findings produced by this check.

### 2.5 Canonical Findings (`findings`)
Each finding represents an observed condition or assessed asset:
```json
{
  "finding_id": "find-inf-7b2e1a49f802",
  "category": "INFERENCE_PROVENANCE",
  "asset_id": "seal-demo-valid-001",
  "status": "PASS",
  "severity": "LOW",
  "confidence": {
    "value": 1.0,
    "interpretation": "HIGH",
    "basis": [
      "Cryptographic RFC-8785 canonical hash verified.",
      "Ed25519 signature validated against InferenceProvenance public key registry.",
      "Model weights digest confirmed."
    ],
    "threshold": null,
    "limitations": [
      "Execution authenticity guaranteed; pre-inference sensory pedigree unverified."
    ]
  },
  "title": "Inference Output Authenticity Verified: seal-demo-valid-001",
  "description": "Cryptographic seal seal-demo-valid-001 verified. Model digest, input tensor hash, config, and output binding are authentic.",
  "evidence": [
    {
      "type": "sealed_inference_record",
      "reference": "seal-demo-valid-001",
      "description": "Cryptographic sealed inference output",
      "details": {
        "modelAssetID": "model-id-00000028",
        "inputHash": "f0252f29c40ffb13c7b4b8985d4b2b960f10d0755680249beb3ac33ea711c237",
        "modelDigest": "cd88076498c5c79fce68bffef38102f3394ef5c9f6691dc2f0efc48bf51f3e0b"
      }
    }
  ],
  "affected_scope": "Inference Seal seal-demo-valid-001 (Model model-id-00000028)",
  "detection_method": "InferenceProvenance (Ed25519 / RFC-8785 Canonical JSON / SHA-256)",
  "access_assumptions": "Sealed inference JSON records with registered public key",
  "recommendation": {
    "disposition": "ACCEPT",
    "reason": "Inference seal is cryptographically valid and authentic.",
    "suggested_action": "Inference result cleared for downstream automated consumption.",
    "priority": "ROUTINE"
  },
  "limitations": [
    "Guarantees post-execution non-repudiation; does not inspect input image acquisition sensor."
  ],
  "timestamp": "2026-09-22T11:19:10Z",
  "module_name": "InferenceProvenance",
  "evidence_hash": "6a9b0f11cab8afc2ffa14c3013a04d714c2a25ae183546ab661ade5da0a2815d",
  "signature": "66bd97c54476164088a8a2301bef0955548bc023cb4187a57aab0ad6ab11e37c185e87c2d834605ddaf08d5e69b6b0e19ea8069c86e2fd3bab2c5260e95a6204"
}
```

### 2.6 Overall Assessment (`overall_assessment`)
- `overall_status` (string): `"PASS"`, `"PASS_WITH_LIMITATIONS"`, `"REVIEW"`, `"FAIL"`, `"NOT_ASSESSED"`.
- `disposition` (string): `"ACCEPT"`, `"REVIEW"`, `"QUARANTINE"`.
- `summary` (string): Executive narrative summary.
- `critical_findings` (integer): Count of critical findings.
- `warning_findings` (integer): Count of warnings.
- `review_findings` (integer): Count of review-level findings.
- `pass_findings` (integer): Count of passed checks.
- `not_assessed` (integer): Count of unassessed checks.
- `basis` (array of strings): Deterministic criteria justifying the disposition.

### 2.7 Tamper-Evident Report Integrity (`report_integrity`)
- `report_hash` (string): SHA-256 digest of RFC-8785 canonical JSON of the entire report excluding `report_integrity`.
- `signature` (string): 128-hex character Ed25519 digital signature over `report_hash`.
- `signer` (string): Module identity key (`"GovernanceEngine"`).
- `algorithm` (string): `"Ed25519+SHA256"`.
- `signed_at` (string): ISO-8601 UTC timestamp.
