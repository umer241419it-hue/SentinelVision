
# SentinelVision — Setup Notes

**SIH Problem Statement:** PS 26228  
**Project:** SentinelVision — Trustworthy Computer Vision Integrity Assurance for Data, Models and Inference Outputs in Multi-Contributor Pipelines.

This document describes the recommended fresh-machine setup for SentinelVision.

> **Important:** SentinelVision is designed for fully offline / air-gapped operation at runtime. Initial provisioning of software packages, Docker images, Fabric binaries and public benchmark data may require an internet-connected machine. Provision those resources first, then operate the assurance stack locally/offline.

## 1. Operating System

### Recommended

Use a native Linux system, preferably Ubuntu LTS.

The project uses Bash scripts, Python, Node.js/npm, Docker and Hyperledger Fabric test-network tooling. Linux is therefore the primary setup target.

### Windows users

Do **not** run the complete Fabric/SentinelVision setup directly from Windows CMD or PowerShell.

Choose either:

1. A native Linux machine; **recommended**.
2. Windows with **WSL2 + Ubuntu**.

For WSL2:

1. Open PowerShell as Administrator.
2. Install Ubuntu/WSL2:

    wsl --install -d Ubuntu

3. Restart Windows if requested.
4. Open Ubuntu.
5. Verify:

    wsl --version
    uname -a

6. Install Docker Desktop for Windows.
7. In Docker Desktop enable:
   **Settings → Resources → WSL Integration → your Ubuntu distribution**
8. From Ubuntu verify:

    docker --version
    docker info

If Docker info fails, fix Docker Desktop/WSL integration before continuing.

Keep the project inside the Linux filesystem, for example:

    ~/projects/SentinelVision

Avoid running the repository from /mnt/c/... when possible.

## 2. Linux System Packages

On Ubuntu/Debian:

    sudo apt update
    sudo apt install -y git curl ca-certificates build-essential python3 python3-pip python3-venv jq

Verify:

    git --version
    curl --version
    python3 --version
    pip3 --version
    jq --version

Docker is required for Hyperledger Fabric.

### Native Linux Docker

Install Docker using the official Docker instructions for your Linux distribution.

Then verify:

    docker --version
    docker info

If systemd is used:

    sudo systemctl enable docker
    sudo systemctl start docker

Optional:

    sudo usermod -aG docker "$USER"

Log out/in after adding the user to the docker group.

### Windows + WSL2

When Docker Desktop WSL2 integration is used, use the Docker CLI exposed to WSL. Do not create a second Docker daemon inside WSL unless you have a specific reason.

## 3. GPU

A GPU is recommended for the heavier model-integrity workloads, particularly Neural Cleanse and STRIP.

Check:

    nvidia-smi

After installing PyTorch:

    python3 -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"

CPU execution is possible for supported workflows but can be substantially slower.

## 4. Clone the Repository

    mkdir -p ~/projects
    cd ~/projects
    git clone https://github.com/umer241419it-hue/SentinelVision.git
    cd SentinelVision
    git checkout Malad
    git pull origin Malad

Verify:

    git status

## 5. Python Environment

Create an isolated environment:

    cd ~/projects/SentinelVision
    python3 -m venv .venv
    source .venv/bin/activate
    python --version
    pip --version

Upgrade packaging tools:

    python -m pip install --upgrade pip setuptools wheel

Install the repository's declared data-integrity and drift dependencies:

    pip install -r data-integrity/requirements.txt
    pip install -r drift-monitor/requirements.txt

Install the cryptographic dependency:

    pip install pynacl

The model-integrity implementation uses PyTorch, torchvision, NumPy, pandas and Pillow. Install the appropriate PyTorch build for the target machine, then:

    pip install numpy pandas pillow

For NVIDIA systems, select a PyTorch build compatible with the installed NVIDIA driver/CUDA environment. Do not depend on runtime model-weight downloads.

Verify core imports:

    python - <<'PY'
    import numpy
    import scipy
    import sklearn
    import cleanlab
    import nacl
    import torch
    print("Python stack OK")
    print("NumPy:", numpy.__version__)
    print("PyTorch:", torch.__version__)
    print("CUDA available:", torch.cuda.is_available())
    PY

## 6. Node.js

The current tested environment uses Node.js 22.x.

