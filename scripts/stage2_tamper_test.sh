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

echo "================================================================="
echo "STEP 5: TAMPER ATTEMPT OUTSIDE CHAINCODE PATH (Direct CouchDB Edit)"
echo "================================================================="
echo "1. Current untampered CouchDB record on couchdb0 (Org1):"
curl -s http://admin:adminpw@localhost:5984/mychannel_basic/finding-001 | jq .

echo ""
echo "2. Current untampered CouchDB record on couchdb1 (Org2):"
curl -s http://admin:adminpw@localhost:7984/mychannel_basic/finding-001 | jq .

echo ""
echo "3. Attacker directly edits couchdb0 (Org1) via REST API to downgrade severity and disposition..."
DOC=$(curl -s http://admin:adminpw@localhost:5984/mychannel_basic/finding-001)
REV=$(echo "$DOC" | jq -r '._rev')

TAMPERED_PAYLOAD=$(echo "$DOC" | jq '.severity="LOW" | .disposition="CLEARED_BY_ATTACKER" | .reason="Tampered outside chaincode path" | .confidence="0.10"')

echo "Sending PUT request to http://localhost:5984/mychannel_basic/finding-001 with tampered payload:"
TAMPER_RES=$(curl -s -X PUT http://admin:adminpw@localhost:5984/mychannel_basic/finding-001 \
  -H "Content-Type: application/json" \
  -d "$TAMPERED_PAYLOAD")
echo "CouchDB Response: $TAMPER_RES"

echo ""
echo "4. Verify that couchdb0 now holds the tampered data:"
curl -s http://admin:adminpw@localhost:5984/mychannel_basic/finding-001 | jq .

echo ""
echo "5. Query Org1 peer directly (reading from tampered couchdb0):"
peer chaincode query \
  -C mychannel \
  -n basic \
  -c '{"Args":["queryFinding","finding-001"]}'

echo ""
echo "6. Query Org2 peer directly (reading from untampered couchdb1):"
CORE_PEER_LOCALMSPID="Org2MSP" \
CORE_PEER_TLS_ROOTCERT_FILE="$ORG2_CA" \
CORE_PEER_MSPCONFIGPATH="$PROJECT_ROOT/fabric-samples/test-network/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp" \
CORE_PEER_ADDRESS=localhost:9051 \
peer chaincode query \
  -C mychannel \
  -n basic \
  -c '{"Args":["queryFinding","finding-001"]}'

echo ""
echo "================================================================="
echo "7. Fabric Integrity Enforcement: Attempt invoke requiring 2-org endorsement"
echo "================================================================="
echo "Attempting to invoke updateFindingDisposition on channel 'mychannel' with endorsements from both Org1 and Org2..."
set +e
INVOKE_TAMPER_OUTPUT=$(peer chaincode invoke \
  -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com \
  --tls \
  --cafile "$ORDERER_CA" \
  -C mychannel \
  -n basic \
  --peerAddresses localhost:7051 --tlsRootCertFiles "$CORE_PEER_TLS_ROOTCERT_FILE" \
  --peerAddresses localhost:9051 --tlsRootCertFiles "$ORG2_CA" \
  -c '{"function":"updateFindingDisposition","Args":["finding-001","AUDITED_AND_RESOLVED"]}' 2>&1)
INVOKE_RC=$?
set -e

echo "$INVOKE_TAMPER_OUTPUT"
echo "Invoke Exit Code: $INVOKE_RC"

echo ""
echo "================================================================="
echo "8. Inspecting Peer / Endorsement Discrepancy Evidence"
echo "================================================================="
echo "Checking if Fabric detected the endorsement payload mismatch:"
echo "$INVOKE_TAMPER_OUTPUT" | grep -iE "endorse|mismatch|failure|status:500|error" || true

