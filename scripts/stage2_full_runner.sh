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

echo "================================================================================"
echo "STAGE 2 VERIFICATION & LEDGER TAMPER-EVIDENCE REPORT"
echo "================================================================================"

echo ""
echo "--------------------------------------------------------------------------------"
echo "CHECKPOINT 1 & 2: CHAINCODE DEFINITION & DOCKER CONTAINERS"
echo "--------------------------------------------------------------------------------"
docker ps --format "table {{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Names}}"
echo ""
echo "Committed chaincode definition on mychannel:"
peer lifecycle chaincode querycommitted --channelID mychannel --name basic

echo ""
echo "--------------------------------------------------------------------------------"
echo "CHECKPOINT 3: INVOKE submitFinding via peer CLI"
echo "--------------------------------------------------------------------------------"
peer chaincode invoke \
  -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com \
  --tls \
  --cafile "$ORDERER_CA" \
  -C mychannel \
  -n basic \
  --peerAddresses localhost:7051 --tlsRootCertFiles "$CORE_PEER_TLS_ROOTCERT_FILE" \
  --peerAddresses localhost:9051 --tlsRootCertFiles "$ORG2_CA" \
  -c '{"function":"submitFinding","Args":["finding-stage2-audit","SentinelVision-Malad-Guard","Unauthorized ingress connection detected from blacklisted CIDR","e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","0.97","CRITICAL","QUARANTINE","2026-09-13T10:25:00Z"]}'

sleep 3

echo ""
echo "--------------------------------------------------------------------------------"
echo "CHECKPOINT 4: QUERY queryFinding via peer CLI (Peer0 Org1)"
echo "--------------------------------------------------------------------------------"
peer chaincode query \
  -C mychannel \
  -n basic \
  -c '{"Args":["queryFinding","finding-stage2-audit"]}'

echo ""
echo "--------------------------------------------------------------------------------"
echo "CHECKPOINT 4: QUERY queryFinding via peer CLI (Peer0 Org2)"
echo "--------------------------------------------------------------------------------"
CORE_PEER_LOCALMSPID="Org2MSP" \
CORE_PEER_TLS_ROOTCERT_FILE="$ORG2_CA" \
CORE_PEER_MSPCONFIGPATH="$PROJECT_ROOT/fabric-samples/test-network/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp" \
CORE_PEER_ADDRESS=localhost:9051 \
peer chaincode query \
  -C mychannel \
  -n basic \
  -c '{"Args":["queryFinding","finding-stage2-audit"]}'

echo ""
echo "--------------------------------------------------------------------------------"
echo "CHECKPOINT 5: DIRECT COUCHDB STATE AUDIT (Both Peers Before Tampering)"
echo "--------------------------------------------------------------------------------"
echo "CouchDB0 (Org1) document:"
curl -s http://admin:adminpw@localhost:5984/mychannel_basic/finding-stage2-audit | jq .
echo "CouchDB1 (Org2) document:"
curl -s http://admin:adminpw@localhost:7984/mychannel_basic/finding-stage2-audit | jq .

echo ""
echo "--------------------------------------------------------------------------------"
echo "CHECKPOINT 5A: TAMPER ATTEMPT OUTSIDE CHAINCODE PATH (Direct CouchDB REST API)"
echo "--------------------------------------------------------------------------------"
echo "Executing direct HTTP PUT to couchdb0 on port 5984 to alter record outside blockchain..."
REV=$(curl -s http://admin:adminpw@localhost:5984/mychannel_basic/finding-stage2-audit | jq -r '._rev')
VERSION=$(curl -s http://admin:adminpw@localhost:5984/mychannel_basic/finding-stage2-audit | jq -r '."~version"')

curl -s -X PUT http://admin:adminpw@localhost:5984/mychannel_basic/finding-stage2-audit \
  -H 'Content-Type: application/json' \
  -d '{
    "_id":"finding-stage2-audit",
    "_rev":"'"$REV"'",
    "assetID":"finding-stage2-audit",
    "confidence":"0.10",
    "disposition":"CLEARED_BY_ATTACKER",
    "evidenceHash":"tampered_bad_hash_999",
    "moduleName":"SentinelVision-Malad-Guard",
    "reason":"Tampered directly inside CouchDB bypassing Fabric chaincode",
    "severity":"LOW",
    "timestamp":"2026-09-13T10:25:00Z",
    "~version":"'"$VERSION"'"
  }' | jq .

echo ""
echo "Verifying tampered document in couchdb0:"
curl -s http://admin:adminpw@localhost:5984/mychannel_basic/finding-stage2-audit | jq .

echo ""
echo "Flushing peer0.org1 in-memory cache to force reading modified CouchDB state..."
docker restart peer0.org1.example.com > /dev/null
sleep 5

echo ""
echo "State Divergence Exposed:"
echo "Query Peer0 Org1 (tampered CouchDB0):"
peer chaincode query -C mychannel -n basic -c '{"Args":["queryFinding","finding-stage2-audit"]}'

echo "Query Peer0 Org2 (untampered CouchDB1):"
CORE_PEER_LOCALMSPID="Org2MSP" \
CORE_PEER_TLS_ROOTCERT_FILE="$ORG2_CA" \
CORE_PEER_MSPCONFIGPATH="$PROJECT_ROOT/fabric-samples/test-network/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp" \
CORE_PEER_ADDRESS=localhost:9051 \
peer chaincode query -C mychannel -n basic -c '{"Args":["queryFinding","finding-stage2-audit"]}'

echo ""
echo "--------------------------------------------------------------------------------"
echo "CHECKPOINT 5B: FABRIC INTEGRITY ENFORCEMENT & REJECTION"
echo "--------------------------------------------------------------------------------"
echo "Attempting endorsement across both Org1 and Org2 for updateFindingDisposition..."
set +e
INVOKE_REJECT_OUT=$(peer chaincode invoke \
  -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com \
  --tls \
  --cafile "$ORDERER_CA" \
  -C mychannel \
  -n basic \
  --peerAddresses localhost:7051 --tlsRootCertFiles "$CORE_PEER_TLS_ROOTCERT_FILE" \
  --peerAddresses localhost:9051 --tlsRootCertFiles "$ORG2_CA" \
  -c '{"function":"updateFindingDisposition","Args":["finding-stage2-audit","CONFIRMED_QUARANTINE"]}' 2>&1)
REJECT_EXIT=$?
set -e

echo "$INVOKE_REJECT_OUT"
echo ""
echo "Invoke Exit Code: $REJECT_EXIT (Non-zero confirms transaction was aborted and rejected)"

echo ""
echo "Verifying CouchDB1 (Org2) was protected and unmodified:"
CORE_PEER_LOCALMSPID="Org2MSP" \
CORE_PEER_TLS_ROOTCERT_FILE="$ORG2_CA" \
CORE_PEER_MSPCONFIGPATH="$PROJECT_ROOT/fabric-samples/test-network/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp" \
CORE_PEER_ADDRESS=localhost:9051 \
peer chaincode query -C mychannel -n basic -c '{"Args":["queryFinding","finding-stage2-audit"]}'

echo ""
echo "================================================================================"
echo "STAGE 2 RUN COMPLETE"
echo "================================================================================"
