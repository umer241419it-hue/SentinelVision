
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