Verify:

    node --version
    npm --version

Install bridge dependencies:

    cd ~/projects/SentinelVision/bridge
    npm install

Install frontend dependencies:

    cd ~/projects/SentinelVision/frontend
    npm install

Verify the frontend:

    npm run build

## 7. Cryptographic Keys

SentinelVision uses Ed25519 signatures for assurance findings and related evidence.

Private keys are intentionally excluded from Git under:

    crypto-utils/keys/

A fresh deployment must therefore provision or generate its required local keys.

Inspect the key generator:

    cd ~/projects/SentinelVision
    python crypto-utils/keygen.py --help

Generate/provision only the identities required by the deployment.

**Never commit private keys to GitHub.**

The public registry is version controlled:

    crypto-utils/public_key_registry.json

## 8. Hyperledger Fabric

### Why Fabric is external

The repository contains SentinelVision's chaincode:

    chaincode/finding/

but does not contain the Fabric binaries, Docker images, certificates, peers, orderer or test-network installation.

The tested setup uses:

- Hyperledger Fabric 2.5.16
- Fabric CA 1.5.17
- Docker
- Fabric test-network
- Channel: mychannel
- Chaincode: basic
- Chaincode language: JavaScript

Keep Fabric samples outside the Git repository.

### Install Fabric

Create a separate Fabric workspace:

    mkdir -p ~/projects/fabric
    cd ~/projects/fabric

Install the tested Fabric versions:

    curl -sSL https://raw.githubusercontent.com/hyperledger/fabric/main/scripts/install-fabric.sh | \
      bash -s -- -f 2.5.16 -c 1.5.17 binary docker

Enter the installed samples:

    cd ~/projects/fabric/fabric-samples

Verify:

    ./bin/peer version
    ./bin/orderer version
    ./bin/fabric-ca-client version

The expected versions are Fabric 2.5.16 and Fabric CA 1.5.17.

Do not mix arbitrary Fabric binaries/images/samples versions.

## 9. Start the Fabric Network

    cd ~/projects/fabric/fabric-samples/test-network

Clean an old test network if necessary:

    ./network.sh down

Start the network and create SentinelVision's channel:

    ./network.sh up createChannel -c mychannel -ca

Verify:

    docker ps

## 10. Deploy SentinelVision Chaincode

Set the project path:

    export SENTINELVISION_ROOT="$HOME/projects/SentinelVision"

Deploy the actual SentinelVision finding contract:

    cd ~/projects/fabric/fabric-samples/test-network

    ./network.sh deployCC \
      -ccn basic \
      -ccp "$SENTINELVISION_ROOT/chaincode/finding" \
      -ccl javascript

Expected deployment:

    Chaincode: basic
    Channel:   mychannel
    Language:  javascript

## 11. Configure Fabric Paths

The bridge dynamically resolves Fabric paths, but explicit environment variables are recommended.

    export SENTINELVISION_ROOT="$HOME/projects/SentinelVision"
    export FABRIC_SAMPLES_PATH="$HOME/projects/fabric/fabric-samples"
    export CRYPTO_PATH="$FABRIC_SAMPLES_PATH/test-network/organizations"

Verify:

    test -d "$FABRIC_SAMPLES_PATH" && echo "FABRIC_SAMPLES_PATH: OK"
    test -d "$CRYPTO_PATH" && echo "CRYPTO_PATH: OK"

To persist them:

    echo 'export SENTINELVISION_ROOT="$HOME/projects/SentinelVision"' >> ~/.bashrc
    echo 'export FABRIC_SAMPLES_PATH="$HOME/projects/fabric/fabric-samples"' >> ~/.bashrc
    echo 'export CRYPTO_PATH="$FABRIC_SAMPLES_PATH/test-network/organizations"' >> ~/.bashrc
    source ~/.bashrc

## 12. Verify the Unified CLI

    cd ~/projects/SentinelVision
    source .venv/bin/activate
    ./sentinelvision --help

The unified CLI provides workflows including:

    dataset prepare-voc2012
    integrity generate-benchmark
    integrity scan
    integrity evaluate
    report generate

## 13. Prepare the VOC2012 Benchmark

The repository includes a PASCAL VOC2012 preparation workflow.

    ./sentinelvision dataset prepare-voc2012 --limit 500

