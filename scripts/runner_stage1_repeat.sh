#!/usr/bin/env bash
set -e

echo "=== FRESH SESSION PID ==="
echo "FRESH_PID=$$"

echo "=== CHECKING DIRECTORY ==="
cd /home/anyone/projects/SentinelVision/fabric-samples/test-network
pwd

echo "=== NETWORK DOWN ==="
./network.sh down

echo "=== NETWORK UP CREATECHANNEL -S COUCHDB ==="
./network.sh up createChannel -c mychannel -s couchdb

echo "=== DEPLOY CHAINCODE ==="
./network.sh deployCC -ccn basic -ccp ../asset-transfer-basic/chaincode-go -ccl go

echo "=== RUN WRITE & READ (assetSentinel3) ==="
./test_cc3.sh

echo "=== COMPLETE ==="
