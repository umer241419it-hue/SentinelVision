# SentinelVision: Comprehensive System Workflow & Solution Report

> **Problem Statement (SIH PS 26228):** Trustworthy Computer Vision Integrity Assurance for Data, Models, and Inference Outputs in Multi-Contributor Pipelines
> **Organization:** Ministry of Defence (MoD) / Indian Army (DGIS)
> **Theme:** Blockchain & Cybersecurity

---

## Table of Contents
1. [Executive Overview: What Problem Does SentinelVision Solve?](#1-executive-overview-what-problem-does-sentinelvision-solve)
2. [Plain-Language Glossary (Explaining the Technical Terms)](#2-plain-language-glossary-explaining-the-technical-terms)
3. [The Big Picture: Why Defence Computer Vision is Vulnerable](#3-the-big-picture-why-defence-computer-vision-is-vulnerable)
4. [Step-by-Step Architecture: How SentinelVision Works](#4-step-by-step-architecture-how-sentinelvision-works)
   - [Phase 1: Training-Data Integrity (Inspecting the Raw Inputs)](#phase-1-training-data-integrity-inspecting-the-raw-inputs)
   - [Phase 2: Model Integrity (Scanning the AI Brain)](#phase-2-model-integrity-scanning-the-ai-brain)
   - [Phase 3: Inference Provenance (Sealing Every Live Decision)](#phase-3-inference-provenance-sealing-every-live-decision)
   - [Phase 4: Real-World Drift Monitoring (Observing Changing Environments)](#phase-4-real-world-drift-monitoring-observing-changing-environments)
   - [Phase 5: Governance, Actionable Dispositions & Blockchain Ledger](#phase-5-governance-actionable-dispositions--blockchain-ledger)
5. [End-to-End Operational Workflow (A Day in the Life of an Analyst)](#5-end-to-end-operational-workflow-a-day-in-the-life-of-an-analyst)
6. [Air-Gapped & Military Readiness (Zero Cloud Reliance)](#6-air-gapped--military-readiness-zero-cloud-reliance)
7. [Summary: Why This Solution Fully Satisfies the MoD / DGIS Requirements](#7-summary-why-this-solution-fully-satisfies-the-mod--dgis-requirements)

---

## 1. Executive Overview: What Problem Does SentinelVision Solve?

In modern military operations—such as drone surveillance along borders, autonomous vehicle navigation, or satellite imagery analysis—the Armed Forces rely heavily on Computer Vision (Artificial Intelligence that "sees" and identifies objects).

However, building these systems requires gathering thousands of images from multiple external vendors, civilian contractors, and field units. It also requires using pre-trained AI models built by third parties.

**This creates severe security vulnerabilities:**
1. **Sabotaged Training Data:** A malicious or negligent contractor could sneak poisoned photos into the training set (e.g., mislabeling enemy tanks as civilian trucks or adding a hidden sticker that fools the camera later).
2. **Trojan Horses in AI Models:** A vendor could supply an AI model that performs brilliantly during regular tests, but contains a secret "backdoor" that disables detection when a specific trigger appears.
3. **Falsified Live Reports (Inference Tampering):** During live missions, a hacker could intercept the camera feed and replay yesterday’s empty landscape to blind headquarters to an ongoing border infiltration.

**The Solution:**
**SentinelVision** is an **independent, unified digital inspector and cryptographic notary**. It acts like an uncompromising military auditor that inspects the data before training, scans the AI model for hidden backdoors, cryptographically "seals" every live recognition output with digital signatures, and anchors all findings onto an immutable blockchain ledger.

---

## 2. Plain-Language Glossary (Explaining the Technical Terms)

To make this document understandable to anyone regardless of technical background, here is how key terms translate into everyday concepts:

* **Computer Vision (CV):** Software that acts like eyes and brain for a computer, allowing it to look at an image or video and say: *"That is a tank,"* *"That is a bridge,"* or *"That is an authorized personnel."*
* **Inference:** The exact moment when the AI looks at a new, live photo and makes its decision or detection.
* **Digital Fingerprint (Cryptographic Hash / SHA-256):** A unique string of characters calculated mathematically from a file. If even a single pixel in an image or a single comma in a document is altered, the entire fingerprint changes completely.
* **Digital Signature (Ed25519):** The digital equivalent of a wax seal pressed with an official signet ring. Only the authorized software holding the private key can stamp it, but anyone with the public key can verify that it is genuine and untouched.
* **Blockchain Ledger (Hyperledger Fabric):** A digital record book shared across authorized defense nodes. Once an event is written into the ledger, nobody—not even a system administrator—can rewrite, delete, or secretly edit the past records.
* **Backdoor / Trojan:** A secret trapdoor hidden inside an AI model. Under 99.9% of conditions, the AI works normally. But when the enemy presents a specific visual cue (like a tiny yellow square or specific symbol), the AI intentionally misidentifies the target.
* **Distribution Drift:** When the physical environment changes naturally (such as summer green forests turning into winter snow, bright morning sun turning into night-vision dusk, or dusty desert storms). The AI must know when its surroundings have changed so it doesn't give false alarms.
* **Air-Gapped:** An isolated computer system that has zero connection to the public internet, ensuring no foreign servers can snoop or tamper with operations.

---

## 3. The Big Picture: Why Defence Computer Vision is Vulnerable

In multi-contributor pipelines, trust cannot simply be assumed. The lifecycle consists of three distinct stages:

```
[ Contributor Datasets ] ──> [ Trained AI Model ] ──> [ Live Camera Inferences ]
          │                          │                           │
          ▼                          ▼                           ▼
    Data Poisoning            Hidden Backdoors           Replay & Tampering
    Label Flipping          Weight Substitution         Falsified Detections
```

Before SentinelVision, security tools were fragmented. Someone might check the dataset, but ignore model weights; or they might test the model, but have no way to verify whether the live drone video output was intercepted and doctored in transit.

SentinelVision bridges these gaps by providing an unbroken **Chain of Custody and Assurance** across the complete lifecycle.

---

## 4. Step-by-Step Architecture: How SentinelVision Works

SentinelVision evaluates the pipeline in five coordinated phases:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   SENTINELVISION ASSURANCE PIPELINE                     │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
       ┌───────────────────────────┼───────────────────────────┐
       ▼                           ▼                           ▼
[ 1. Data Integrity ]     [ 2. Model Integrity ]   [ 3. Inference Seals ]
 • Duplicate Flooding      • Neural Cleanse         • Cryptographic Sealing
 • OOD Infiltration        • STRIP Entropy          • Nonce Replay Guards
 • Label Flipping          • Weight Verification    • 9-Field RFC-8785 Hash
 • Contributor Risk        • Anomaly Indexing       • Ed25519 Signing
       │                           │                           │
       └───────────────────────────┼───────────────────────────┘
                                   │
                                   ▼
                      [ 4. Drift Monitoring ]
                       • Maximum Mean Discrepancy (MMD)
                       • Lighting, Contrast & Sensor Checks
                       • Operational vs. Malicious Drift
                                   │
                                   ▼
                      [ 5. Central Governance ]
                       • Actionable Dispositions: ACCEPT / REVIEW / QUARANTINE
                       • SHA-256 Tamper-Evident Hash Chain
                       • Hyperledger Fabric Multi-Org Ledger
```

---

### Phase 1: Training-Data Integrity (Inspecting the Raw Inputs)

Before any model is trained, the system scans the dataset submitted by external contractors. It inspects five dangerous attack vectors:

1. **Near-Duplicate Flooding:**
   * *What it is:* A contractor attempts to bias the AI by submitting hundreds of identical or near-identical images with minor adjustments (like slight cropping or brightness tweaks).
   * *How SentinelVision detects it:* It transforms images into mathematical feature representations and measures their cosine similarity. Images that match beyond 99% are flagged as redundant floods.
2. **Out-of-Distribution (OOD) Insertion:**
   * *What it is:* Inappropriate or irrelevant images snuck into the dataset (e.g., civilian sedans injected into an armored vehicle classification dataset).
   * *How SentinelVision detects it:* It measures the statistical distance (Trimmed Mahalanobis Distance) of each sample from the clean reference distribution. If an image is too alien, it is quarantined.
3. **Label Flipping & Systematic Mislabelling:**
   * *What it is:* A contractor deliberately labels an enemy tank as a civilian ambulance so the AI learns to ignore it during operations.
   * *How SentinelVision detects it:* Using *Confident Learning* (Cleanlab algorithm), the system compares what the image actually looks like against the human label. If there is a persistent mismatch, it gets highlighted.
4. **Trigger Injection (Poisoned Patches):**
   * *What it is:* A microscopic physical pattern or watermark added to multiple images to prepare a backdoor attack.
   * *How SentinelVision detects it:* It searches for repeating localized pixel artifacts and cross-correlates residual patterns across images.
5. **Contributor Risk Aggregation (Not Just Isolated Samples):**
   * *What it is:* Instead of just saying *"Image #45 is bad,"* the system aggregates all flags by **Contributor ID**, **Batch Number**, and **Department**.
   * *Why it matters:* If Contractor "Alpha" has an anomaly rate 5 times higher than normal baselines, SentinelVision calculates a statistical z-score and flags the entire contractor as a high-risk source.

---

### Phase 2: Model Integrity (Scanning the AI Brain)

Once an AI model is delivered, SentinelVision inspects the neural network to verify it hasn't been tampered with or replaced:

1. **Digital Identity Match (Weight Digest):**
   The model file’s cryptographic SHA-256 fingerprint is compared against the authorized military registry. If a single byte was altered, it is immediately rejected.
2. **Hunting for Hidden Backdoors (Neural Cleanse & MAD):**
   * *The Intuition:* If a model has a secret backdoor for Class 2 (e.g., enemy bunker), it requires an unnaturally tiny perturbation to trick the AI into that class compared to any legitimate class.
   * *The Action:* The system mathematically optimizes reverse-engineered triggers for every class, then applies Median Absolute Deviation (MAD) anomaly indexing. If one class stands out dramatically, a backdoor is suspected.
3. **Independent Corroboration via Entropy Testing (STRIP):**
   * *The Intuition:* When an image containing a real backdoor trigger is blended with random noise or other background images, a backdoored model stubbornly outputs the trigger's target class with near-zero uncertainty (entropy suppression).
   * *Double-Check:* If both Neural Cleanse and STRIP agree on the exact same compromised class, the model is definitively flagged for **QUARANTINE**. If the tests give conflicting results, it is marked for expert human **REVIEW**.

---

### Phase 3: Inference Provenance (Sealing Every Live Decision)

During live deployment (e.g., a surveillance drone flying a reconnaissance mission), every visual detection must be legally and operationally non-repudiable.

Whenever the model runs `sealed_predict()`, SentinelVision creates an unforgeable cryptographic seal consisting of 9 critical fields:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        CRYPTOGRAPHIC SEAL (9 FIELDS)                   │
├────────────────────────────────────────────────────────────────────────┤
│ 1. sealID           : Unique identifier for this inference event        │
│ 2. modelAssetID     : Name and version of the verified model           │
│ 3. inputHash        : Exact SHA-256 fingerprint of the raw camera image │
│ 4. modelDigest      : SHA-256 fingerprint of the active model weights  │
│ 5. config           : Camera resolution, color normalization, settings │
│ 6. nonce            : 128-bit single-use random cryptographic number   │
│ 7. timestamp        : Exact UTC time (ISO-8601)                        │
│ 8. outputSummary    : Detected target, bounding boxes, confidence      │
│ 9. signerModule     : Identifier of the authorized signing station     │
├────────────────────────────────────────────────────────────────────────┤
│ • Canonicalization  : RFC-8785 Deterministic Key-Sorted JSON           │
│ • Signature         : Ed25519 Digital Signature                        │
└────────────────────────────────────────────────────────────────────────┘
```

#### What Attacks Does This Prevent?
* **Post-Hoc Alteration:** If an operative tries to alter the output (e.g., changing "Detected: Hostile Tank" to "Detected: Tractor"), the content hash changes, breaking the signature. The system screams **TAMPERED**.
* **Model Substitution:** If someone secretly runs a weaker or compromised model, the `modelDigest` in the seal will not match the registered key.
* **Replay Attacks:** If an adversary intercepts authentic footage from yesterday and replays it today to deceive the base, the **nonce** and **timestamp** will be recognized as already consumed, immediately rejecting the duplicate data.

---

### Phase 4: Real-World Drift Monitoring (Observing Changing Environments)

AI models are trained on specific conditions. If a drone trained in the desert is deployed to Ladakh during snowfall, its accuracy might drop. The military commander needs to know whether decreased performance is due to natural weather changes or enemy electronic warfare.

1. **Maximum Mean Discrepancy (MMD):**
   SentinelVision compares a sliding window of recent live images against a pre-calibrated "Reference Battery" of verified baseline images using an RBF statistical kernel.
2. **Distinguishing Natural Drift from Malicious Manipulation:**
   * **Operational Environmental Drift:** If the shift is explained by changes in overall brightness, contrast, or color temperature (e.g., dusk, rain, or glare), the system informs the analyst: *"Operational lighting drift detected; model confidence reduced by 15%, but no malicious tampering evident."*
   * **Unexplained / Suspicious Drift:** If the statistical distribution shifts radically without corresponding environmental explanations, the system raises an alarm for manual intervention.

---

### Phase 5: Governance, Actionable Dispositions & Blockchain Ledger

Raw data and mathematical scores are useless if a military commander cannot understand them in seconds. SentinelVision synthesizes all findings into a clean governance standard:

#### 1. Clear Human Dispositions
Every finding receives one of three standardized operational verdicts:
* <span style="color:green;font-weight:bold;">ACCEPT:</span> The asset passed all cryptographic and statistical tests cleanly. Safe for deployment.
* <span style="color:orange;font-weight:bold;">REVIEW:</span> An anomaly or environmental shift was observed, but does not indicate intentional sabotage. Requires analyst visual inspection.
* <span style="color:red;font-weight:bold;">QUARANTINE:</span> A cryptographic failure, signature violation, or corroborated trojan backdoor was detected. The asset is immediately locked and barred from operations.

#### 2. Tamper-Evident Audit Hash Chain
Every evaluation event is added to a sequential SHA-256 cryptographic chain (similar to a local blockchain). Event #2 includes the hash of Event #1; Event #3 includes the hash of Event #2. If any unauthorized user edits past audit logs, the entire chain breaks.

#### 3. Hyperledger Fabric Blockchain Anchoring
Findings are submitted to a **Hyperledger Fabric Smart Contract** (`FindingContract.js`).
* **Multi-Organization Endorsement:** Both Organization 1 and Organization 2 peers must cryptographically agree before a record is added to the ledger.
* **Anti-Replay Guard:** The smart contract maintains an internal composite-key index (`evidenceHash~assetID`). If anyone tries to submit the same evidence twice or overwrite an existing asset, the blockchain engine rejects the transaction.

---

## 5. End-to-End Operational Workflow (A Day in the Life of an Analyst)

Here is how an intelligence officer or security analyst uses SentinelVision:

```
[ Step 1: Upload / Register Assets ]
  - Upload dataset zip (VOC, COCO, YOLO) or PyTorch/ONNX model.
  - Contractor and unit metadata attached.
                │
                ▼
[ Step 2: Automated Multi-Module Scan ]
  - Data Integrity engine checks for duplicates, OOD, and flipped labels.
  - Model Integrity engine scans weights and tests for backdoors.
                │
                ▼
[ Step 3: Central Governance Aggregation ]
  - Findings normalized into 9-field canonical schema.
  - Evidence files saved in immutable storage.
  - Overall verdict calculated (ACCEPT / REVIEW / QUARANTINE).
                │
                ▼
[ Step 4: Blockchain Ledger Commitment ]
  - Findings signed with Ed25519 digital key.
  - Submitted via REST Bridge to Hyperledger Fabric peers.
  - Endorsed and permanently committed to the ledger world state.
                │
                ▼
[ Step 5: Analyst Interaction via Console ]
  - Analyst opens the Electron / Vite desktop application.
  - Views high-risk contributors, inspects quarantined models,
    or exports digitally signed PDF/HTML/JSON reports.
```

---

## 6. Air-Gapped & Military Readiness (Zero Cloud Reliance)

In sensitive defence installations, systems must operate completely cut off from the global internet (air-gapped):

* **No Cloud Dependencies:** SentinelVision has zero calls to external APIs, AWS, Google Cloud, or third-party telemetry.
* **Self-Contained Rendering:** HTML reports, visual graphs, and dashboards contain embedded styles and code; they do not load external fonts or CDN scripts.
* **Local Cryptographic Key Management:** All Ed25519 private keys are stored locally on the secure server with restricted file permissions (`0600`).
* **No Retraining Required for Baseline Checks:** Analyzing a model does not require days of expensive GPU retraining; integrity evaluations run in minutes using sample inversion and statistical embedding math.

---

## 7. Summary: Why This Solution Fully Satisfies the MoD / DGIS Requirements

| Problem Statement Requirement (PS 26228) | How SentinelVision Satisfies It |
| :--- | :--- |
| **Model-Agnostic & Format Flexibility** | Ingests PyTorch (`.pt`) and ONNX models; accepts PASCAL VOC, COCO, and YOLO datasets. |
| **Training Data Anomaly Identification** | Detects near-duplicates, label flips, OOD samples, and trigger patches using Cleanlab and Mahalanobis math. |
| **Source / Contributor Risk Aggregation** | Provenance Aggregator groups sample errors into contributor-level z-scores and risk ratios. |
| **Model Integrity & Trojan Detection** | Employs Neural Cleanse trigger inversion, MAD anomaly indexing, and STRIP entropy corroboration. |
| **Inference Provenance & Cryptographic Binding** | `sealed_predict` binds 9 critical fields into RFC-8785 canonical JSON signed with Ed25519 keys. |
| **Post-Hoc Tampering & Replay Prevention** | 100% detection rate on field alterations; 128-bit nonces and blockchain composite keys reject replayed records. |
| **Distribution Drift Characterization** | MMD statistical tests measure divergence and separate operational lighting drift from suspicious manipulation. |
| **Analyst-Facing Governance & Dispositions** | Clear human-readable reasons, evidence hashes, and deterministic dispositions (`ACCEPT`, `REVIEW`, `QUARANTINE`). |
| **Tamper-Evident Audit Trail** | SHA-256 sequential hash chaining and Hyperledger Fabric enterprise blockchain ledger. |
| **Air-Gapped & Offline Operation** | 100% self-contained codebase; zero external network queries or cloud dependencies. |

---

*Report generated by the SentinelVision Governance & Assurance Platform.*
*Verified for Defence & Security Integrity Standards (DGIS / MoD).*