The workflow verifies the downloaded archive, extracts it safely, validates the VOC structure and generates SentinelVision manifests/benchmark data.

Large datasets and generated runtime data are excluded from Git.

For an air-gapped deployment, acquire and verify required public benchmark assets on the provisioning machine and transfer them through the approved offline-media process.

## 14. Data Integrity Workflow

Generate the SentinelVision benchmark:

    ./sentinelvision integrity generate-benchmark --limit 300

Scan:

    ./sentinelvision integrity scan datasets/sentinelvision_voc2012/mixed_attack

Evaluate:

    ./sentinelvision integrity evaluate \
      --manifest datasets/sentinelvision_voc2012/metadata/attack_manifest.json

Generated evidence/results remain local.

## 15. Run the Backend Bridge

The Express bridge listens on port 3000.

    cd ~/projects/SentinelVision/bridge
    npm start

From another terminal:

    curl http://127.0.0.1:3000/health

The bridge connects to Fabric when the Fabric network and credentials are available. A local/offline standby state must not be interpreted as a confirmed on-chain transaction.

## 16. Run the Frontend

    cd ~/projects/SentinelVision/frontend
    npm run dev -- --host 127.0.0.1 --port 5173

Open:

    http://127.0.0.1:5173

The frontend communicates with the bridge at:

    http://127.0.0.1:3000

## 17. Recommended Startup

Once the prerequisites are installed:

    cd ~/projects/SentinelVision
    ./start_sentinelvision.sh

The startup script:

1. Checks Python and Node.js.
2. Checks GPU/CUDA availability.
3. Creates required runtime directories.
4. Starts the bridge on port 3000.
5. Waits for the bridge health endpoint.
6. Starts the Vite frontend on port 5173.
7. Waits for frontend availability.
8. Keeps the services running until Ctrl+C.

URLs:

| Service | Address |
|---|---|
| SentinelVision UI | http://127.0.0.1:5173 |
| Bridge API | http://127.0.0.1:3000 |
| Bridge Health | http://127.0.0.1:3000/health |

Stop with:

    Ctrl+C

## 18. Electron Development UI

From frontend:

    cd ~/projects/SentinelVision/frontend
    npm run electron:dev

The development runner manages the bridge/frontend lifecycle and waits for the required endpoints.

## 19. Complete Verification

Repository and CLI:

    cd ~/projects/SentinelVision
    source .venv/bin/activate
    ./sentinelvision --help
    git status

Python:

    python -c "import numpy, scipy, sklearn, cleanlab, nacl, torch; print('Python stack OK')"

Node:

    node --version
    npm --version

Frontend:

    cd frontend
    npm run build

Backend:

    cd ../bridge
    npm start

Health check from another terminal:

    curl http://127.0.0.1:3000/health

Fabric:

    cd "$FABRIC_SAMPLES_PATH/test-network"
    docker ps
    ./network.sh channel list

## 20. Fabric CLI Environment

For direct Fabric verification:

    cd "$FABRIC_SAMPLES_PATH/test-network"

    export PATH="$FABRIC_SAMPLES_PATH/bin:$PATH"
    export FABRIC_CFG_PATH="$FABRIC_SAMPLES_PATH/config"

    export CORE_PEER_TLS_ENABLED=true
    export CORE_PEER_LOCALMSPID=Org1MSP
    export CORE_PEER_TLS_ROOTCERT_FILE="$FABRIC_SAMPLES_PATH/test-network/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"
    export CORE_PEER_MSPCONFIGPATH="$FABRIC_SAMPLES_PATH/test-network/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp"
    export CORE_PEER_ADDRESS=localhost:7051

These variables allow direct peer CLI verification of the local ledger.

## 21. Runtime Architecture

    SentinelVision React/Vite Frontend
                 |
                 | HTTP
                 v
          Express Bridge :3000
                 |
        +--------+--------+----------------+
        |                 |                |
        v                 v                v
    Data Integrity   Model Integrity   Provenance /
    Python Engine    Python Engine     Drift / Governance
        |                 |                |
        +-----------------+----------------+
                          |
                          v
                  Assurance Findings
                          |
                          v
                  SHA-256 + Ed25519
                          |
                          v
                Hyperledger Fabric
                  mychannel / basic
                          |
                          v
                   Local Ledger

