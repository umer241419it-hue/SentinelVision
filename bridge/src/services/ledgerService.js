'use strict';

/**
 * ledgerService — single source of truth for what the bridge has written (or
 * attempted to write) to Hyperledger Fabric.
 *
 * Fabric itself is authoritative for on-chain state. This journal records every
 * submit attempt made by the bridge together with the REAL outcome returned by
 * the Fabric Gateway (transaction ID, block number, validation code) or the real
 * error when the network is unavailable. Nothing here is synthesized: when a
 * value is not known it is stored as null and displayed as "Not available".
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

const WORKSPACE_ROOT = path.resolve(__dirname, '../../../');
const JOURNAL_FILE = path.join(WORKSPACE_ROOT, 'data/ledger_journal.json');
const CRYPTO_UTILS_DIR = path.join(WORKSPACE_ROOT, 'crypto-utils');

let gateway = null;
try {
    gateway = require('../gateway');
} catch {
    gateway = null;
}

// Real connection state, updated on every gateway interaction.
const fabricState = {
    connected: false,
    lastError: gateway ? 'Not yet contacted' : 'Fabric gateway module unavailable',
    lastCheckedAt: null
};

function readJournal() {
    try {
        if (fs.existsSync(JOURNAL_FILE)) return JSON.parse(fs.readFileSync(JOURNAL_FILE, 'utf-8'));
    } catch (err) {
        console.error('Failed to read ledger journal:', err.message);
    }
    return [];
}

function writeJournal(list) {
    fs.mkdirSync(path.dirname(JOURNAL_FILE), { recursive: true });
    fs.writeFileSync(JOURNAL_FILE, JSON.stringify(list, null, 2), 'utf-8');
}

async function getContract() {
    fabricState.lastCheckedAt = new Date().toISOString();
    if (!gateway || !gateway.initializeContract) {
        fabricState.connected = false;
        fabricState.lastError = 'Fabric gateway module unavailable';
        throw new Error(fabricState.lastError);
    }
    try {
        const contract = await gateway.initializeContract();
        fabricState.connected = true;
        fabricState.lastError = null;
        return contract;
    } catch (err) {
        fabricState.connected = false;
        fabricState.lastError = err.message;
        throw err;
    }
}

/** Probe the gateway once (used at startup and by /health consumers). */
async function probe() {
    try {
        await getContract();
    } catch {
        // state already recorded
    }
    return getFabricState();
}

function getFabricState() {
    return {
        ...fabricState,
        channel: gateway?.channelName || null,
        chaincode: gateway?.chaincodeName || null,
        mspId: gateway?.mspId || null,
        peerEndpoint: gateway?.peerEndpoint || null
    };
}

function sha256Hex(value) {
    return crypto.createHash('sha256').update(value).digest('hex');
}

/** Deterministic hash of a record (sorted keys) — used as a governance record digest. */
function recordDigest(obj) {
    const canonical = JSON.stringify(obj, Object.keys(obj).sort());
    return sha256Hex(canonical);
}

/**
 * Sign the 8 finding fields with the GovernanceEngine Ed25519 key using the
 * existing crypto-utils/sign.py implementation (same scheme as every other
 * module). Returns { signature } or { error } — never a placeholder.
 */
function signGovernanceFields(fields) {
    const script = [
        'import sys, json',
        `sys.path.insert(0, ${JSON.stringify(CRYPTO_UTILS_DIR)})`,
        'from sign import sign_fields',
        "print(sign_fields('GovernanceEngine', json.loads(sys.stdin.read())))"
    ].join('\n');
    const result = spawnSync(process.env.PYTHON || 'python3', ['-c', script], {
        input: JSON.stringify(fields),
        encoding: 'utf-8',
        timeout: 20000
    });
    const sig = String(result.stdout || '').trim();
    if (result.status === 0 && /^[0-9a-f]{128}$/i.test(sig)) return { signature: sig };
    return { error: String(result.stderr || result.error?.message || 'Signing failed').trim().split('\n').pop() };
}

/**
 * Submit a finding to the chaincode and journal the real outcome.
 *
 * @param {object} fields   The 9 chaincode arguments (assetID … signature).
 * @param {object} context  Provenance metadata stored alongside the journal entry
 *                          (findingId, testId, quarantineId, contributor, actor…).
 */
async function submitFinding(fields, context = {}) {
    const entry = {
        journalId: `ljr-${Date.now()}-${crypto.randomBytes(3).toString('hex')}`,
        attemptedAt: new Date().toISOString(),
        ledgerKey: fields.assetID,
        moduleName: fields.moduleName,
        reason: fields.reason,
        evidenceHash: fields.evidenceHash || null,
        confidence: fields.confidence ?? null,
        severity: fields.severity || null,
        disposition: fields.disposition || null,
        findingTimestamp: fields.timestamp || null,
        signaturePresent: Boolean(fields.signature),
        channel: gateway?.channelName || null,
        chaincode: gateway?.chaincodeName || null,
        txId: null,
        blockNumber: null,
        validationCode: null,
        status: 'PENDING',
        error: null,
        ...context
    };

    if (!fields.evidenceHash || !fields.signature) {
        entry.status = 'REJECTED_LOCALLY';
        entry.error = 'Chaincode requires a non-empty evidenceHash and signature; submission was not attempted.';
    } else {
        try {
            const contract = await getContract();
            const args = [
                fields.assetID, fields.moduleName, fields.reason, fields.evidenceHash,
                fields.confidence, fields.severity, fields.disposition, fields.timestamp, fields.signature
            ].map(v => String(v ?? ''));
            const submitted = await contract.submitAsync('submitFinding', { arguments: args });
            entry.txId = submitted.getTransactionId();
            const status = await submitted.getStatus();
            entry.blockNumber = status.blockNumber != null ? String(status.blockNumber) : null;
            entry.validationCode = status.code != null ? String(status.code) : null;
            entry.status = status.successful ? 'COMMITTED' : 'INVALIDATED';
            if (!status.successful) entry.error = `Transaction ${entry.txId} failed validation (code ${status.code})`;
        } catch (err) {
            entry.status = fabricState.connected ? 'FAILED' : 'FABRIC_UNAVAILABLE';
            entry.error = err.details?.map?.(d => d.message).join('; ') || err.message;
        }
    }

    const list = readJournal();
    list.unshift(entry);
    writeJournal(list);
    return entry;
}

function listEntries() {
    return readJournal();
}

/** Latest COMMITTED entry matching an evidence hash or ledger key. */
function findCommitted({ evidenceHash, ledgerKey } = {}) {
    return readJournal().find(e => e.status === 'COMMITTED' && (
        (evidenceHash && e.evidenceHash === evidenceHash) || (ledgerKey && e.ledgerKey === ledgerKey)
    )) || null;
}

/** Query the chaincode for the current on-chain record of a ledger key. */
async function queryOnChain(ledgerKey) {
    const contract = await getContract();
    const bytes = await contract.evaluateTransaction('queryFinding', String(ledgerKey));
    const text = Buffer.from(bytes).toString('utf-8');
    try { return JSON.parse(text); } catch { return { raw: text }; }
}

module.exports = {
    probe,
    getFabricState,
    submitFinding,
    listEntries,
    findCommitted,
    queryOnChain,
    signGovernanceFields,
    recordDigest,
    sha256Hex
};
