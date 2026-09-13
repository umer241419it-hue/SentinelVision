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
echo "STEP 4: INVOKE submitFinding via peer CLI"
echo "================================================================="
peer chaincode invoke \
  -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com \
  --tls \
  --cafile "$ORDERER_CA" \
  -C mychannel \
  -n basic \
  --peerAddresses localhost:7051 --tlsRootCertFiles "$CORE_PEER_TLS_ROOTCERT_FILE" \
  --peerAddresses localhost:9051 --tlsRootCertFiles "$ORG2_CA" \
  -c '{"function":"submitFinding","Args":["finding-001","SentinelVision-Malad-Guard","Unauthorized ingress connection detected from blacklisted CIDR","e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","0.97","CRITICAL","QUARANTINE","2026-09-13T10:25:00Z"]}'

sleep 3

echo ""
echo "================================================================="
echo "STEP 4: QUERY queryFinding via peer CLI (Org1)"
echo "================================================================="
peer chaincode query \
  -C mychannel \
  -n basic \
  -c '{"Args":["queryFinding","finding-001"]}'

echo ""
echo "================================================================="
echo "STEP 4: QUERY queryFinding via peer CLI (Org2)"
echo "================================================================="
CORE_PEER_LOCALMSPID="Org2MSP" \
CORE_PEER_TLS_ROOTCERT_FILE="$ORG2_CA" \
CORE_PEER_MSPCONFIGPATH="$PROJECT_ROOT/fabric-samples/test-network/organizations/peerOrganizations/org2.example.com/users/Admin@org2.example.com/msp" \
CORE_PEER_ADDRESS=localhost:9051 \
peer chaincode query \
  -C mychannel \
  -n basic \
  -c '{"Args":["queryFinding","finding-001"]}'

