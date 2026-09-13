'use strict';

const express = require('express');
const { initializeContract, closeGateway } = require('./gateway');

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
        'timestamp'
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
        timestamp
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
            String(timestamp)
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
                timestamp
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
