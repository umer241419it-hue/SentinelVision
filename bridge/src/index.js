'use strict';

const express = require('express');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const { initializeContract, closeGateway } = require('./gateway');

const REGISTRY_PATH = path.resolve(__dirname, '../../crypto-utils/public_key_registry.json');
const CRYPTO_UTILS_DIR = path.resolve(__dirname, '../../crypto-utils');

/**
 * resolveSignerModule
 * Matches composite module descriptor (e.g. 'ModelIntegrity-NeuralCleanse-MAD-STRIP')
 * against registry base identity keys ('ModelIntegrity', 'InferenceProvenance').
 * Checks which registry key moduleName starts with (longest prefix match).
 * Returns null if no match found.
 */
function resolveSignerModule(moduleName) {
    if (!moduleName || typeof moduleName !== 'string') {
        return null;
    }
    let registry;
    try {
        const raw = fs.readFileSync(REGISTRY_PATH, 'utf-8');
        registry = JSON.parse(raw);
    } catch (err) {
        console.error('Failed to read public key registry:', err);
        return null;
    }

    const matchingKeys = Object.keys(registry)
        .filter(key => moduleName.startsWith(key))
        .sort((a, b) => b.length - a.length);

    return matchingKeys.length > 0 ? matchingKeys[0] : null;
}

/**
 * verifyFindingSignature
 * Invokes crypto-utils/verify.py's verify_fields() via Python subprocess.
 * Reuses canonical_json and Ed25519 verification without duplicating logic.
 */
function verifyFindingSignature(signerModule, fields, signature) {
    return new Promise((resolve) => {
        const pythonScript = `
import sys
import json
sys.path.insert(0, sys.argv[1])
from verify import verify_fields

try:
    input_data = json.loads(sys.stdin.read())
    signer_module = input_data['signerModule']
    fields = input_data['fields']
    signature = input_data['signature']
    is_valid = verify_fields(signer_module, fields, signature)
    print(json.dumps({'valid': is_valid}))
except Exception as e:
    print(json.dumps({'valid': False, 'error': str(e)}))
`;
        const pyProc = spawn('python3', ['-c', pythonScript, CRYPTO_UTILS_DIR]);

        let stdout = '';
        let stderr = '';

        pyProc.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        pyProc.stderr.on('data', (chunk) => { stderr += chunk.toString(); });

        pyProc.on('close', (code) => {
            if (code !== 0) {
                console.error(`Python verification process exited with code ${code}:`, stderr);
                return resolve({ valid: false, error: stderr || `Process exited with code ${code}` });
            }
            try {
                const res = JSON.parse(stdout.trim());
                resolve(res);
            } catch (err) {
                console.error('Failed to parse Python verification output:', stdout, err);
                resolve({ valid: false, error: err.message });
            }
        });

        pyProc.stdin.write(JSON.stringify({ signerModule, fields, signature }));
        pyProc.stdin.end();
    });
}

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;
const utf8Decoder = new TextDecoder();

function validateFindingPayload(body) {
    if (!body || typeof body !== 'object' || Array.isArray(body)) {
        return {
            valid: false,
            status: 400,
            error: 'Validation Error',
            details: 'Request body must be a valid JSON object'
        };
    }

    const requiredFields = [
        'assetID',
        'moduleName',
        'reason',
        'evidenceHash',
        'confidence',
        'severity',
        'disposition',
        'timestamp',
        'signature'
    ];

    for (const field of requiredFields) {
        if (body[field] === undefined || body[field] === null || body[field] === '') {
            return {
                valid: false,
                status: 400,
                error: 'Validation Error',
                details: `Missing or empty required field: '${field}'`
            };
        }
    }

    const numericConfidence = Number(body.confidence);
    if (isNaN(numericConfidence) || typeof body.confidence === 'boolean' || numericConfidence < 0 || numericConfidence > 1) {
        return {
            valid: false,
            status: 400,
            error: 'Validation Error',
            details: `Field 'confidence' must be a valid numeric value between 0.0 and 1.0 (received: ${JSON.stringify(body.confidence)})`
        };
    }

    return { valid: true };
}

app.get('/health', (req, res) => {
    res.json({
        status: 'UP',
        service: 'SentinelVision-Fabric-Bridge',
        channel: process.env.CHANNEL_NAME || 'mychannel',
        chaincode: process.env.CHAINCODE_NAME || 'basic',
        timestamp: new Date().toISOString()
    });
});

