'use strict';

const grpc = require('@grpc/grpc-js');
const { connect, hash, signers } = require('@hyperledger/fabric-gateway');
const crypto = require('crypto');
const fs = require('fs/promises');
const path = require('path');

const channelName = process.env.CHANNEL_NAME || 'mychannel';
const chaincodeName = process.env.CHAINCODE_NAME || 'basic';
const mspId = process.env.MSP_ID || 'Org1MSP';

const projectRoot = path.resolve(__dirname, '../../');
const cryptoPath = process.env.CRYPTO_PATH || path.resolve(
    projectRoot,
    'fabric-samples/test-network/organizations/peerOrganizations/org1.example.com'
);
const keyDirectoryPath = path.resolve(
    cryptoPath,
    'users/User1@org1.example.com/msp/keystore'
);
const certDirectoryPath = path.resolve(
    cryptoPath,
    'users/User1@org1.example.com/msp/signcerts'
);
const tlsCertPath = path.resolve(
    cryptoPath,
    'peers/peer0.org1.example.com/tls/ca.crt'
);

const peerEndpoint = process.env.PEER_ENDPOINT || 'localhost:7051';
const peerHostAlias = process.env.PEER_HOST_ALIAS || 'peer0.org1.example.com';

let gatewayInstance = null;
let clientInstance = null;
let contractInstance = null;

async function getFirstDirFileName(dirPath) {
    const files = await fs.readdir(dirPath);
    const file = files[0];
    if (!file) {
        throw new Error(`No files in directory: ${dirPath}`);
    }
    return path.join(dirPath, file);
}

async function newGrpcConnection() {
    const tlsRootCert = await fs.readFile(tlsCertPath);
    const tlsCredentials = grpc.credentials.createSsl(tlsRootCert);
    return new grpc.Client(peerEndpoint, tlsCredentials, {
        'grpc.ssl_target_name_override': peerHostAlias,
    });
}

async function newIdentity() {
    const certPath = await getFirstDirFileName(certDirectoryPath);
    const credentials = await fs.readFile(certPath);
    return { mspId, credentials };
}

async function newSigner() {
    const keyPath = await getFirstDirFileName(keyDirectoryPath);
    const privateKeyPem = await fs.readFile(keyPath);
    const privateKey = crypto.createPrivateKey(privateKeyPem);
    return signers.newPrivateKeySigner(privateKey);
}

async function initializeContract() {
    if (contractInstance) {
        return contractInstance;
    }

    clientInstance = await newGrpcConnection();
    gatewayInstance = connect({
        client: clientInstance,
        identity: await newIdentity(),
        signer: await newSigner(),
        hash: hash.sha256,
        evaluateOptions: () => ({ deadline: Date.now() + 5000 }),
        endorseOptions: () => ({ deadline: Date.now() + 15000 }),
        submitOptions: () => ({ deadline: Date.now() + 15000 }),
        commitStatusOptions: () => ({ deadline: Date.now() + 60000 }),
    });

    const network = gatewayInstance.getNetwork(channelName);
    contractInstance = network.getContract(chaincodeName);
    return contractInstance;
}

async function closeGateway() {
    if (gatewayInstance) {
        gatewayInstance.close();
    }
    if (clientInstance) {
        clientInstance.close();
    }
    contractInstance = null;
}

module.exports = {
    initializeContract,
    closeGateway,
};
