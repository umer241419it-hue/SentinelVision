#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$( cd "$DIR/.." >/dev/null 2>&1 && pwd )"

export PATH="$PROJECT_ROOT/fabric-samples/bin:$PATH"
export FABRIC_CFG_PATH="$PROJECT_ROOT/fabric-samples/config/"
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID="Org1MSP"
export CORE_PEER_TLS_ROOTCERT_FILE="$PROJECT_ROOT/fabric-samples/test-network/organizations/peerOrganizations/org1.example.com/tlsca/tlsca.org1.example.com-cert.pem"
export CORE_PEER_MSPCONFIGPATH="$PROJECT_ROOT/fabric-samples/test-network/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp"
export CORE_PEER_ADDRESS=localhost:7051

ORDERER_CA="$PROJECT_ROOT/fabric-samples/test-network/organizations/ordererOrganizations/example.com/tlsca/tlsca.example.com-cert.pem"
ORG2_CA="$PROJECT_ROOT/fabric-samples/test-network/organizations/peerOrganizations/org2.example.com/tlsca/tlsca.org2.example.com-cert.pem"

echo "=== 1. Current State in CouchDB0 (Org1) ==="
curl -s http://admin:adminpw@localhost:5984/mychannel_basic/finding-001 | jq .

echo ""
echo "=== 2. Directly Editing CouchDB0 (Tampering severity to TAMPERED_LOW and disposition to CLEARED_BY_ATTACKER) ==="
REV=$(curl -s http://admin:adminpw@localhost:5984/mychannel_basic/finding-001 | jq -r '._rev')
curl -s -X PUT http://admin:adminpw@localhost:5984/mychannel_basic/finding-001 \
  -H 'Content-Type: application/json' \
  -d '{
    "_id":"finding-001",
    "_rev":"'"$REV"'",
    "assetID":"finding-001",
    "confidence":"0.05",
    "disposition":"CLEARED_BY_ATTACKER",
    "evidenceHash":"tampered_hash_9999",
    "moduleName":"SentinelVision-Malad-Guard",
    "reason":"Tampered by unauthorized actor directly in CouchDB",
    "severity":"TAMPERED_LOW",
    "timestamp":"2026-09-13T10:25:00Z",
    "~version":"CgMBCwA="
  }' | jq .

echo ""
echo "=== 3. Flushing Peer0 Org1 In-Memory State Cache (Restarting container to force DB read) ==="
docker restart peer0.org1.example.com
sleep 5

echo ""
echo "=== 4. Querying Peer0 Org1 (Direct Read from Tampered CouchDB0) ==="
peer chaincode query \
  -C mychannel \
  -n basic \
  -c '{"Args":["queryFinding","finding-001"]}'

echo ""
echo "=== 5. Querying Peer0 Org2 (Direct Read from Genuine CouchDB1) ==="
CORE_PEER_LOCALMSPID="Org2MSP" \
CORE_PEER_TLS_ROOTCERT_FILE="$ORG2_CA" \
CORE_PEER_MSPCONFIGPATH="$PROJECT_ROOT/fabric-samples/test-network/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp" \
CORE_PEER_ADDRESS=localhost:9051 \
peer chaincode query \
  -C mychannel \
  -n basic \
  -c '{"Args":["queryFinding","finding-001"]}'

echo ""
echo "=== 6. Endorsement Verification Attempt (Fabric Integrity Enforcement) ==="
echo "Client attempts to invoke updateFindingDisposition across both Peer0 Org1 and Peer0 Org2..."
set +e
INVOKE_OUT=$(peer chaincode invoke \
  -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com \
  --tls \
  --cafile "$ORDERER_CA" \
  -C mychannel \
  -n basic \
  --peerAddresses localhost:7051 --tlsRootCertFiles "$CORE_PEER_TLS_ROOTCERT_FILE" \
  --peerAddresses localhost:9051 --tlsRootCertFiles "$ORG2_CA" \
  -c '{"function":"updateFindingDisposition","Args":["finding-001","QUARANTINE_CONFIRMED"]}' 2>&1)
EXIT_CODE=$?
set -e

echo "$INVOKE_OUT"
echo "Exit Code: $EXIT_CODE"

