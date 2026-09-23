#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$( cd "$DIR/.." >/dev/null 2>&1 && pwd )"

export PATH="$PROJECT_ROOT/fabric-samples/bin:$PATH"
export FABRIC_CFG_PATH="$PROJECT_ROOT/fabric-samples/config/"

cd "$PROJECT_ROOT/fabric-samples/test-network"

echo "=== DEPLOYING SENTINEL FINDING CHAINCODE v1.3 SEQUENCE 3 ==="
./network.sh deployCC -c mychannel -ccn basic -ccp ../../chaincode/finding -ccl javascript -ccv 1.3 -ccs 3

echo "=== DEPLOYMENT COMPLETE ==="