## 22. Offline / Air-Gapped Rules

### Provisioning may use connectivity

A connected provisioning machine may obtain:

- Git repositories
- Python packages
- Node packages
- Docker images
- Hyperledger Fabric binaries
- Public benchmark datasets/models

### Runtime must remain local

Do not introduce:

- Cloud AI APIs
- Remote inference APIs
- Runtime telemetry
- Cloud databases
- Runtime model downloads
- CDN dependencies required by the assurance workflow

After provisioning, datasets/models/reference batteries should be transferred through the approved offline-media process.

## 23. Local / Ignored Assets

The repository intentionally excludes local or generated resources including:

    datasets/
    data/
    reports/
    .venv/
    venv/
    fabric-samples/
    bridge/node_modules/
    frontend/node_modules/
    model-integrity/data/
    model-integrity/triggers/
    crypto-utils/keys/

Therefore a fresh Git clone does not contain:

- Fabric certificates/private keys
- Fabric Docker images
- Python virtual environments
- Node node_modules
- Large benchmark datasets
- Generated runtime reports
- Runtime caches
- Private signing keys

These must be provisioned locally.

## 24. Troubleshooting

### Docker unavailable

    docker --version
    docker info

Native Linux:

    sudo systemctl start docker

Windows/WSL2:

- Start Docker Desktop.
- Ensure WSL2 integration is enabled for Ubuntu.
- Re-run docker info from Ubuntu.

### Fabric network does not start

    cd "$FABRIC_SAMPLES_PATH/test-network"
    ./network.sh down
    docker ps -a
    ./network.sh up createChannel -c mychannel -ca

### Chaincode deployment fails

Check:

    test -f "$SENTINELVISION_ROOT/chaincode/finding/index.js"
    test -f "$SENTINELVISION_ROOT/chaincode/finding/lib/findingContract.js"

Then:

    cd "$FABRIC_SAMPLES_PATH/test-network"
    ./network.sh deployCC -ccn basic -ccp "$SENTINELVISION_ROOT/chaincode/finding" -ccl javascript

### Bridge cannot connect to Fabric

Check:

    echo "$FABRIC_SAMPLES_PATH"
    echo "$CRYPTO_PATH"
    test -d "$FABRIC_SAMPLES_PATH"
    test -d "$CRYPTO_PATH"
    docker ps

Confirm that the Fabric network is running and organization credentials exist.

### Port 3000 or 5173 is occupied

    ss -ltnp | grep ':3000'
    ss -ltnp | grep ':5173'

Use the SentinelVision startup script for normal development startup.

### GPU unavailable

    nvidia-smi
    python -c "import torch; print(torch.cuda.is_available())"

CPU execution can be used where supported, but model-integrity workloads may be slower.

### Private-key error

    ls -la ~/projects/SentinelVision/crypto-utils/keys/

Provision/generate the required Ed25519 key. Never commit private keys.

## 25. Fresh-Machine Quick Start

For Linux with Docker already working:

    mkdir -p ~/projects
    cd ~/projects
    git clone https://github.com/umer241419it-hue/SentinelVision.git
    cd SentinelVision
    git checkout Malad

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip setuptools wheel
    pip install -r data-integrity/requirements.txt
    pip install -r drift-monitor/requirements.txt
    pip install pynacl
    pip install numpy pandas pillow

    cd bridge
    npm install

    cd ../frontend
    npm install
    npm run build

    cd ..
    ./sentinelvision --help

Then install/configure Hyperledger Fabric 2.5.16 + Fabric CA 1.5.17, create mychannel, deploy chaincode basic, configure FABRIC_SAMPLES_PATH/CRYPTO_PATH, and start:

    ./start_sentinelvision.sh

## 26. Setup Checklist

