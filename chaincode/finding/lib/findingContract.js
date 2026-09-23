'use strict';

const { Contract } = require('fabric-contract-api');
const stringify = require('json-stringify-deterministic');
const sortKeysRecursive = require('sort-keys-recursive');

class FindingContract extends Contract {

    async InitLedger(ctx) {
        console.info('SentinelVision Finding Contract Initialized');
    }

    /**
     * submitFinding
     * Writes the 9 specified fields as JSON to the ledger under key = assetID.
     * Enforces presence of signature (non-empty string).
     * Enforces assetID uniqueness (rejects overwrite of existing assetID).
     * Enforces duplicate evidenceHash prevention via composite key secondary index.
     */
    async submitFinding(ctx, assetID, moduleName, reason, evidenceHash, confidence, severity, disposition, timestamp, signature) {
        if (!assetID) {
            throw new Error('assetID must be specified');
        }
        if (!evidenceHash) {
            throw new Error('evidenceHash must be specified');
        }
        if (!signature || typeof signature !== 'string' || signature.trim() === '') {
            throw new Error('signature must be specified and non-empty');
        }

        // 1. Check if assetID already has a committed finding in world state
        const existingFindingBytes = await ctx.stub.getState(assetID);
        if (existingFindingBytes && existingFindingBytes.length > 0) {
            throw new Error(`ASSET_EXISTS: assetID ${assetID} already has a committed finding; resubmission under an existing assetID is not permitted`);
        }

        // 2. Check for duplicate evidenceHash across all findings via composite key secondary index
        const iterator = await ctx.stub.getStateByPartialCompositeKey('evidenceHash~assetID', [evidenceHash]);
        let duplicateFound = false;
        let existingAssetID = null;

        try {
            while (true) {
                const response = await iterator.next();
                if (response.value && response.value.key) {
                    duplicateFound = true;
                    const splitKey = ctx.stub.splitCompositeKey(response.value.key);
                    existingAssetID = (splitKey.attributes && splitKey.attributes[1])
                        ? splitKey.attributes[1]
                        : (response.value.value ? response.value.value.toString('utf8') : 'UNKNOWN');
                    break;
                }
                if (response.done) {
                    break;
                }
            }
        } finally {
            await iterator.close();
        }

        if (duplicateFound) {
            throw new Error(`DUPLICATE_EVIDENCE: evidenceHash ${evidenceHash} was already committed under assetID ${existingAssetID}`);
        }

        const finding = {
            assetID: assetID,
            moduleName: moduleName,
            reason: reason,
            evidenceHash: evidenceHash,
            confidence: confidence,
            severity: severity,
            disposition: disposition,
            timestamp: timestamp,
            signature: signature
        };

        const findingBuffer = Buffer.from(stringify(sortKeysRecursive(finding)));
        await ctx.stub.putState(assetID, findingBuffer);

        // Put marker at composite key so future submissions with this evidenceHash are caught
        const compositeKey = ctx.stub.createCompositeKey('evidenceHash~assetID', [evidenceHash, assetID]);
        await ctx.stub.putState(compositeKey, Buffer.from(assetID));

        return stringify(sortKeysRecursive(finding));
    }

    /**
     * queryFinding
     * Reads back the finding JSON from the ledger for the given assetID.
     * Does NOT fail on older 8-field findings (reads stored JSON as-is).
     */
    async queryFinding(ctx, assetID) {
        if (!assetID) {
            throw new Error('assetID must be specified');
        }

        const findingBytes = await ctx.stub.getState(assetID);
        if (!findingBytes || findingBytes.length === 0) {
            throw new Error(`FINDING_NOT_FOUND: ${assetID}`);
        }
        return findingBytes.toString();
    }

    /**
     * findingExists
     * Checks if a finding exists in world state.
     */
    async findingExists(ctx, assetID) {
        const findingBytes = await ctx.stub.getState(assetID);
        return findingBytes && findingBytes.length > 0;
    }

    /**
     * updateFindingDisposition
     * Reads the current finding, updates the disposition, and writes back.
     * Crucial for state-read transaction verification and endorsement consensus checking.
     */
    async updateFindingDisposition(ctx, assetID, newDisposition) {
        if (!assetID) {
            throw new Error('assetID must be specified');
        }
        const findingBytes = await ctx.stub.getState(assetID);
        if (!findingBytes || findingBytes.length === 0) {
            throw new Error(`FINDING_NOT_FOUND: ${assetID}`);
        }

        const finding = JSON.parse(findingBytes.toString());
        finding.disposition = newDisposition;

        const findingBuffer = Buffer.from(stringify(sortKeysRecursive(finding)));
        await ctx.stub.putState(assetID, findingBuffer);
        return stringify(sortKeysRecursive(finding));
    }
}

module.exports = FindingContract;
