#!/usr/bin/env bash
set -e
export PATH=${PWD}/../bin:$PATH
export FABRIC_CFG_PATH=${PWD}/../config/
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID="Org1MSP"
export CORE_PEER_TLS_ROOTCERT_FILE=${PWD}/organizations/peerOrganizations/org1.example.com/tlsca/tlsca.org1.example.com-cert.pem
export CORE_PEER_MSPCONFIGPATH=${PWD}/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp
export CORE_PEER_ADDRESS=localhost:7051

ORDERER_CA=${PWD}/organizations/ordererOrganizations/example.com/tlsca/tlsca.example.com-cert.pem
ORG2_CA=${PWD}/organizations/peerOrganizations/org2.example.com/tlsca/tlsca.org2.example.com-cert.pem

echo "=== INVOKE WRITE: InitLedger ==="
peer chaincode invoke -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com --tls --cafile "$ORDERER_CA" -C mychannel -n basic --peerAddresses localhost:7051 --tlsRootCertFiles "$CORE_PEER_TLS_ROOTCERT_FILE" --peerAddresses localhost:9051 --tlsRootCertFiles "$ORG2_CA" -c '{"function":"InitLedger","Args":[]}'

sleep 3

echo "=== QUERY READ: asset1 ==="
peer chaincode query -C mychannel -n basic -c '{"Args":["ReadAsset","asset1"]}'

echo "=== INVOKE WRITE: CreateAsset assetSentinel ==="
peer chaincode invoke -o localhost:7050 --ordererTLSHostnameOverride orderer.example.com --tls --cafile "$ORDERER_CA" -C mychannel -n basic --peerAddresses localhost:7051 --tlsRootCertFiles "$CORE_PEER_TLS_ROOTCERT_FILE" --peerAddresses localhost:9051 --tlsRootCertFiles "$ORG2_CA" -c '{"function":"CreateAsset","Args":["assetSentinel","indigo","15","SentinelVisionMalad","4500"]}'

sleep 3

echo "=== QUERY READ: assetSentinel ==="
peer chaincode query -C mychannel -n basic -c '{"Args":["ReadAsset","assetSentinel"]}'