- [ ] Native Linux or WSL2 Ubuntu is being used.
- [ ] Docker is installed and docker info succeeds.
- [ ] Python 3 and venv are available.
- [ ] SentinelVision Python dependencies are installed.
- [ ] Node.js 22.x and npm are installed.
- [ ] Bridge dependencies are installed.
- [ ] Frontend dependencies are installed.
- [ ] Frontend build succeeds.
- [ ] Required Ed25519 private keys are provisioned locally.
- [ ] Hyperledger Fabric 2.5.16 is installed.
- [ ] Fabric CA 1.5.17 is installed.
- [ ] Fabric test-network is running.
- [ ] mychannel exists.
- [ ] SentinelVision basic chaincode is deployed.
- [ ] FABRIC_SAMPLES_PATH is configured.
- [ ] CRYPTO_PATH is configured.
- [ ] ./sentinelvision --help works.
- [ ] Bridge health responds on port 3000.
- [ ] Frontend responds on port 5173.
- [ ] Runtime does not require cloud services.

## 27. Repository Components

| Component | Location | Purpose |
|---|---|---|
| Unified CLI | sentinelvision / sentinelvision_cli.py | Main command-line workflows |
| Frontend | frontend/ | React/Vite/Electron analyst interface |
| Bridge | bridge/ | Express API and integration layer |
| Data Integrity | data-integrity/ | Training-data integrity checks |
| Model Integrity | model-integrity/ | Neural Cleanse, MAD and STRIP |
| Inference Provenance | inference-provenance/ | Cryptographic inference sealing/verification |
| Drift Monitor | drift-monitor/ | Distribution-shift monitoring |
| Governance | governance/ | Assurance aggregation, reports and audit trail |
| Crypto Utilities | crypto-utils/ | SHA-256/Ed25519 signing and verification |
| Fabric Chaincode | chaincode/finding/ | On-chain finding contract |
| Startup | start_sentinelvision.sh | Local startup |
| Architecture | ARCHITECTURE.md | Architecture/governance specification |

## 28. Final Deployment Note

The setup is intentionally split into:

1. SentinelVision source code.
2. Local Python/Node dependencies.
3. Local cryptographic private keys.
4. External Hyperledger Fabric infrastructure.
5. Large benchmark/model/data assets.
6. Generated runtime evidence and reports.

This separation keeps the Git repository clean while supporting the PS requirement for an offline/air-gapped operational deployment.

The repository does **not** claim that a fresh Git clone alone contains a complete Fabric installation or private deployment credentials. Those resources are provisioned as part of the target deployment environment.



# 29. Judge / Evaluator End-to-End Test Procedure

This section is the recommended procedure for a judge who wants to independently verify the complete PS 26228 implementation rather than only opening the UI.

## 29.1 Clean runtime and application

    cd ~/projects/SentinelVision
    source .venv/bin/activate
    ./sentinelvision --help
    git status

Start Fabric:

    cd "$FABRIC_SAMPLES_PATH/test-network"
    ./network.sh up createChannel -c mychannel -ca
    docker ps

Configure paths:

    export SENTINELVISION_ROOT="$HOME/projects/SentinelVision"
    export FABRIC_SAMPLES_PATH="$HOME/projects/fabric/fabric-samples"
    export CRYPTO_PATH="$FABRIC_SAMPLES_PATH/test-network/organizations"

Start SentinelVision:

    cd "$SENTINELVISION_ROOT"
    ./start_sentinelvision.sh

Open http://127.0.0.1:5173 and verify:

    curl http://127.0.0.1:3000/health

## 29.2 Training-data integrity test

This directly tests PS 26228 capability 2.2.1.

Prepare VOC2012:

    ./sentinelvision dataset prepare-voc2012 --limit 500

Generate controlled attack scenarios:

    ./sentinelvision integrity generate-benchmark --limit 300

Expected scenario directories:

    label_flip/
    systematic_mislabel/
    duplicate_flooding/
    ood_insertion/
    trigger_injection/
    mixed_attack/

Run the real detector:

    ./sentinelvision integrity scan \
      --dataset datasets/sentinelvision_voc2012/mixed_attack

Evaluate against the authoritative attack manifest:

    ./sentinelvision integrity evaluate \
      --manifest datasets/sentinelvision_voc2012/metadata/attack_manifest.json

Run the clean-control test:

    ./sentinelvision integrity clean-control --limit 200

Generate the report:

    ./sentinelvision report generate

Inspect:

    datasets/sentinelvision_voc2012/results/
    datasets/sentinelvision_voc2012/metadata/attack_manifest.json

The judge should verify that the result changes when the input scenario changes and that the evidence is generated by the detector rather than being a static UI fixture.

## 29.3 Model-integrity test