app.post('/findings', async (req, res) => {
    const validation = validateFindingPayload(req.body);
    if (!validation.valid) {
        return res.status(validation.status).json({
            success: false,
            error: validation.error,
            details: validation.details
        });
    }

    const {
        assetID,
        moduleName,
        reason,
        evidenceHash,
        confidence,
        severity,
        disposition,
        timestamp,
        signature
    } = req.body;

    try {
        const contract = await initializeContract();
        const resultBytes = await contract.submitTransaction(
            'submitFinding',
            String(assetID),
            String(moduleName),
            String(reason),
            String(evidenceHash),
            String(confidence),
            String(severity),
            String(disposition),
            String(timestamp),
            String(signature)
        );

        let parsedResult = null;
        if (resultBytes && resultBytes.length > 0) {
            try {
                parsedResult = JSON.parse(utf8Decoder.decode(resultBytes));
            } catch {
                parsedResult = utf8Decoder.decode(resultBytes);
            }
        }

        return res.status(201).json({
            success: true,
            message: 'Finding successfully committed to Fabric ledger',
            data: parsedResult || {
                assetID,
                moduleName,
                reason,
                evidenceHash,
                confidence: String(confidence),
                severity,
                disposition,
                timestamp,
                signature: String(signature)
            }
        });
    } catch (err) {
        console.error('Error submitting transaction:', err);
        return res.status(500).json({
            success: false,
            error: 'Ledger Commit Failure',
            details: err.message || String(err)
        });
    }
});

app.get('/findings/:id', async (req, res) => {
    const { id } = req.params;
    if (!id || id.trim() === '') {
        return res.status(400).json({
            success: false,
            error: 'Validation Error',
            details: 'Path parameter :id cannot be empty'
        });
    }

    try {
        const contract = await initializeContract();
        const resultBytes = await contract.evaluateTransaction('queryFinding', id);
        const resultJson = utf8Decoder.decode(resultBytes);
        const parsedData = JSON.parse(resultJson);

        // Read-time signature verification (does NOT modify ledger state)
        if (!parsedData.signature || typeof parsedData.signature !== 'string' || parsedData.signature.trim() === '') {
            parsedData.signatureStatus = 'UNSIGNED_LEGACY';
        } else {
            const signerModule = resolveSignerModule(parsedData.moduleName);
            if (!signerModule) {
                parsedData.signatureStatus = 'UNKNOWN_SIGNER';
                parsedData.signatureMessage = `No registered public key found matching module prefix for '${parsedData.moduleName}'`;
            } else {
                const fieldsToVerify = {
                    assetID: parsedData.assetID,
                    moduleName: parsedData.moduleName,
                    reason: parsedData.reason,
                    evidenceHash: parsedData.evidenceHash,
                    confidence: parsedData.confidence,
                    severity: parsedData.severity,
                    disposition: parsedData.disposition,
                    timestamp: parsedData.timestamp
                };
                const verResult = await verifyFindingSignature(signerModule, fieldsToVerify, parsedData.signature);
                parsedData.signatureStatus = verResult.valid ? 'VALID' : 'TAMPERED';
            }
        }

        return res.status(200).json({
            success: true,
            data: parsedData
        });
    } catch (err) {
        const errMsg = err.message || String(err);
        // Must match the exact error prefix thrown in chaincode/finding/lib/findingContract.js — do not change one without the other.
        if (errMsg.startsWith('FINDING_NOT_FOUND') || errMsg.includes('FINDING_NOT_FOUND')) {
            return res.status(404).json({
                success: false,
                error: 'Not Found',
                details: `Finding with ID '${id}' does not exist on the ledger`
            });
        }

        console.error(`Error querying finding ${id}:`, err);
        return res.status(500).json({
            success: false,
            error: 'Ledger Query Failure',
            details: errMsg
        });
    }
});

const server = app.listen(PORT, async () => {
    console.log(`SentinelVision Fabric Bridge listening on port ${PORT}`);
    try {
        await initializeContract();
        console.log('Fabric Gateway connection initialized successfully.');
    } catch (err) {
        console.error('Initial Gateway connection warning:', err.message);
    }
});

process.on('SIGTERM', async () => {
    console.log('Shutting down server...');
    server.close();
    await closeGateway();
});

process.on('SIGINT', async () => {
    console.log('Shutting down server...');
    server.close();
    await closeGateway();
});
