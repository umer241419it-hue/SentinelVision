#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$( cd "$DIR/.." >/dev/null 2>&1 && pwd )"

export PATH="$PROJECT_ROOT/fabric-samples/bin:$PATH"
export FABRIC_CFG_PATH="$PROJECT_ROOT/fabric-samples/config/"

cd "$PROJECT_ROOT/fabric-samples/test-network"

echo "=== DEPLOYING SENTINEL FINDING CHAINCODE (Replacing sample chaincode 'basic' with v2.0 sequence 2) ==="
./network.sh deployCC -ccn basic -ccp ../../chaincode/finding -ccl javascript -ccv 2.0 -ccs 2

echo "=== DEPLOYMENT COMPLETE ==="