This directly tests PS 26228 capability 2.2.2.

Review the coverage statement first:

    less model-integrity/COVERAGE.md

Inspect the available model-integrity tools:

    find model-integrity -maxdepth 2 -type f | sort

Inspect the detector CLI:

    cd model-integrity
    python3 src/strip_detector.py --help

For a supported local model, run the detector using its displayed model-path option, for example:

    python3 src/strip_detector.py --model-path /path/to/model.pt

Record the model digest before testing:

    sha256sum /path/to/model.pt

Inspect generated findings/evidence:

    model-integrity/findings.json

The model workflow uses the repository's calibrated model-integrity pipeline. The judge must use COVERAGE.md to interpret supported access assumptions and limitations.

If a required white-box assessment is unavailable, that condition must be reported as unavailable/not assessed rather than interpreted as a clean model.

## 29.4 Inference provenance and output-integrity test

This directly tests PS 26228 capability 2.2.3.

Inspect the tools:

    find inference-provenance -maxdepth 2 -type f | sort

Inspect the local verifier:

    python3 inference-provenance/src/run_local_verification.py --help

Verify a real generated inference seal using the verifier's displayed arguments.

Then perform a tamper test:

1. Copy a generated seal/evidence JSON.
2. Modify one protected value such as an input digest, model digest, preprocessing value or output.
3. Run the verifier again.

Expected result: verification failure / invalid / tampered.

For replay/substitution testing, associate a seal with a different input/model record and verify that the cryptographic binding rejects the mismatch.

## 29.5 Distribution-shift test

This directly tests PS 26228 capability 2.2.4.

Generate deterministic local scenarios:

    cd ~/projects/SentinelVision
    python3 scripts/generate_drift_test_data.py

Build the reference battery:

    cd drift-monitor
    python3 -m src.reference_builder --config config.json

Calibrate:

    python3 -m src.threshold_calibrator --config config.json

Normal scenario:

    python3 -m src.run_drift_monitor \
      --config config.json \
      --input ../data/scenario1-normal

Expected assessment:

    NO_SIGNIFICANT_SHIFT

Lighting/operational shift:

    python3 -m src.run_drift_monitor \
      --config config.json \
      --input ../data/scenario2-lighting-shift

Expected behavior includes increased MMD and operational diagnostics, normally producing:

    OPERATIONAL_SHIFT_LIKELY

Unexplained shift:

    python3 -m src.run_drift_monitor \
      --config config.json \
      --input ../data/scenario4-unexplained

Expected:

    UNEXPLAINED_SHIFT

Important: distribution shift is evidence of a changed distribution, not proof that an attacker caused it.

With bridge and Fabric running, a finding can be submitted using:

    python3 -m src.run_drift_monitor \
      --config config.json \
      --input ../data/scenario2-lighting-shift \
      --submit \
      --bridge-url http://127.0.0.1:3000

## 29.6 Governance and assurance-report test

This directly tests PS 26228 capability 2.2.5 and the expected assurance-report/audit-log deliverables.

Check:

    ./cv-assurance --help
    ./sentinelvision governance --help

Run the repository governance demonstration when its prerequisite result assets are available:

    ./sentinelvision governance demo

For a custom assessment:

    ./sentinelvision governance assess --help

The assessor accepts dataset, model, data findings, model findings, inference records, drift results and reference-battery inputs. Use only files that were actually generated.

Verify a generated assurance report:

    ./sentinelvision governance verify-report \
      --report /path/to/assurance_report.json

Verify its audit chain:

    ./sentinelvision governance verify-audit \
      --report /path/to/assurance_report.json

A modified, inserted, deleted or reordered audit event should cause audit verification to fail.

## 29.7 Real Fabric ledger test

Verify the network:

    cd "$FABRIC_SAMPLES_PATH/test-network"
    docker ps
    ./network.sh channel list

Verify SentinelVision chaincode is running:

    docker ps --format '{{.Names}}' | grep basic

Start the bridge if it is not already running:

    cd "$SENTINELVISION_ROOT/bridge"
    npm start

Check the live ledger API:

    curl http://127.0.0.1:3000/ledger/transactions

Submit a real finding through a supported detector/bridge workflow.

Then verify that the transaction has:

