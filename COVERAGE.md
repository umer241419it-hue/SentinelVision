# SentinelVision — Platform Coverage Statement & Attack-Class Declarations

**Problem Statement (SIH PS 26228):** Trustworthy Computer Vision Integrity Assurance for Data, Models and Inference Outputs in Multi-Contributor Pipelines.

---

## 1. System Capability Matrix

| Assurance Capability | Support Status | Required Access | Primary Detection Method | Evidence Generated |
| :--- | :---: | :--- | :--- | :--- |
| **Label Anomaly Detection** | `PARTIALLY_SUPPORTED` | Dataset images & annotations | Cleanlab confident learning with cross-validated KNN/classifier on embeddings | Out-of-sample predicted probability discrepancy |
| **Systematic Mislabeling** | `PARTIALLY_SUPPORTED` | Dataset annotations & multi-contributor provenance | Provenance aggregator confusion matrix across contributor/batch dimensions | Contributor-specific label confusion rates |
| **Near-Duplicate Flooding** | `PARTIALLY_SUPPORTED` | Dataset images | Pairwise standardized cosine similarity on image embeddings | Similarity cluster indices & pairwise cosine metrics |
| **Out-of-Distribution Insertion** | `PARTIALLY_SUPPORTED` | Dataset images & clean calibration subset | Class-conditional trimmed Mahalanobis distance | Minimum Mahalanobis distance & calibrated threshold |
| **Training Data Trigger Injection** | `PARTIALLY_SUPPORTED` | Dataset images & candidate class labels | Patch residual cross-correlation across candidate images | Residual cross-correlation coefficient & patch mask |
| **Model Trojan & Backdoor Inversion** | `PARTIALLY_SUPPORTED` | White-box model weights (`.pt`) & calibration inputs | Neural Cleanse per-class trigger norm optimization + MAD anomaly index, corroborated by STRIP entropy testing | Inverted trigger mask, MAD anomaly index, STRIP entropy deficit |
| **Model Substitution & Modification** | `SUPPORTED` | Model weights file & registered digest | Cryptographic SHA-256 weight hashing against public key registry | Model digest match/mismatch |
| **Inference Tamper Detection** | `SUPPORTED` | Sealed inference records | Ed25519 digital signature over RFC-8785 canonical JSON of 9 inference fields | Signature validity, content hash match |
| **Inference Replay Detection** | `SUPPORTED` | Sealed records & ledger state | Per-execution 128-bit cryptographic nonces + ledger duplicate evidenceHash guards | Nonce uniqueness & duplicate evidence guard rejection |
| **Distribution Drift Monitoring** | `SUPPORTED` | Reference battery & live window batches | Maximum Mean Discrepancy (MMD) with RBF kernel and permutation test | MMD test statistic, permutation $p$-value, operational diagnostics |
| **Contributor Risk Aggregation** | `PARTIALLY_SUPPORTED` | Multi-contributor provenance metadata | Binomial / hypergeometric concentration tests across contributor tags | Contributor risk ratio & anomaly concentration |
| **Adversarial Evasion Patches** | `UNSUPPORTED` | Live execution inputs | None in current release | None |
| **Model Extraction & Stealing** | `UNSUPPORTED` | Query API telemetry | None in current release | None |

---

## 2. Attack-Class Declarations & Boundary Analysis

### 2.1 Supported Attack Classes

#### `INFERENCE_TAMPERING` (`SUPPORTED`)
- **Mechanism**: The `sealed_predict()` wrapper binds the raw input tensor hash, model weights digest, execution configuration (device, resolution, normalization), per-inference cryptographic nonce, timestamp, and model output summary into an immutable RFC-8785 canonical representation, signed using the `InferenceProvenance` Ed25519 private key.
- **Guarantee**: Any post-execution modification to any of the signed fields breaks the content hash or signature and immediately triggers `signatureStatus: "TAMPERED"` and governance disposition `QUARANTINE`.
- **Limitation**: Protects post-execution non-repudiation; does not inspect or guarantee physical sensor authenticity before tensor ingestion.

