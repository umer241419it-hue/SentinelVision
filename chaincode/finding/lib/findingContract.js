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
     * Writes the 8 specified fields as JSON to the ledger under key = assetID.
     */
    async submitFinding(ctx, assetID, moduleName, reason, evidenceHash, confidence, severity, disposition, timestamp) {
        if (!assetID) {
            throw new Error('assetID must be specified');
        }

        const finding = {
            assetID: assetID,
            moduleName: moduleName,
            reason: reason,
            evidenceHash: evidenceHash,
            confidence: confidence,
            severity: severity,
            disposition: disposition,
            timestamp: timestamp
        };

        const findingBuffer = Buffer.from(stringify(sortKeysRecursive(finding)));
        await ctx.stub.putState(assetID, findingBuffer);
        return stringify(sortKeysRecursive(finding));
    }

    /**
     * queryFinding
     * Reads back the finding JSON from the ledger for the given assetID.
     */
    async queryFinding(ctx, assetID) {
        if (!assetID) {
            throw new Error('assetID must be specified');
        }

        const findingBytes = await ctx.stub.getState(assetID);
        if (!findingBytes || findingBytes.length === 0) {
            throw new Error(`The finding for assetID ${assetID} does not exist`);
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
            throw new Error(`The finding for assetID ${assetID} does not exist`);
        }

        const finding = JSON.parse(findingBytes.toString());
        finding.disposition = newDisposition;

        const findingBuffer = Buffer.from(stringify(sortKeysRecursive(finding)));
        await ctx.stub.putState(assetID, findingBuffer);
        return stringify(sortKeysRecursive(finding));
    }
}

module.exports = FindingContract;