- a real Fabric transaction ID;
- committed status;
- actual ledger/block information;
- the real asset/finding data.

The application intentionally distinguishes a local submission attempt from a confirmed on-chain commit. A failed/offline submission must never be interpreted as a committed transaction.

## 29.8 Chaincode immutability tests

The finding contract enforces:

- non-empty asset ID;
- non-empty evidence hash;
- non-empty signature;
- unique asset IDs;
- unique evidence hashes.

Submit an identical asset ID twice.

Expected second result:

    ASSET_EXISTS

Attempt to reuse an existing evidence hash under another asset ID.

Expected result:

    DUPLICATE_EVIDENCE

This verifies enforcement at the Fabric smart-contract layer, not merely in the frontend.

## 29.9 Frontend live-integration test

Open:

    http://127.0.0.1:5173

Test:

1. Analyst/validation workflow.
2. Data Integrity.
3. Model Integrity.
4. Drift monitoring.
5. Inference/provenance verification.
6. Findings.
7. Quarantine.
8. Governance Reports.
9. Fabric Ledger.
10. System/settings status.

While executing a validation, inspect the bridge log:

    tail -f ~/projects/SentinelVision/logs/bridge.log

The bridge should launch the real Python engine and collect its generated result/evidence.

The judge should compare the UI result with the generated local artifact and, where applicable, with the Fabric ledger.

## 29.10 Quarantine test

For a high-confidence/high-severity real finding, inspect the Quarantine page.

Verify that a record contains:

- asset/finding identifier;
- human-readable reason;
- severity/confidence where applicable;
- evidence relationship;
- disposition;
- timestamp;
- provenance/ledger state where available.

The UI must not invent a Fabric transaction ID when the transaction was not committed.

## 29.11 Governance Reports test

Open Governance Reports and verify:

1. The report is actually present in the local report store.
2. The report opens in a readable viewer.
3. Assessed assets are identified.
4. Per-check statuses are present.
5. Findings contain reasons/evidence.
6. Confidence/severity/disposition are present where applicable.
7. Coverage/limitations are declared.
8. Audit information is present.
9. CLI cryptographic verification succeeds.

## 29.12 Fabric Ledger UI test

Open the Fabric Ledger page and verify:

- channel is mychannel;
- chaincode is basic;
- peer/organization information matches the actual local network;
- committed records contain genuine Fabric transaction IDs;
- block numbers correspond to actual ledger state;
- local submission attempts are not displayed as committed blocks.

For any displayed transaction, independently query Fabric and compare transaction ID, asset ID, finding/module, evidence hash, severity/disposition, timestamp and signature.

## 29.13 Offline/air-gapped test

After provisioning all packages, Docker images, Fabric artifacts, datasets and models, disconnect the machine from the internet.

Run:

    ./sentinelvision --help
    curl http://127.0.0.1:3000/health
    curl http://127.0.0.1:5173

Run a local detector using already-provisioned assets.

Expected:

- no cloud AI API;
- no remote inference service;
- no runtime model download;
- local Python engines still operate;
- local Fabric still operates;
- frontend/backend remain local.

If an optional asset is missing, the system must report unavailable/not assessed rather than fabricating a successful result.

# 30. PS 26228 Capability-to-Test Matrix

| PS 26228 requirement | SentinelVision component | Judge verification |
|---|---|---|
| Training-data integrity | data-integrity/ | Generate attack benchmark → scan → evaluate |
| Trigger injection | Data Integrity Trigger Detector | trigger_injection / mixed_attack |
| Label flipping | Data Integrity | label_flip |
| Systematic mislabelling | Data Integrity | systematic_mislabel |
| Near-duplicate flooding | Data Integrity | duplicate_flooding |
| OOD insertion | Data Integrity | ood_insertion |
| Contributor/source aggregation | Provenance aggregation | Inspect group/source analysis |
| Model integrity | model-integrity/ | Run detector on a local supported model |
| Backdoor/trigger search | Neural Cleanse/MAD + STRIP | Inspect model evidence |
| Model substitution | SHA-256 model digest | Modify model and compare digest |
| Access assumptions | model-integrity/COVERAGE.md | Review coverage and unavailable behavior |
| Inference provenance | inference-provenance/ | Generate/verify seal |
| Tampering detection | Seal verification | Modify protected field → failure |
| Replay/substitution | Cryptographic binding | Use seal with different input/model → failure |
| Distribution shift | drift-monitor/ | Normal, lighting/source/unexplained scenarios |
| Calibrated threshold | Drift calibration | Build reference → calibrate → detect |
| Human-readable findings | Governance/finding schema | Inspect reason/evidence |
| Severity/confidence | Governance | Inspect generated finding/report |
| Accept/review/quarantine | Governance disposition | Inspect recommendation |
| Tamper-evident audit trail | governance/audit.py | verify-audit |
| Assurance report schema | governance/ | Generate + verify report |
| Tamper-evident ledger | Hyperledger Fabric | Submit → query Fabric directly |
| Duplicate protection | chaincode/finding/ | Repeat asset/evidence submission |
| Offline operation | Entire local stack | Disconnect network after provisioning |

