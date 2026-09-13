#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$( cd "$DIR/.." >/dev/null 2>&1 && pwd )"

export PATH="$PROJECT_ROOT/fabric-samples/bin:$PATH"
export FABRIC_CFG_PATH="$PROJECT_ROOT/fabric-samples/config/"

cd "$PROJECT_ROOT/fabric-samples/test-network"

echo "=== 1. NETWORK DOWN (Purging corrupted world state, chaincode containers, and artifacts) ==="
./network.sh down

echo ""
echo "=== 2. NETWORK UP (Clean Bring-Up with CouchDB & Channel 'mychannel') ==="
./network.sh up createChannel -c mychannel -s couchdb

echo ""
echo "=== 3. DEPLOYING STAGE 2 FINDING CHAINCODE (Fresh deployment on mychannel) ==="
./network.sh deployCC -ccn basic -ccp ../../chaincode/finding -ccl javascript -ccv 1.0 -ccs 1

echo ""
echo "=== 4. CONFIRM RUNNING CONTAINERS (docker ps) ==="
docker ps --format "table {{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Names}}"

echo ""
echo "=== 5. FRESH VERIFICATION WRITE & READ ON CLEAN NETWORK ==="
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID="Org1MSP"
export CORE_PEER_TLS_ROOTCERT_FILE="$PROJECT_ROOT/fabric-samples/test-network/organizations/peerOrganizations/org1.example.com/tlsca/tlsca.org1.example.com-cert.pem"
export CORE_PEER_MSPCONFIGPATH="$PROJECT_ROOT/fabric-samples/test-network/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp"
export CORE_PEER_ADDRESS=localhost:7051

ORDERER_CA="$PROJECT_ROOT/fabric-samples/test-network/organizations/ordererOrganizations/example.com/tlsca/tlsca.example.com-cert.pem"
ORG2_CA="$PROJECT_ROOT/fabric-samples/test-network/organizations/peerOrganizations/org2.example.com/tlsca/tlsca.org2.example.com-cert.pem"

echo "Invoking submitFinding on clean ledger..."
peer chaincode invoke \
  -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com \
  --tls \
  --cafile "$ORDERER_CA" \
  -C mychannel \
  -n basic \
  --peerAddresses localhost:7051 --tlsRootCertFiles "$CORE_PEER_TLS_ROOTCERT_FILE" \
  --peerAddresses localhost:9051 --tlsRootCertFiles "$ORG2_CA" \
  -c '{"function":"submitFinding","Args":["finding-clean-01","SentinelVision-Guard","Network baseline established","8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4","0.99","INFO","RESOLVED","2026-09-13T10:40:00Z"]}'

sleep 3

echo ""
echo "Fresh Query on Peer0 Org1 (localhost:7051):"
peer chaincode query -C mychannel -n basic -c '{"Args":["queryFinding","finding-clean-01"]}'

echo ""
echo "Fresh Query on Peer0 Org2 (localhost:9051):"
CORE_PEER_LOCALMSPID="Org2MSP" \
CORE_PEER_TLS_ROOTCERT_FILE="$ORG2_CA" \
CORE_PEER_MSPCONFIGPATH="$PROJECT_ROOT/fabric-samples/test-network/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp" \
CORE_PEER_ADDRESS=localhost:9051 \
peer chaincode query -C mychannel -n basic -c '{"Args":["queryFinding","finding-clean-01"]}'

echo ""
echo "=== CLEAN RESTART COMPLETE ==="