#### `MODEL_SUBSTITUTION` & `MODEL_MODIFICATION` (`SUPPORTED`)
- **Mechanism**: Pre-registered model digests (SHA-256) are validated against weights binaries at load time and bound into inference seals.
- **Guarantee**: Bit-level modifications to model weights are detected immediately.

#### `DISTRIBUTION_SHIFT` (`SUPPORTED`)
- **Mechanism**: Computes Maximum Mean Discrepancy (MMD) between a frozen reference battery and rolling live windows using an RBF kernel and reference-calibrated null thresholds.
- **Guarantee**: Detects statistically significant distribution shifts and measures operational factors (brightness, contrast, color).
- **Limitation**: A distribution shift does not prove malicious adversary action; it indicates divergence from the reference distribution and is surfaced as `REVIEW`.

---

### 2.2 Partially Supported Attack Classes

#### `BACKDOOR_BEHAVIOUR` & `TRIGGER_INJECTION` (`PARTIALLY_SUPPORTED`)
- **Mechanism**: Neural Cleanse inverts candidate triggers per class; MAD scores anomaly indices; STRIP corroborates entropy suppression. In training data, trigger residual cross-correlation identifies localized patterns.
- **Limitations**:
  - **Access Boundary**: White-box weights access is required. Black-box trigger inversion is unsupported.
  - **Trigger Style Scope**: Validated exclusively against localized patch-style backdoor triggers (BadNets / StaticTarget). Blended, invisible, WaNet-style, or physical-world dynamic perturbations are unsupported.
  - **Dependent Corroboration**: STRIP only corroborates classes that Neural Cleanse + MAD flags; it does not operate as an independent whole-model scanner.

#### `LABEL_FLIPPING` & `SYSTEMATIC_MISLABELING` (`PARTIALLY_SUPPORTED`)
- **Mechanism**: Cleanlab confident learning identifies out-of-sample label inconsistencies in feature embedding space; provenance aggregators test contributor-level mislabeling concentrations.
- **Limitations**:
  - Accuracy depends on auxiliary classifier performance.
  - Label errors that are semantically identical in feature space evade detection.

#### `DUPLICATE_FLOODING` (`PARTIALLY_SUPPORTED`)
- **Mechanism**: Pairwise standardized cosine similarity on frozen embeddings identifies near-duplicates.
- **Limitations**: Catches compression, cropping, and color jitter; does not identify distinct photographs taken from different angles of the same physical object.

#### `OUT_OF_DISTRIBUTION_INSERTION` (`PARTIALLY_SUPPORTED`)
- **Mechanism**: Class-conditional trimmed Mahalanobis distance against robustly calibrated covariance matrices.
- **Limitations**: If the training pool itself is heavily poisoned (>25%), calibration degrades.

---

### 2.3 Unsupported Attack Classes

#### `ADVERSARIAL_EVASION_PATCH` (`UNSUPPORTED`)
- Test-time adversarial perturbation patches (e.g. AdvPatch, optical illusions) designed to cause misclassification during benign inference are not detected by current static/drift modules.

#### `MODEL_EXTRACTION_STEALING` (`UNSUPPORTED`)
- High-volume querying attacks attempting to steal model intellectual property through API queries are outside the scope of the offline assurance pipeline.

---

## 3. Remaining Gaps Towards Problem Statement PS 26228

To achieve full operational maturity across all aspects of PS 26228, the following components remain to be addressed in future phases:
1. **Black-Box / Grey-Box Trojan Detection**: Inverting triggers when only API query access or logits are accessible without PyTorch weights.
2. **Dynamic / Non-Patch Backdoors**: Extending detection to frequency-domain, blended, and sample-specific backdoors (WaNet, clean-label backdoors).
3. **Hardware / Sensory Hardware Provenance**: Cryptographic camera/sensor attestation (e.g. TPM/Secure Enclave hardware signing) to secure data capture prior to tensor ingestion.
4. **Online Multi-Peer Endorsement Bridging**: Production deployment with live Hyperledger Fabric Raft orderers and multi-organization peers for decentralized finding anchoring.