COCO/YOLO and ONNX/PyTorch/TorchScript are organiser-defined target formats in the PS. Before using one of those formats as a judge test, verify the actual adapter/model support present in the current repository and report unsupported formats honestly.

# 31. What the Judge Should Independently Verify

The following should not have to be trusted merely because the UI displays them:

- finding data;
- model SHA-256 digest;
- inference seal;
- evidence hash;
- governance report signature;
- audit-chain hash;
- Fabric transaction ID;
- Fabric block number;
- chaincode state;
- quarantine disposition.

The frontend is the analyst-facing presentation layer. The Python engines, cryptographic evidence, governance artifacts and Fabric ledger are the verification sources.

# 32. Recommended Fast Judge Path

For a compact but meaningful evaluation:

    docker info
    python3 --version
    node --version
    ./sentinelvision --help

    ./start_sentinelvision.sh

Then:

1. Open the UI.
2. Verify bridge health.
3. Verify Fabric channel and chaincode.
4. Prepare a small VOC2012 benchmark.
5. Generate controlled attacks.
6. Run data-integrity scan/evaluation.
7. Run clean-control.
8. Run one model-integrity assessment.
9. Verify one inference seal and tamper with it.
10. Run normal and shifted drift scenarios.
11. Generate/verify a governance report.
12. Submit a real finding to Fabric.
13. Query that finding directly from Fabric.
14. Test duplicate asset/evidence rejection.
15. Inspect Findings, Quarantine, Governance Reports and Fabric Ledger.
16. Disconnect internet and verify local operation.

# 33. Final Judge Checklist

- [ ] Linux or WSL2 Ubuntu.
- [ ] Docker works.
- [ ] Python environment works.
- [ ] Node.js 22.x works.
- [ ] Frontend builds.
- [ ] Ed25519 keys are provisioned locally.
- [ ] Fabric 2.5.16 is installed.
- [ ] Fabric CA 1.5.17 is installed.
- [ ] mychannel exists.
- [ ] basic chaincode is deployed.
- [ ] SentinelVision starts.
- [ ] Bridge health is available.
- [ ] Frontend is available.
- [ ] VOC2012 preparation succeeds.
- [ ] Controlled attack benchmark generation succeeds.
- [ ] Data-integrity scan produces real findings.
- [ ] Benchmark evaluation produces measurable results.
- [ ] Clean-control evaluation runs.
- [ ] Model-integrity assessment runs on a supported local model.
- [ ] Model digest/evidence can be inspected.
- [ ] Inference seal verification works.
- [ ] Tampered inference evidence is rejected.
- [ ] Drift reference/calibration works.
- [ ] Normal and shifted drift scenarios produce different assessments.
- [ ] Governance report is generated.
- [ ] Governance report verification succeeds.
- [ ] Audit-chain verification succeeds.
- [ ] Real finding reaches Fabric.
- [ ] Fabric transaction can be independently queried.
- [ ] Duplicate asset submission is rejected.
- [ ] Duplicate evidence hash is rejected.
- [ ] Findings page displays live evidence.
- [ ] Quarantine page displays live records.
- [ ] Governance Reports displays generated reports.
- [ ] Fabric Ledger displays confirmed ledger state.
- [ ] Runtime still works after internet disconnection.
- [ ] Coverage/limitations are reviewed before declaring support for any PS attack class or file format.

This is the reproducible evaluation procedure for PS 26228.
