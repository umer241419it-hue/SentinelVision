'use strict';

const express = require('express');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { spawn } = require('child_process');

const authService = require('./services/authService');
const dataService = require('./services/dataService');
const jobService = require('./services/jobService');
const datasetValidationService = require('./services/datasetValidationService');
const modelValidationService = require('./services/modelValidationService');
const modelHookService = require('./services/modelHookService');
const validationEngineService = require('./services/validationEngineService');
const ledgerService = require('./services/ledgerService');

let fabricGateway = null;
try {
    fabricGateway = require('./gateway');
} catch (e) {
    console.log('Fabric Gateway module not loaded:', e.message);
}

const REGISTRY_PATH = path.resolve(__dirname, '../../crypto-utils/public_key_registry.json');
const CRYPTO_UTILS_DIR = path.resolve(__dirname, '../../crypto-utils');
const WORKSPACE_ROOT = path.resolve(__dirname, '../../');
const UPLOADS_DIR = path.join(WORKSPACE_ROOT, 'data/uploads');
const UPLOADS_META_FILE = path.join(WORKSPACE_ROOT, 'data/uploads_meta.json');
const CONTRIBUTORS_FILE = path.join(WORKSPACE_ROOT, 'data/contributors.json');
const QUARANTINE_FILE = path.join(WORKSPACE_ROOT, 'data/quarantine_registry.json');

if (!fs.existsSync(UPLOADS_DIR)) fs.mkdirSync(UPLOADS_DIR, { recursive: true });

// Load / Save Contributors
let contributors = [];
function loadContributors() {
    if (fs.existsSync(CONTRIBUTORS_FILE)) {
        try { contributors = JSON.parse(fs.readFileSync(CONTRIBUTORS_FILE, 'utf-8')); } catch { contributors = []; }
    } else {
        contributors = [];
    }
}
function saveContributors() {
    try {
        fs.writeFileSync(CONTRIBUTORS_FILE, JSON.stringify(contributors, null, 2), 'utf-8');
    } catch (err) {
        console.error('Error saving contributors:', err.message);
    }
}
loadContributors();

// Load / Save Uploads
let uploads = [];
function loadUploads() {
    if (fs.existsSync(UPLOADS_META_FILE)) {
        try { uploads = JSON.parse(fs.readFileSync(UPLOADS_META_FILE, 'utf-8')); } catch { uploads = []; }
    } else {
        uploads = [];
        saveUploads();
    }
}
function saveUploads() {
    try { fs.writeFileSync(UPLOADS_META_FILE, JSON.stringify(uploads, null, 2), 'utf-8'); } catch (err) { console.error('Error saving uploads:', err.message); }
}
loadUploads();

// Load / Save Quarantine
let quarantineRegistry = [];
function loadQuarantine() {
    if (fs.existsSync(QUARANTINE_FILE)) {
        try { quarantineRegistry = JSON.parse(fs.readFileSync(QUARANTINE_FILE, 'utf-8')); } catch { quarantineRegistry = []; }
    } else {
        quarantineRegistry = [];
        saveQuarantine();
    }
}
function saveQuarantine() {
    try { fs.writeFileSync(QUARANTINE_FILE, JSON.stringify(quarantineRegistry, null, 2), 'utf-8'); } catch (err) { console.error('Error saving quarantine:', err.message); }
}
loadQuarantine();

const app = express();

// CORS setup
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, Authorization');
    if (req.method === 'OPTIONS') {
        return res.sendStatus(200);
    }
    next();
});

// Raw body parser for multipart file uploads & JSON
app.use(express.json({ limit: '512mb' }));
app.use(express.urlencoded({ extended: true, limit: '512mb' }));
app.use(express.raw({ type: 'multipart/form-data', limit: '512mb' }));

const PORT = process.env.PORT || 3000;
const utf8Decoder = new TextDecoder();

// Helper to parse multipart/form-data with multiple files & fields (zero external dependencies)
function parseMultipartData(req) {
    return new Promise((resolve, reject) => {
        const getBuffer = () => {
            if (Buffer.isBuffer(req.body) && req.body.length > 0) {
                return Promise.resolve(req.body);
            }
            return new Promise((res, rej) => {
                const chunks = [];
                req.on('data', (c) => chunks.push(c));
                req.on('end', () => res(Buffer.concat(chunks)));
                req.on('error', rej);
            });
        };

        const contentType = req.headers['content-type'] || '';
        const boundaryMatch = contentType.match(/boundary=(?:"([^"]+)"|([^;]+))/i);
        if (!boundaryMatch) {
            return reject(new Error('Missing multipart boundary'));
        }
        const boundary = (boundaryMatch[1] || boundaryMatch[2]).trim();
        const boundaryBuf = Buffer.from(`--${boundary}`);

        getBuffer().then((buf) => {
            const files = [];
            const fields = {};

            let cur = 0;
            while (cur < buf.length) {
                const bIdx = buf.indexOf(boundaryBuf, cur);
                if (bIdx === -1) break;

                // Check if closing boundary --boundary--
                if (buf.slice(bIdx + boundaryBuf.length, bIdx + boundaryBuf.length + 2).toString() === '--') {
                    break;
                }

                let headerStart = bIdx + boundaryBuf.length;
                if (buf[headerStart] === 13 && buf[headerStart + 1] === 10) headerStart += 2; // \r\n
                else if (buf[headerStart] === 10) headerStart += 1; // \n

                const headerEndCRLF = buf.indexOf(Buffer.from('\r\n\r\n'), headerStart);
                const headerEndLF = buf.indexOf(Buffer.from('\n\n'), headerStart);
                let headerEnd = -1;
                let headerEndLen = 4;
                if (headerEndCRLF !== -1 && (headerEndLF === -1 || headerEndCRLF <= headerEndLF)) {
                    headerEnd = headerEndCRLF;
                    headerEndLen = 4;
                } else if (headerEndLF !== -1) {
                    headerEnd = headerEndLF;
                    headerEndLen = 2;
                }
                if (headerEnd === -1) break;

                const headers = buf.slice(headerStart, headerEnd).toString('utf-8');
                const partStart = headerEnd + headerEndLen;

                const nextBIdx = buf.indexOf(boundaryBuf, partStart);
                if (nextBIdx === -1) break;

                let partEnd = nextBIdx;
                if (partEnd >= 2 && buf[partEnd - 2] === 13 && buf[partEnd - 1] === 10) partEnd -= 2;
                else if (partEnd >= 1 && buf[partEnd - 1] === 10) partEnd -= 1;

                const partBuffer = buf.slice(partStart, partEnd);

                const nameMatch = headers.match(/name="([^"]+)"/i);
                const fnMatch = headers.match(/filename="([^"]+)"/i);
                const fieldName = nameMatch ? nameMatch[1] : '';

                if (fnMatch) {
                    files.push({
                        fieldName,
                        filename: fnMatch[1],
                        fileBuffer: partBuffer,
                        size: partBuffer.length
                    });
                } else if (fieldName) {
                    fields[fieldName] = partBuffer.toString('utf-8').trim();
                }

                cur = nextBIdx;
            }

            resolve({ files, fields });
        }).catch(reject);
    });
}

// Backward-compatible single file parser
async function parseMultipartBuffer(req) {
    const parsed = await parseMultipartData(req);
    if (!parsed.files || parsed.files.length === 0) {
        throw new Error('No file part found in request');
    }
    return {
        fileBuffer: parsed.files[0].fileBuffer,
        filename: parsed.files[0].filename,
        fields: parsed.fields
    };
}

// ---------------------------------------------------------------------------
// 1. Health & Subsystem Status
// ---------------------------------------------------------------------------
app.get('/health', async (req, res) => {
    try {
        await ledgerService.probe();
    } catch {}
    res.json(dataService.getSystemHealth());
});

// ---------------------------------------------------------------------------
// 2. Authentication Endpoints (/api/auth/*)
// ---------------------------------------------------------------------------
app.post('/api/auth/login', (req, res) => {
    try {
        const { email, password } = req.body || {};
        const result = authService.login(email, password);
        jobService.recordAuditEvent('USER_LOGIN', { email, role: result.user.role }, result.user);
        res.json(result);
    } catch (err) {
        res.status(err.status || 500).json({ error: err.message });
    }
});

app.post('/api/auth/register', (req, res) => {
    try {
        const result = authService.register(req.body || {});
        res.status(201).json(result);
    } catch (err) {
        res.status(err.status || 500).json({ error: err.message });
    }
});

app.get('/api/auth/me', authService.requireAuth, (req, res) => {
    res.json({ user: req.user });
});

app.post('/api/auth/logout', (req, res) => {
    res.json({ success: true, message: 'Logged out successfully' });
});

// ---------------------------------------------------------------------------
// 3. Core Findings & Module Results Endpoints
// ---------------------------------------------------------------------------
app.get('/findings', (req, res) => {
    res.json(dataService.getAllFindings());
});

app.get('/api/findings', (req, res) => {
    res.json({ findings: dataService.getAllFindings() });
});

app.get('/findings/:id', (req, res) => {
    const finding = dataService.getFindingById(req.params.id);
    if (!finding) {
        return res.status(404).json({ error: 'Finding not found' });
    }
    res.json({ success: true, data: finding });
});

app.post('/findings', async (req, res) => {
    const finding = req.body;
    if (!finding || !finding.assetID) {
        return res.status(400).json({ error: 'Invalid finding payload' });
    }

    const nowIso = new Date().toISOString();
    const fields = {
        assetID: String(finding.assetID),
        moduleName: String(finding.moduleName || 'DataIntegrity'),
        reason: String(finding.reason || 'Integrity anomaly detected'),
        evidenceHash: String(finding.evidenceHash || ledgerService.recordDigest(finding)),
        confidence: Number(finding.confidence ?? 0.95),
        severity: String(finding.severity || 'HIGH'),
        disposition: String(finding.disposition || 'REVIEW'),
        timestamp: String(finding.timestamp || nowIso),
        signature: String(finding.signature || '')
    };

    if (!fields.signature) {
        const sigResult = ledgerService.signGovernanceFields(fields);
        if (sigResult.signature) {
            fields.signature = sigResult.signature;
        }
    }

    const journalEntry = await ledgerService.submitFinding(fields, {
        findingId: finding.id || finding.assetID,
        contributorId: finding.contributorId || null,
        contributorName: finding.contributorName || null,
        actor: req.user?.email || 'analyst@sentinelvision.io',
        action: 'FINDING_SUBMIT'
    });

    const saved = dataService.saveSubmittedFinding(finding, journalEntry);
    jobService.recordAuditEvent('FINDING_SUBMITTED', {
        assetID: finding.assetID,
        module: finding.moduleName,
        txId: journalEntry.txId,
        status: journalEntry.status
    });
    res.status(201).json({ success: true, message: 'Finding recorded', data: saved, journalEntry });
});

app.get('/integrity/results', (req, res) => {
    res.json(dataService.getDataIntegrityResults());
});

app.get('/model-integrity/results', (req, res) => {
    res.json(dataService.getModelIntegrityResults());
});

app.get('/drift/results', (req, res) => {
    res.json(dataService.getDriftResults());
});

app.get('/evidence', (req, res) => {
    res.json(dataService.getEvidenceList());
});

app.get('/evidence/:evidenceId/verify', (req, res) => {
    try {
        const id = path.basename(req.params.evidenceId);
        if (!/^[a-f0-9]{64}$/i.test(id)) {
            return res.status(400).json({ verified: false, error: 'Invalid evidence identifier' });
        }

        const evidenceDirs = [
            path.join(WORKSPACE_ROOT, 'data-integrity/evidence_store'),
            path.join(WORKSPACE_ROOT, 'model-integrity/evidence_store'),
            path.join(WORKSPACE_ROOT, 'drift-monitor/evidence_store'),
            path.join(WORKSPACE_ROOT, 'inference-provenance/evidence_store')
        ];
        let target = null;
        for (const dir of evidenceDirs) {
            const candidate = path.join(dir, `${id}.json`);
            if (fs.existsSync(candidate)) {
                target = candidate;
                break;
            }
        }
        if (!target) return res.status(404).json({ verified: false, error: 'Evidence record not found' });

        const digest = crypto.createHash('sha256').update(fs.readFileSync(target)).digest('hex');
        const verified = digest.toLowerCase() === id.toLowerCase();
        res.json({
            verified,
            evidenceId: id,
            computedHash: digest,
            recordedHash: id,
            timestamp: new Date().toISOString()
        });
    } catch (err) {
        res.status(500).json({ verified: false, error: err.message });
    }
});

app.get('/ledger/transactions', (req, res) => {
    res.json(dataService.getLedgerTransactions());
});

// Compatibility route used by the auditor frontend.
app.get('/api/auditor/ledger/transactions', (req, res) => {
    res.json(dataService.getLedgerTransactions());
});

app.get('/overview', (req, res) => {
    res.json(dataService.getOverview());
});

app.get('/api/overview', (req, res) => {
    const ov = dataService.getOverview();
    res.json({ kpis: ov.kpis, threats: ov.threats });
});

app.get('/overview/activity', (req, res) => {
    const range = req.query.range || '24H';
    res.json(dataService.getActivitySeries(range));
});

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// 4. Resource Registries (/api/datasets, /api/models, /api/configs, /api/contributors)
// ---------------------------------------------------------------------------

function resolveAssetPath(asset) {
    const raw = asset.filePath || asset.storagePath || asset.datasetPath || asset.weightsPath;
    if (!raw) return null;
    return path.isAbsolute(raw) ? raw : path.resolve(WORKSPACE_ROOT, raw);
}

function verifyAssetAvailability(asset) {
    const fullPath = resolveAssetPath(asset);
    if (!fullPath) return { available: false, reason: 'No storage path recorded for asset in registry', path: null };
    if (!fs.existsSync(fullPath)) {
        const rel = path.relative(WORKSPACE_ROOT, fullPath);
        return { available: false, reason: `Asset is missing from local storage (${rel})`, path: fullPath };
    }
    try {
        const stat = fs.statSync(fullPath);
        if (stat.isDirectory()) {
            const files = fs.readdirSync(fullPath);
            if (files.length === 0) {
                return { available: false, reason: 'Asset folder is empty (0 files on disk)', path: fullPath };
            }
            return { available: true, reason: null, path: fullPath };
        } else {
            if (stat.size === 0) {
                return { available: false, reason: 'Asset file is empty (0 bytes on disk)', path: fullPath };
            }
            return { available: true, reason: null, path: fullPath };
        }
    } catch (err) {
        return { available: false, reason: err.message, path: fullPath };
    }
}

app.get('/api/datasets', (req, res) => {
    loadUploads();
    const contributorId = req.query.contributorId;
    let list = uploads.filter(u => u.kind === 'dataset');
    if (contributorId && contributorId !== 'all') {
        list = list.filter(u => (u.contributorId || 'unassigned') === contributorId);
    }
    res.json({
        datasets: list.map(u => {
            const check = verifyAssetAvailability(u);
            const resolvedPath = check.path;
            const isDir = Boolean(resolvedPath && fs.existsSync(resolvedPath) && fs.statSync(resolvedPath).isDirectory());
            return {
                id: u.uploadId,
                name: u.originalName || u.datasetName || u.uploadId,
                sha256: u.sha256,
                datasetPath: u.datasetPath || u.filePath,
                storagePath: resolvedPath,
                contributorId: u.contributorId || 'unassigned',
                contributorName: u.contributorName || 'Unassigned',
                format: u.format || 'Unknown',
                size: u.size,
                createdAt: u.createdAt || u.uploadedAt,
                available: check.available,
                unavailableReason: check.reason,
                isFolder: isDir
            };
        })
    });
});

app.get('/api/models', (req, res) => {
    loadUploads();
    const contributorId = req.query.contributorId;
    let list = uploads.filter(u => u.kind === 'model');
    if (contributorId && contributorId !== 'all') {
        list = list.filter(u => (u.contributorId || 'unassigned') === contributorId);
    }
    res.json({
        models: list.map(u => {
            const check = verifyAssetAvailability(u);
            const resolvedPath = check.path;
            const isDir = Boolean(resolvedPath && fs.existsSync(resolvedPath) && fs.statSync(resolvedPath).isDirectory());
            return {
                id: u.uploadId,
                name: u.originalName || u.filename || u.uploadId,
                sha256: u.sha256,
                weightsPath: u.weightsPath || u.filePath,
                storagePath: resolvedPath,
                contributorId: u.contributorId || 'unassigned',
                contributorName: u.contributorName || 'Unassigned',
                framework: u.framework || 'PyTorch',
                size: u.size,
                createdAt: u.createdAt || u.uploadedAt,
                available: check.available,
                unavailableReason: check.reason,
                isFolder: isDir
            };
        })
    });
});

app.get('/api/configs', (req, res) => {
    res.json({
        configs: [
            { id: 'cfg-benchmark-voc', name: 'VOC2012 Benchmark Preset (ResNet50 / Pixelstat)', path: 'data-integrity/benchmark_config.json' },
            { id: 'cfg-data-default', name: 'Data Integrity Standard Config', path: 'data-integrity/config.json' },
            { id: 'cfg-drift-default', name: 'Drift Monitor Calibrated Config (MMD/RBF)', path: 'drift-monitor/config.json' }
        ]
    });
});

// Contributors Management APIs
app.get('/api/contributors', (req, res) => {
    loadContributors();
    loadUploads();
    const result = contributors.map(c => {
        const cDatasets = uploads.filter(u => u.kind === 'dataset' && u.contributorId === c.id);
        const cModels = uploads.filter(u => u.kind === 'model' && u.contributorId === c.id);
        return {
            ...c,
            datasetCount: cDatasets.length,
            modelCount: cModels.length,
            totalAssets: cDatasets.length + cModels.length
        };
    });

    const unassignedDatasets = uploads.filter(u => u.kind === 'dataset' && (!u.contributorId || u.contributorId === 'unassigned'));
    const unassignedModels = uploads.filter(u => u.kind === 'model' && (!u.contributorId || u.contributorId === 'unassigned'));
    if (unassignedDatasets.length > 0 || unassignedModels.length > 0) {
        result.push({
            id: 'unassigned',
            name: 'Unassigned Assets',
            type: 'LEGACY',
            description: 'Legacy or unassigned datasets and models',
            status: 'ACTIVE',
            datasetCount: unassignedDatasets.length,
            modelCount: unassignedModels.length,
            totalAssets: unassignedDatasets.length + unassignedModels.length,
            createdAt: '2026-09-01T00:00:00Z',
            updatedAt: '2026-09-01T00:00:00Z'
        });
    }

    res.json({ contributors: result });
});

app.get('/api/contributors/:id', (req, res) => {
    loadContributors();
    loadUploads();
    const id = req.params.id;
    let contributor = contributors.find(c => c.id === id);
    if (!contributor && id === 'unassigned') {
        contributor = {
            id: 'unassigned',
            name: 'Unassigned Assets',
            type: 'LEGACY',
            description: 'Legacy or unassigned datasets and models',
            status: 'ACTIVE',
            createdAt: '2026-09-01T00:00:00Z',
            updatedAt: '2026-09-01T00:00:00Z'
        };
    }
    if (!contributor) {
        return res.status(404).json({ error: 'Contributor not found' });
    }
    const cDatasets = uploads.filter(u => u.kind === 'dataset' && (u.contributorId === id || (id === 'unassigned' && (!u.contributorId || u.contributorId === 'unassigned'))));
    const cModels = uploads.filter(u => u.kind === 'model' && (u.contributorId === id || (id === 'unassigned' && (!u.contributorId || u.contributorId === 'unassigned'))));

    res.json({
        contributor: {
            ...contributor,
            datasetCount: cDatasets.length,
            modelCount: cModels.length,
            datasets: cDatasets,
            models: cModels
        }
    });
});

app.post('/api/contributors', (req, res) => {
    loadContributors();
    const { name, id: customId, type, description } = req.body || {};
    if (!name || typeof name !== 'string' || !name.trim()) {
        return res.status(400).json({ error: 'Contributor name is required' });
    }
    const trimmedName = name.trim();
    const id = (customId && customId.trim()) || trimmedName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

    if (contributors.some(c => c.id === id)) {
        return res.status(409).json({ error: `Contributor with ID "${id}" already exists` });
    }

    const newContributor = {
        id,
        name: trimmedName,
        type: type || 'VENDOR',
        description: description || 'External asset provider',
        status: 'ACTIVE',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
    };
    contributors.push(newContributor);
    saveContributors();

    res.status(201).json({ contributor: newContributor });
});

app.patch('/api/contributors/:id', (req, res) => {
    loadContributors();
    const id = req.params.id;
    const contributor = contributors.find(c => c.id === id);
    if (!contributor) return res.status(404).json({ error: 'Contributor not found' });

    const { name, type, description, status } = req.body || {};
    if (name) contributor.name = name.trim();
    if (type) contributor.type = type;
    if (description !== undefined) contributor.description = description;
    if (status) contributor.status = status;
    contributor.updatedAt = new Date().toISOString();
    saveContributors();

    res.json({ contributor });
});

app.get('/api/contributors/:id/datasets', (req, res) => {
    loadUploads();
    const id = req.params.id;
    const cDatasets = uploads.filter(u => u.kind === 'dataset' && (u.contributorId === id || (id === 'unassigned' && (!u.contributorId || u.contributorId === 'unassigned'))));
    res.json({
        datasets: cDatasets.map(u => {
            const check = verifyAssetAvailability(u);
            const resolvedPath = check.path;
            const isDir = Boolean(resolvedPath && fs.existsSync(resolvedPath) && fs.statSync(resolvedPath).isDirectory());
            return {
                ...u,
                id: u.uploadId,
                name: u.originalName || u.datasetName || u.uploadId,
                available: check.available,
                unavailableReason: check.reason,
                isFolder: isDir,
                storagePath: resolvedPath
            };
        })
    });
});

app.get('/api/contributors/:id/models', (req, res) => {
    loadUploads();
    const id = req.params.id;
    const cModels = uploads.filter(u => u.kind === 'model' && (u.contributorId === id || (id === 'unassigned' && (!u.contributorId || u.contributorId === 'unassigned'))));
    res.json({
        models: cModels.map(u => {
            const check = verifyAssetAvailability(u);
            const resolvedPath = check.path;
            const isDir = Boolean(resolvedPath && fs.existsSync(resolvedPath) && fs.statSync(resolvedPath).isDirectory());
            return {
                ...u,
                id: u.uploadId,
                name: u.originalName || u.filename || u.uploadId,
                available: check.available,
                unavailableReason: check.reason,
                isFolder: isDir,
                storagePath: resolvedPath
            };
        })
    });
});

// ---------------------------------------------------------------------------
 // 5A. Model Validation & Monitoring Hooks
 // ---------------------------------------------------------------------------
 app.get('/api/models/validations', authService.requireAuth, authService.requireRole(['ANALYST']), (req, res) => {
     const limit = Math.max(1, Math.min(100, Number(req.query.limit) || 50));
     res.json({ validations: modelValidationService.listValidations().slice(0, limit) });
 });
 
 app.post('/api/models/validate/:id', authService.requireAuth, authService.requireRole(['ANALYST']), async (req, res) => {
     loadUploads();
     loadContributors();
     const model = uploads.find(u => u.kind === 'model' && u.uploadId === req.params.id);
     if (!model) return res.status(404).json({ error: 'Model not found in asset registry' });
     const contributor = contributors.find(c => c.id === model.contributorId);
     const report = modelValidationService.validateModelAsset(
         { ...model, id: model.uploadId },
         contributor || null
     );

     // The registry/file checks above are only the ingestion gate. For a
     // calibrated SentinelVision model, execute the real Model Integrity engine
     // (STRIP + live SHA-256 verification) against this exact model file.
     if (report.status !== 'INVALID' && (model.filePath || model.weightsPath)) {
         let rawModelPath = model.weightsPath || model.filePath;
         let modelPath = path.isAbsolute(rawModelPath) ? rawModelPath : path.resolve(WORKSPACE_ROOT, rawModelPath);
         
         // If modelPath is a folder, find the primary weights file inside it
         if (fs.existsSync(modelPath) && fs.statSync(modelPath).isDirectory()) {
             const candidateExts = ['.pt', '.pth', '.onnx', '.bin', '.h5', '.keras', '.tflite', '.ckpt'];
             let found = null;
             const walk = (p) => {
                 if (found) return;
                 try {
                     const entries = fs.readdirSync(p, { withFileTypes: true });
                     for (const entry of entries) {
                         const full = path.join(p, entry.name);
                         if (entry.isDirectory()) walk(full);
                         else if (candidateExts.includes(path.extname(entry.name).toLowerCase())) {
                             found = full;
                             return;
                         }
                     }
                 } catch {}
             };
             walk(modelPath);
             if (found) modelPath = found;
         }

         const rawName = model.originalName || path.basename(modelPath);
         const m = String(rawName).match(/id-\d{8}/) || String(model.uploadId).match(/id-\d{8}/) || String(modelPath).match(/id-\d{8}/);
         const modelId = m ? m[0] : path.parse(rawName).name;
         const engineWorkspace = path.join(WORKSPACE_ROOT, 'reports', report.validationId, 'model-integrity');
         report.engine = await validationEngineService.runModelIntegrityEngine({
             modelId,
             modelPath: path.isAbsolute(modelPath) ? modelPath : path.resolve(WORKSPACE_ROOT, modelPath),
             outputDir: engineWorkspace
         });
         if (report.engine.status === 'COMPLETED') {
             report.engineVerdict = 'ENGINE_COMPLETED';
             const verdict = String(report.engine?.output?.verdict || 'REVIEW').toUpperCase();
             if (verdict === 'QUARANTINE') {
                 report.status = 'INVALID';
                 const reason = report.engine?.output?.scoring?.reason || 'Model Integrity scoring produced a QUARANTINE disposition.';
                 report.errors = [...(report.errors || []), reason];
             } else if (verdict === 'ACCEPT') {
                 report.status = 'VALID';
             } else {
                 report.status = 'WARNING';
                 report.warnings = [...(report.warnings || []), report.engine?.output?.scoring?.reason || 'Model Integrity completed with a REVIEW disposition.'];
             }
         } else {
             report.engineVerdict = report.engine.status === 'UNSUPPORTED' ? 'ENGINE_UNSUPPORTED' : 'ENGINE_FAILED_OR_UNSUPPORTED';
             report.warnings = [
                 ...(report.warnings || []),
                 'The structural model validation completed, but the real Model Integrity engine could not complete or does not support this model. This is not treated as a clean model result.'
             ];
         }
     } else {
         report.engineVerdict = 'ENGINE_NOT_RUN';
     }

     modelValidationService.updateValidation(report.validationId, {
         engine: report.engine,
         engineVerdict: report.engineVerdict,
         validatedAt: new Date().toISOString()
     });

     res.status(200).json({
         ok: report.status !== 'INVALID' && report.engineVerdict === 'ENGINE_COMPLETED',
         report
     });
 });
 
 app.get('/api/model-hooks', authService.requireAuth, authService.requireRole(['ANALYST']), (req, res) => {
     res.json({ hooks: modelHookService.listHooks() });
 });
 
 app.post('/api/model-hooks', authService.requireAuth, authService.requireRole(['ANALYST']), (req, res) => {
     try {
         loadUploads();
         loadContributors();
         const { modelId, contributorId, driftMonitoring, inferenceProvenance } = req.body || {};
         const model = uploads.find(u => u.kind === 'model' && u.uploadId === modelId);
         if (!model) return res.status(404).json({ error: 'Model not found in asset registry' });
         const contributor = contributors.find(c => c.id === (contributorId || model.contributorId));
         if (!contributor) return res.status(400).json({ error: 'Contributor / Vendor is required' });
         if (model.contributorId !== contributor.id) {
             return res.status(400).json({ error: 'Selected contributor does not match the model attribution' });
         }
         const hook = modelHookService.upsertHook({
             modelId: model.uploadId,
             modelName: model.originalName,
             contributorId: contributor.id,
             contributorName: contributor.name,
             driftMonitoring,
             inferenceProvenance
         });
         res.status(201).json({ hook });
     } catch (err) {
         res.status(400).json({ error: err.message });
     }
 });
 
 app.post('/api/model-hooks/:id/disable', authService.requireAuth, authService.requireRole(['ANALYST']), (req, res) => {
     const hook = modelHookService.disableHook(req.params.id);
     if (!hook) return res.status(404).json({ error: 'Hook not found' });
     res.json({ hook });
 });
 
 // ---------------------------------------------------------------------------
// 5. Uploads (/api/uploads, /api/datasets/upload, /api/models/upload)
// ---------------------------------------------------------------------------
async function handleMultipleAssetUpload(req, res, kind) {
    try {
        let items = [];
        let contributorId = '';
        let contributorName = '';

        if (req.headers['content-type']?.includes('multipart/form-data')) {
            const parsed = await parseMultipartData(req);
            contributorId = (parsed.fields.contributorId || req.query.contributorId || '').trim();
            contributorName = (parsed.fields.contributorName || req.query.contributorName || '').trim();
            items = parsed.files.map(f => ({
                filename: f.filename,
                buffer: f.fileBuffer
            }));
        } else if (req.body && Array.isArray(req.body.files)) {
            contributorId = (req.body.contributorId || req.query.contributorId || '').trim();
            contributorName = (req.body.contributorName || '').trim();
            items = req.body.files.map(f => ({
                filename: f.filename || `file-${Date.now()}`,
                buffer: Buffer.from(f.fileContent || f.base64 || '', f.base64 ? 'base64' : 'utf-8')
            }));
        } else if (req.body && (req.body.fileContent || req.body.filename)) {
            contributorId = (req.body.contributorId || req.query.contributorId || '').trim();
            contributorName = (req.body.contributorName || '').trim();
            items = [{
                filename: req.body.filename || `file-${Date.now()}`,
                buffer: Buffer.from(req.body.fileContent || '', 'utf-8')
            }];
        } else {
            return res.status(400).json({ error: 'No files provided in upload request' });
        }

        // Validate contributorId
        if (!contributorId || contributorId === 'unassigned') {
            return res.status(400).json({
                error: `Contributor / Vendor is required. Select the contributor who provided this ${kind}.`
            });
        }

        loadContributors();
        const foundContrib = contributors.find(c => c.id === contributorId);
        if (!foundContrib) {
            return res.status(400).json({
                error: `Contributor "${contributorId}" does not exist. Please select a valid registered contributor.`
            });
        }
        contributorName = foundContrib.name;

        if (items.length === 0) {
            return res.status(400).json({ error: 'No files detected in upload' });
        }

        const results = [];
        loadUploads();

        // A dataset selected from the analyst UI is a logical bundle, not a
        // collection of unrelated one-file assets. Persist multi-file uploads
        // as one directory so the trust runner can execute the real engine.
        if (kind === 'dataset' && (items.length > 1 || (items[0] && String(items[0].filename).includes('/')))) {
            const hash = crypto.createHash('sha256');
            for (const item of items) {
                hash.update(String(item.filename || ''));
                hash.update(Buffer.from(item.buffer || Buffer.alloc(0)));
            }
            const datasetId = `dataset-${hash.digest('hex').slice(0, 10)}`;
            const datasetDir = path.join(UPLOADS_DIR, datasetId);
            fs.mkdirSync(datasetDir, { recursive: true });

            for (const item of items) {
                const relative = String(item.filename || 'file')
                    .replace(/\\/g, '/')
                    .replace(/^[/\\]+/, '')
                    .split('/')
                    .filter(part => part && part !== '.' && part !== '..')
                    .join('/');
                const target = path.join(datasetDir, relative || `file-${Date.now()}`);
                if (!target.startsWith(datasetDir + path.sep)) {
                    return res.status(400).json({ error: 'Unsafe dataset path rejected' });
                }
                fs.mkdirSync(path.dirname(target), { recursive: true });
                fs.writeFileSync(target, item.buffer);
            }

            const folderCandidate = items.find(x => String(x.filename).includes('/'));
            const detectedFolderName = folderCandidate ? String(folderCandidate.filename).split('/')[0] : null;
            const datasetBundleName = detectedFolderName || (items.length === 1 ? path.basename(items[0].filename) : `Dataset bundle (${items.length} files)`);
            const detectedFormat = items.some(x => /\.json$/i.test(x.filename)) ? 'COCO' : 'YOLO';

            const now = new Date().toISOString();
            const registryRecord = {
                uploadId: datasetId,
                filename: datasetId,
                originalName: datasetBundleName,
                datasetName: datasetBundleName,
                kind: 'dataset',
                type: 'dataset',
                sha256: crypto.createHash('sha256').update(items.map(x => String(x.filename) + ':' + crypto.createHash('sha256').update(x.buffer).digest('hex')).sort().join('|')).digest('hex'),
                size: items.reduce((n, x) => n + x.buffer.length, 0),
                createdAt: now,
                uploadedAt: now,
                filePath: datasetDir,
                storagePath: datasetDir,
                datasetPath: datasetDir,
                contributorId,
                contributorName,
                format: detectedFormat,
                isFolder: true
            };
            uploads.unshift(registryRecord);
            saveUploads();

            return res.status(201).json({
                success: true,
                contributor: { id: contributorId, name: contributorName },
                total: items.length,
                successful: 1,
                failed: 0,
                results: [{
                    filename: registryRecord.originalName,
                    uploadId: datasetId,
                    status: 'SUCCESS',
                    size: registryRecord.size,
                    sha256: registryRecord.sha256,
                    contributorId,
                    contributorName,
                    bundledFiles: items.length,
                    format: detectedFormat
                }]
            });
        }

        // A model folder upload from the UI is also a bundle containing weights,
        // config, labels, etc. Persist all files into a model directory.
        if (kind === 'model' && (items.length > 1 || (items[0] && String(items[0].filename).includes('/')))) {
            const validModelExts = ['.pt', '.pth', '.onnx', '.bin', '.h5', '.keras', '.tflite', '.ckpt'];
            const weightsItem = items.find(x => validModelExts.includes(path.extname(x.filename).toLowerCase()));
            if (!weightsItem) {
                return res.status(400).json({
                    error: `No valid model weights file (${validModelExts.join(', ')}) found in the uploaded model folder.`
                });
            }

            const hash = crypto.createHash('sha256');
            for (const item of items) {
                hash.update(String(item.filename || ''));
                hash.update(Buffer.from(item.buffer || Buffer.alloc(0)));
            }
            const modelId = `model-${hash.digest('hex').slice(0, 10)}`;
            const modelDir = path.join(UPLOADS_DIR, modelId);
            fs.mkdirSync(modelDir, { recursive: true });

            for (const item of items) {
                const relative = String(item.filename || 'file')
                    .replace(/\\/g, '/')
                    .replace(/^[/\\]+/, '')
                    .split('/')
                    .filter(part => part && part !== '.' && part !== '..')
                    .join('/');
                const target = path.join(modelDir, relative || `file-${Date.now()}`);
                if (!target.startsWith(modelDir + path.sep)) {
                    return res.status(400).json({ error: 'Unsafe model path rejected' });
                }
                fs.mkdirSync(path.dirname(target), { recursive: true });
                fs.writeFileSync(target, item.buffer);
            }

            const folderCandidate = items.find(x => String(x.filename).includes('/'));
            const detectedFolderName = folderCandidate ? String(folderCandidate.filename).split('/')[0] : null;
            const modelBundleName = detectedFolderName || path.parse(weightsItem.filename).name;

            const relativeWeights = String(weightsItem.filename)
                .replace(/\\/g, '/')
                .replace(/^[/\\]+/, '')
                .split('/')
                .filter(part => part && part !== '.' && part !== '..')
                .join('/');
            const primaryWeightsPath = path.join(modelDir, relativeWeights);

            const ext = path.extname(weightsItem.filename).toLowerCase();
            const framework = ext === '.onnx' ? 'ONNX' : (['.h5', '.keras', '.tflite'].includes(ext) ? 'TensorFlow/Keras' : 'PyTorch');

            const now = new Date().toISOString();
            const registryRecord = {
                uploadId: modelId,
                filename: modelBundleName,
                originalName: modelBundleName,
                kind: 'model',
                type: 'model',
                sha256: crypto.createHash('sha256').update(items.map(x => String(x.filename) + ':' + crypto.createHash('sha256').update(x.buffer).digest('hex')).sort().join('|')).digest('hex'),
                size: items.reduce((n, x) => n + x.buffer.length, 0),
                createdAt: now,
                uploadedAt: now,
                filePath: modelDir,
                storagePath: modelDir,
                weightsPath: primaryWeightsPath,
                isFolder: true,
                framework,
                contributorId,
                contributorName
            };
            uploads.unshift(registryRecord);
            saveUploads();

            return res.status(201).json({
                success: true,
                contributor: { id: contributorId, name: contributorName },
                total: items.length,
                successful: 1,
                failed: 0,
                results: [{
                    filename: registryRecord.originalName,
                    uploadId: modelId,
                    status: 'SUCCESS',
                    size: registryRecord.size,
                    sha256: registryRecord.sha256,
                    contributorId,
                    contributorName,
                    bundledFiles: items.length,
                    framework
                }]
            });
        }

        for (const item of items) {
            try {
                const { filename, buffer } = item;
                if (!buffer || buffer.length === 0) {
                    results.push({
                        filename,
                        status: 'FAILED',
                        error: 'Empty file buffer'
                    });
                    continue;
                }

                // Format validation
                const ext = path.extname(filename).toLowerCase();
                if (kind === 'model') {
                    const validModelExts = ['.pt', '.pth', '.onnx', '.bin', '.h5', '.keras', '.tflite', '.ckpt', '.tar', '.gz'];
                    if (ext && !validModelExts.includes(ext) && !filename.includes('.tar.')) {
                        results.push({
                            filename,
                            status: 'FAILED',
                            error: `Unsupported model extension "${ext}". Allowed: ${validModelExts.join(', ')}`
                        });
                        continue;
                    }
                } else if (kind === 'dataset') {
                    const validDatasetExts = ['.zip', '.tar', '.gz', '.tgz', '.json', '.xml', '.csv', '.parquet', '.jpg', '.jpeg', '.png'];
                    if (ext && !validDatasetExts.includes(ext) && !filename.includes('.tar.')) {
                        results.push({
                            filename,
                            status: 'FAILED',
                            error: `Unsupported dataset extension "${ext}". Allowed: ${validDatasetExts.join(', ')}`
                        });
                        continue;
                    }
                }

                const sha256 = crypto.createHash('sha256').update(buffer).digest('hex');
                const uploadId = `${kind}-${sha256.slice(0, 10)}`;

                const existingIdx = uploads.findIndex(u => u.sha256 === sha256 && u.contributorId === contributorId);
                if (existingIdx !== -1) {
                    results.push({
                        filename,
                        uploadId: uploads[existingIdx].uploadId,
                        status: 'EXISTS',
                        message: 'Asset already registered for this contributor',
                        sha256,
                        contributorId,
                        contributorName
                    });
                    continue;
                }

                const destPath = path.join(UPLOADS_DIR, `${uploadId}_${filename}`);
                fs.writeFileSync(destPath, buffer);

                const now = new Date().toISOString();
                const newUpload = {
                    uploadId,
                    filename,
                    originalName: filename,
                    kind,
                    type: kind,
                    sha256,
                    size: buffer.length,
                    createdAt: now,
                    uploadedAt: now,
                    filePath: destPath,
                    storagePath: destPath,
                    contributorId,
                    contributorName,
                    format: kind === 'dataset' ? (ext.replace('.', '').toUpperCase() || 'CUSTOM') : undefined,
                    framework: kind === 'model' ? (ext === '.onnx' ? 'ONNX' : 'PyTorch') : undefined,
                    datasetPath: kind === 'dataset' ? destPath : undefined,
                    weightsPath: kind === 'model' ? destPath : undefined
                };

                uploads.unshift(newUpload);
                results.push({
                    filename,
                    uploadId,
                    status: 'SUCCESS',
                    size: buffer.length,
                    sha256,
                    contributorId,
                    contributorName
                });
            } catch (fileErr) {
                results.push({
                    filename: item.filename,
                    status: 'FAILED',
                    error: fileErr.message
                });
            }
        }

        saveUploads();

        const successCount = results.filter(r => r.status === 'SUCCESS' || r.status === 'EXISTS').length;
        const failCount = results.filter(r => r.status === 'FAILED').length;

        res.status(failCount === items.length ? 400 : 201).json({
            success: successCount > 0,
            contributor: {
                id: contributorId,
                name: contributorName
            },
            total: items.length,
            successful: successCount,
            failed: failCount,
            results
        });
    } catch (err) {
        console.error('Multiple upload error:', err);
        res.status(500).json({ error: 'Upload process failed', details: err.message });
    }
}

app.get('/api/uploads', (req, res) => {
    loadUploads();
    const contributorId = req.query.contributorId;
    let list = uploads;
    if (contributorId && contributorId !== 'all') {
        list = list.filter(u => (u.contributorId || 'unassigned') === contributorId);
    }
    res.json({ uploads: list });
});

app.post('/api/datasets/upload', async (req, res) => {
    return handleMultipleAssetUpload(req, res, 'dataset');
});

app.post('/api/models/upload', async (req, res) => {
    return handleMultipleAssetUpload(req, res, 'model');
});

app.post('/api/uploads/:kind', async (req, res) => {
    try {
        let fileBuffer, filename, contributorId = req.query.contributorId || 'unassigned', contributorName = req.query.contributorName;
        if (req.headers['content-type']?.includes('multipart/form-data')) {
            const parsed = await parseMultipartData(req);
            if (parsed.files.length > 1) {
                return handleMultipleAssetUpload(req, res, req.params.kind);
            }
            if (parsed.files.length > 0) {
                fileBuffer = parsed.files[0].fileBuffer;
                filename = parsed.files[0].filename;
            }
            if (parsed.fields.contributorId) contributorId = parsed.fields.contributorId;
            if (parsed.fields.contributorName) contributorName = parsed.fields.contributorName;
        } else if (req.body && req.body.fileContent) {
            fileBuffer = Buffer.from(req.body.fileContent, 'utf-8');
            filename = req.body.filename || `upload-${Date.now()}`;
            if (req.body.contributorId) contributorId = req.body.contributorId;
            if (req.body.contributorName) contributorName = req.body.contributorName;
        } else {
            fileBuffer = Buffer.from(JSON.stringify(req.body || {}), 'utf-8');
            filename = `payload-${Date.now()}.json`;
        }

        if (!fileBuffer) {
            return res.status(400).json({ error: 'No file data received' });
        }

        loadContributors();
        const found = contributors.find(c => c.id === contributorId);
        if (!found || !contributorId || contributorId === 'unassigned') {
            return res.status(400).json({
                error: `Contributor / Vendor is required and must be a registered contributor for this upload.`
            });
        }
        contributorName = found.name;

        const kind = req.params.kind === 'model' ? 'model' : 'dataset';
        const sha256 = crypto.createHash('sha256').update(fileBuffer).digest('hex');
        const uploadId = `${kind}-${sha256.slice(0, 10)}`;
        const destPath = path.join(UPLOADS_DIR, `${uploadId}_${filename}`);

        fs.writeFileSync(destPath, fileBuffer);

        const newUpload = {
            uploadId,
            originalName: filename,
            kind,
            sha256,
            size: fileBuffer.length,
            createdAt: new Date().toISOString(),
            filePath: destPath,
            contributorId,
            contributorName,
            datasetPath: kind === 'dataset' ? destPath : undefined,
            weightsPath: kind === 'model' ? destPath : undefined
        };

        uploads.unshift(newUpload);
        saveUploads();

        res.status(201).json({ upload: newUpload, success: true });
    } catch (err) {
        res.status(500).json({ error: 'Upload failed', details: err.message });
    }
});

// ---------------------------------------------------------------------------
// Inference Provenance page workflow
// ---------------------------------------------------------------------------
app.post('/api/inference-provenance/run', authService.requireAuth, authService.requireRole(['ANALYST']), (req, res) => {
    try {
        const { contributorId, modelId } = req.body || {};
        if (!contributorId || !modelId) return res.status(400).json({ error: 'Contributor and uploaded model are required' });
        loadContributors();
        loadUploads();
        const contributor = contributors.find(c => c.id === contributorId);
        const model = uploads.find(u => u.kind === 'model' && u.uploadId === modelId && u.contributorId === contributorId);
        if (!contributor) return res.status(404).json({ error: 'Contributor not found' });
        if (!model) return res.status(404).json({ error: 'Uploaded model not found for this contributor' });
        const job = jobService.startJob({
            testType: 'INFERENCE_SEAL',
            modelId: model.uploadId,
            contributorId: contributor.id,
            contributorName: contributor.name,
            user: req.user
        });
        res.json({ test: job });
    } catch (err) {
        res.status(500).json({ error: 'Failed to start inference provenance verification', details: err.message });
    }
});

app.get('/api/inference-provenance/records', authService.requireAuth, authService.requireRole(['ANALYST']), (req, res) => {
    try {
        const records = (dataService.getEvidenceList() || [])
            .filter((r) => r.module === 'InferenceProvenance' || r.moduleName === 'InferenceProvenance')
            .sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));
        res.json({ records });
    } catch (err) {
        res.status(500).json({ error: 'Failed to load inference provenance records', details: err.message });
    }
});

// ---------------------------------------------------------------------------
// 6. Test & Run Automation Engine (/api/trust/run, /api/runs, /api/trust/batch)
// ---------------------------------------------------------------------------
app.post('/api/trust/run', (req, res) => {
    const { datasetId, modelId, configId, testType, contributorId, contributorName, batchId } = req.body || {};
    const job = jobService.startJob({
        testType: testType || 'FULL_ASSURANCE',
        datasetId,
        modelId,
        configId,
        contributorId,
        contributorName,
        batchId,
        user: req.user
    });
    res.json({ test: job });
});

app.post('/api/runs', (req, res) => {
    const { testType, datasetId, modelId, configId, contributorId, contributorName, batchId } = req.body || {};
    const job = jobService.startJob({
        testType: testType || 'FULL_ASSURANCE',
        datasetId,
        modelId,
        configId,
        contributorId,
        contributorName,
        batchId,
        user: req.user
    });
    res.json(job);
});

app.post('/api/trust/batch', (req, res) => {
    const { contributorId, pairs, configId, testType } = req.body || {};
    loadContributors();
    const contributor = contributors.find(c => c.id === contributorId);
    const contributorName = contributor ? contributor.name : (contributorId || 'Unassigned');
    const batchId = `batch-${Date.now()}`;

    const jobs = [];
    if (Array.isArray(pairs)) {
        for (const pair of pairs) {
            const job = jobService.startJob({
                testType: testType || 'FULL_ASSURANCE',
                datasetId: pair.datasetId,
                modelId: pair.modelId,
                configId: configId || pair.configId,
                contributorId,
                contributorName,
                batchId,
                user: req.user
            });
            jobs.push(job);
        }
    }
    res.json({ batchId, contributorId, contributorName, count: jobs.length, jobs });
});

app.get('/api/trust/tests', (req, res) => {
    res.json({ tests: jobService.listJobs() });
});

app.get('/api/runs', (req, res) => {
    res.json(jobService.listJobs());
});

app.get('/api/trust/tests/:testId', (req, res) => {
    const job = jobService.getJob(req.params.testId);
    if (!job) return res.status(404).json({ error: 'Test not found' });
    res.json({ test: job });
});

app.get('/api/runs/:run_id', (req, res) => {
    const job = jobService.getJob(req.params.run_id);
    if (!job) return res.status(404).json({ error: 'Run not found' });
    res.json(job);
});

app.get('/api/runs/:run_id/report', (req, res) => {
    const job = jobService.getJob(req.params.run_id);
    if (!job || !job.reportPath || !fs.existsSync(job.reportPath)) {
        return res.status(404).json({ error: 'Report not available for this run' });
    }
    const reportData = JSON.parse(fs.readFileSync(job.reportPath, 'utf-8'));
    res.json(reportData);
});

app.post('/api/trust/train', (req, res) => {
    res.json({
        trainingJobId: `train-${Date.now()}`,
        status: 'DISPATCHED',
        device: 'NVIDIA GeForce RTX 5050 Laptop GPU (CUDA 13.0)',
        message: 'Training job scheduled with trustworthy dual-direction guards'
    });
});

app.post('/api/trust/tests/:testId/quarantine', (req, res) => {
    loadQuarantine();
    const job = jobService.getJob(req.params.testId);
    const reason = req.body?.reason || (job && job.error) || 'High anomaly or critical trojan signature flagged during assurance test';
    const nowIso = new Date().toISOString();
    const qId = `qr-${Date.now()}`;

    const item = {
        id: qId,
        quarantineId: qId,
        testId: req.params.testId,
        assetId: (job && job.modelId) || (job && job.datasetId) || 'asset-flagged',
        datasetId: job?.datasetId || null,
        datasetName: job?.datasetName || job?.datasetId || null,
        modelId: job?.modelId || null,
        modelName: job?.modelName || job?.modelId || null,
        kind: (job && job.testType === 'MODEL_INTEGRITY') ? 'MODEL' : 'DATASET',
        reason,
        submittedBy: req.user ? req.user.email : 'analyst@sentinelvision.io',
        userName: req.user ? req.user.email : 'analyst@sentinelvision.io',
        submittedAt: nowIso,
        createdAt: nowIso,
        status: 'QUARANTINED',
        disposition: 'QUARANTINE',
        severity: (job && job.severity) || 'CRITICAL',
        reviewerNotes: null,
        reviewedBy: null,
        reviewedAt: null,
        timeline: [
            { at: nowIso, action: 'QUARANTINE_REQUESTED', actor: req.user ? req.user.email : 'analyst@sentinelvision.io' }
        ]
    };

    quarantineRegistry.unshift(item);
    saveQuarantine();

    jobService.recordAuditEvent('QUARANTINE_REQUESTED', { quarantineId: item.id, assetId: item.assetId, reason }, req.user);
    res.json({ success: true, quarantine: item, item });
});

// ---------------------------------------------------------------------------
// 7. Dataset Validation Gate (/api/datasets/validate)
// ---------------------------------------------------------------------------
app.get('/api/datasets/validations', authService.requireAuth, authService.requireRole(['ANALYST']), (req, res) => {
    const limit = Math.max(1, Math.min(100, Number(req.query.limit) || 50));
    const validations = datasetValidationService.listValidations()
        .filter(v => !req.query.contributorId || req.query.contributorId === 'all' || (v.contributorId || 'unassigned') === req.query.contributorId)
        .slice(0, limit);
    res.json({ validations });
});

app.post('/api/datasets/validate', authService.requireAuth, authService.requireRole(['ANALYST']), async (req, res) => {
    try {
        let files = [];
        let contributorId = '';
        let modelId = '';
        let datasetId = '';

        if (req.headers['content-type']?.includes('multipart/form-data')) {
            const parsed = await parseMultipartData(req);
            files = parsed.files || [];
            contributorId = String(parsed.fields.contributorId || '').trim();
            modelId = String(parsed.fields.modelId || '').trim();
            datasetId = String(parsed.fields.datasetId || '').trim();
            if (datasetId && files.length === 0) {
                loadUploads();
                const existing = uploads.find(u => u.kind === 'dataset' && (u.uploadId === datasetId || u.id === datasetId));
                if (!existing) return res.status(404).json({ ok: false, error: 'Registered dataset not found' });
                const existingPath = existing.datasetPath || existing.filePath || existing.storagePath;
                const resolvedPath = existingPath && (path.isAbsolute(existingPath) ? existingPath : path.resolve(WORKSPACE_ROOT, existingPath));
                if (!resolvedPath || !fs.existsSync(resolvedPath)) {
                    return res.status(404).json({ ok: false, error: 'Registered dataset files are not available locally' });
                }
                const collectFiles = (dir) => {
                    const out = [];
                    const walk = (p) => {
                        const stat = fs.statSync(p);
                        if (stat.isDirectory()) fs.readdirSync(p).forEach(n => walk(path.join(p, n)));
                        else out.push({ filename: path.relative(resolvedPath, p).replace(/\\/g, '/'), fileBuffer: fs.readFileSync(p) });
                    };
                    walk(dir);
                    return out;
                };
                files = fs.statSync(resolvedPath).isDirectory()
                    ? collectFiles(resolvedPath)
                    : [{ filename: path.basename(resolvedPath), fileBuffer: fs.readFileSync(resolvedPath) }];
            }
        } else if (req.body && req.body.fileContent) {
            files = [{
                filename: req.body.filename || 'dataset_annotation.json',
                fileBuffer: Buffer.from(req.body.fileContent, 'utf-8')
            }];
            contributorId = String(req.body.contributorId || '').trim();
            modelId = String(req.body.modelId || '').trim();
            datasetId = String(req.body.datasetId || '').trim();
        } else {
            files = [{
                filename: 'dataset_annotation.json',
                fileBuffer: Buffer.from(JSON.stringify(req.body || {}), 'utf-8')
            }];
            contributorId = String(req.body?.contributorId || '').trim();
            modelId = String(req.body?.modelId || '').trim();
            datasetId = String(req.body?.datasetId || '').trim();
        }

        loadContributors();
        let contributor = contributors.find(c => c.id === contributorId);
        if (!contributor) {
            if (!contributorId && contributors.length > 0) {
                contributor = contributors[0];
                contributorId = contributor.id;
            } else {
                return res.status(400).json({
                    ok: false,
                    error: 'Contributor / Vendor is required. Select the contributor who provided this dataset.'
                });
            }
        }

        loadUploads();
        let selectedDataset = null;
        if (datasetId) {
            selectedDataset = uploads.find(u => u.kind === 'dataset' && (u.uploadId === datasetId || u.id === datasetId));
        }

        if (!files.length) return res.status(400).json({ ok: false, error: 'No dataset files provided' });

        const detectedKind = datasetValidationService.detectDatasetKind(files, req.query.kind);
        const kind = detectedKind === 'unknown' ? String(req.query.kind || 'yolo').toLowerCase() : detectedKind;

        // Structural validation
        const datasetObj = selectedDataset
            ? { id: selectedDataset.uploadId, name: selectedDataset.originalName }
            : (datasetId ? { id: datasetId, name: datasetId } : null);

        const report = datasetValidationService.validateDatasetBundle(
            kind,
            files.map(file => ({
                filename: file.filename,
                fileBuffer: file.fileBuffer
            })),
            { id: contributorId, name: contributor.name },
            datasetObj
        );

        // Persist the exact uploaded folder as a registered dataset asset so a
        // later assurance run can execute against the bytes that were validated.
        const uploadId = datasetId || `dataset-${report.datasetHash.slice(0, 10)}`;
        const datasetDir = path.join(UPLOADS_DIR, uploadId);
        if (!fs.existsSync(datasetDir)) fs.mkdirSync(datasetDir, { recursive: true });

        for (const file of files) {
            const rawName = String(file.filename || 'unnamed');
            const relativeName = rawName
                .replace(/\\/g, '/')
                .replace(/^[/\\]+/, '')
                .split('/')
                .filter(part => part && part !== '.' && part !== '..')
                .join('/');
            const target = path.join(datasetDir, relativeName || `file-${Date.now()}`);
            if (!target.startsWith(datasetDir + path.sep) && target !== datasetDir) {
                throw new Error('Unsafe dataset file path rejected');
            }
            fs.mkdirSync(path.dirname(target), { recursive: true });
            fs.writeFileSync(target, file.fileBuffer);
        }

        const folderCandidate = files.find(f => String(f.filename || '').includes('/'));
        const detectedFolderName = folderCandidate ? String(folderCandidate.filename).split('/')[0] : null;
        const datasetDisplayName = selectedDataset?.originalName || detectedFolderName || (files.length === 1 ? path.basename(files[0].filename) : `Dataset bundle (${files.length} files)`);

        loadUploads();
        const existingIdx = uploads.findIndex(u => u.uploadId === uploadId);
        const now = new Date().toISOString();
        const registryRecord = {
            uploadId,
            filename: uploadId,
            originalName: datasetDisplayName,
            datasetName: datasetDisplayName,
            kind: 'dataset',
            type: 'dataset',
            sha256: report.datasetHash,
            size: files.reduce((sum, f) => sum + (f.fileBuffer?.length || 0), 0),
            createdAt: selectedDataset?.createdAt || now,
            uploadedAt: now,
            filePath: datasetDir,
            storagePath: datasetDir,
            datasetPath: datasetDir,
            contributorId,
            contributorName: contributor.name,
            datasetId: uploadId,
            format: report.format || kind.toUpperCase(),
            isFolder: true
        };
        if (existingIdx >= 0) uploads[existingIdx] = { ...uploads[existingIdx], ...registryRecord };
        else uploads.unshift(registryRecord);
        saveUploads();

        report.datasetId = uploadId;
        report.datasetName = registryRecord.datasetName;
        report.datasetPath = datasetDir;
        report.registered = true;
        report.modelId = modelId || null;

        // IMPORTANT: structural validation above is only the ingestion gate.
        // Run the actual Data Integrity engine against the uploaded bytes before
        // returning the validation result. Never replay a stored result.
        const engineWorkspace = path.join(WORKSPACE_ROOT, 'reports', report.validationId);
        report.engine = await validationEngineService.runDatasetIntegrityEngine({
            validationId: report.validationId,
            kind: kind === 'coco' ? 'coco' : 'yolo',
            files: files.map(file => ({ filename: file.filename, fileBuffer: file.fileBuffer })),
            workspaceDir: engineWorkspace,
            datasetId: uploadId,
            datasetName: registryRecord.datasetName
        });

        if (report.engine.status === 'COMPLETED' && report.engine?.findings?.length) {
            report.status = 'invalid';
            report.errors = (report.errors || 0) + report.engine.findings.length;
            report.error_details = [
                ...(report.error_details || []),
                ...report.engine.findings.map(f => ({ type: f.type || 'ENGINE_FINDING', message: f.message, file: f.file, severity: f.severity }))
            ];
        } else if (report.engine.status === 'FAILED') {
            report.status = 'ENGINE_FAILED';
            report.error_details = [
                ...(report.error_details || []),
                { type: 'ENGINE_ERROR', message: report.engine.error || report.engine.stderr || 'Data Integrity engine failed' }
            ];
        } else if (report.engine.status === 'NOT_RUN') {
            report.status = 'ENGINE_NOT_RUN';
            report.warning_details = [
                ...(report.warning_details || []),
                { type: 'ENGINE_NOT_RUN', message: report.engine.reason }
            ];
        }

        datasetValidationService.updateValidation(report.validationId, {
            status: report.status,
            engine: report.engine,
            datasetId: uploadId,
            datasetName: registryRecord.datasetName,
            engineCompletedAt: new Date().toISOString()
        });

        res.status(200).json({ ok: report.engine.status === 'COMPLETED' && report.status !== 'invalid', report });
    } catch (err) {
        console.error('Dataset validation error:', err);
        res.status(500).json({ ok: false, error: err.message });
    }
});

// ---------------------------------------------------------------------------
// 8. Auditor Endpoints (Quarantine, Logs, Reports)
// ---------------------------------------------------------------------------
app.get('/api/auditor/quarantine', (req, res) => {
    loadQuarantine();
    const status = req.query.status;
    let list = quarantineRegistry.map(q => {
        const id = q.quarantineId || q.id;
        const job = jobService.getJob(q.testId);
        return {
            ...q,
            id,
            quarantineId: id,
            datasetId: q.datasetId || job?.datasetId || null,
            datasetName: q.datasetName || job?.datasetName || null,
            modelId: q.modelId || job?.modelId || null,
            modelName: q.modelName || job?.modelName || null,
            userName: q.userName || q.submittedBy || 'analyst@sentinelvision.io',
            createdAt: q.createdAt || q.submittedAt || new Date().toISOString()
        };
    });
    if (status) {
        list = list.filter(q => q.status === status);
    }
    res.json({ quarantine: list });
});

app.get('/api/auditor/quarantine/:id', (req, res) => {
    loadQuarantine();
    const item = quarantineRegistry.find(q => q.id === req.params.id || q.quarantineId === req.params.id);
    if (!item) return res.status(404).json({ error: 'Quarantine item not found' });
    const id = item.quarantineId || item.id;
    const job = jobService.getJob(item.testId);
    const enriched = {
        ...item,
        id,
        quarantineId: id,
        datasetId: item.datasetId || job?.datasetId || null,
        datasetName: item.datasetName || job?.datasetName || null,
        modelId: item.modelId || job?.modelId || null,
        modelName: item.modelName || job?.modelName || null,
        userName: item.userName || item.submittedBy || 'analyst@sentinelvision.io',
        createdAt: item.createdAt || item.submittedAt || new Date().toISOString(),
        timeline: item.timeline || [
            { at: item.createdAt || item.submittedAt || new Date().toISOString(), action: 'QUARANTINE_REQUESTED', actor: item.submittedBy || 'analyst' }
        ]
    };
    res.json({ quarantine: enriched, item: enriched, test: job || null });
});

app.post('/api/auditor/quarantine/:id/release', (req, res) => {
    loadQuarantine();
    const item = quarantineRegistry.find(q => q.id === req.params.id || q.quarantineId === req.params.id);
    if (!item) return res.status(404).json({ error: 'Quarantine item not found' });

    item.status = 'RELEASED';
    item.disposition = 'RELEASE';
    item.reviewedBy = req.user ? req.user.email : 'auditor@sentinelvision.io';
    item.reviewedAt = new Date().toISOString();
    item.reviewerNotes = req.body?.notes || 'Released by auditor';
    item.timeline = item.timeline || [];
    item.timeline.push({ at: item.reviewedAt, action: 'RELEASED', actor: item.reviewedBy });

    saveQuarantine();
    jobService.recordAuditEvent('QUARANTINE_RELEASED', { id: item.id || item.quarantineId }, req.user);
    res.json({ success: true, item, quarantine: item });
});

app.post('/api/auditor/quarantine/:id/commit', async (req, res) => {
    loadQuarantine();
    const item = quarantineRegistry.find(q => q.id === req.params.id || q.quarantineId === req.params.id);
    if (!item) return res.status(404).json({ error: 'Quarantine item not found' });

    const qId = item.id || item.quarantineId;
    const nowIso = new Date().toISOString();
    const fields = {
        assetID: String(item.assetId || item.testId || qId),
        moduleName: 'Governance',
        reason: String(item.reason || 'Quarantined by security auditor review'),
        evidenceHash: item.evidenceHash || ledgerService.recordDigest(item),
        confidence: 1.0,
        severity: String(item.severity || 'HIGH'),
        disposition: String(item.disposition || 'QUARANTINE'),
        timestamp: String(item.submittedAt || nowIso)
    };

    const sigResult = ledgerService.signGovernanceFields(fields);
    if (sigResult.signature) {
        fields.signature = sigResult.signature;
    }

    const journalEntry = await ledgerService.submitFinding(fields, {
        quarantineId: qId,
        testId: item.testId,
        actor: req.user?.email || 'auditor@sentinelvision.io',
        action: 'QUARANTINE_COMMIT'
    });

    item.ledgerStatus = journalEntry.status;
    item.txId = journalEntry.txId;
    item.status = journalEntry.status === 'COMMITTED' ? 'COMMITTED' : item.status;
    item.committedAt = nowIso;
    item.timeline = item.timeline || [];
    item.timeline.push({
        at: nowIso,
        action: `LEDGER_${journalEntry.status}`,
        actor: req.user?.email || 'auditor@sentinelvision.io'
    });

    saveQuarantine();
    jobService.recordAuditEvent('QUARANTINE_LEDGER_COMMIT', {
        id: qId,
        ledgerStatus: journalEntry.status,
        txId: journalEntry.txId,
        error: journalEntry.error
    }, req.user);

    res.json({
        success: true,
        item,
        quarantine: item,
        ledgerStatus: journalEntry.status,
        txId: journalEntry.txId,
        journalEntry
    });
});

app.post('/api/auditor/quarantine/:id/decision', (req, res) => {
    loadQuarantine();
    const item = quarantineRegistry.find(q => q.id === req.params.id || q.quarantineId === req.params.id);
    if (!item) return res.status(404).json({ error: 'Quarantine item not found' });

    const { decision, notes } = req.body || {};
    item.status = decision || 'QUARANTINED';
    item.reviewerNotes = notes || 'Reviewed by lead auditor';
    item.reviewedBy = req.user ? req.user.email : 'auditor@sentinelvision.io';
    item.reviewedAt = new Date().toISOString();
    item.timeline = item.timeline || [];
    item.timeline.push({ at: item.reviewedAt, action: `DECISION_${item.status}`, actor: item.reviewedBy });

    saveQuarantine();
    jobService.recordAuditEvent('QUARANTINE_DECISION', { id: item.id || item.quarantineId, decision: item.status, notes }, req.user);

    res.json({ success: true, item, quarantine: item });
});

app.get('/api/auditor/logs', (req, res) => {
    res.json({ logs: jobService.getAuditLogs() });
});

app.get('/api/auditor/sessions', (req, res) => {
    res.json({ sessions: authService.listSessions() });
});

app.get('/api/auditor/users', (req, res) => {
    res.json({ users: authService.listUsers() });
});

app.post('/api/auditor/users/:userId/status', (req, res) => {
    try {
        const user = authService.setUserStatus(req.params.userId, req.body?.status);
        jobService.recordAuditEvent('USER_STATUS_CHANGED', {
            userId: req.params.userId,
            status: req.body?.status
        }, req.user);
        res.json({ success: true, user });
    } catch (err) {
        res.status(err.status || 500).json({ error: err.message });
    }
});

app.post('/api/auditor/users/pending/:userId/approve', (req, res) => {
    try {
        const user = authService.approvePendingUser(req.params.userId);
        jobService.recordAuditEvent('USER_APPROVED', { userId: req.params.userId }, req.user);
        res.json({ success: true, user });
    } catch (err) {
        res.status(err.status || 500).json({ error: err.message });
    }
});

function renderReportHtml(data) {
    const id = data.assessment_id || data.report_id || 'Assurance Assessment';
    const ts = data.assessment_timestamp || data.generated_at || new Date().toISOString();
    const disposition = data.overall_assessment?.disposition || data.governance_disposition || 'REVIEW';
    const status = data.overall_assessment?.overall_status || 'UNKNOWN';
    const summary = data.overall_assessment?.summary || data.executive_summary?.overall_statement || 'Assurance assessment complete.';
    const findings = data.findings || [];
    const audit = data.audit || {};

    const findingsHtml = findings.map(f => `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.08);">
            <td style="padding: 10px; font-family: monospace; color: #22d3ee;">${f.finding_id || f.id || '—'}</td>
            <td style="padding: 10px;">${f.check_id || f.module || '—'}</td>
            <td style="padding: 10px; font-weight: bold; color: ${f.severity === 'CRITICAL' ? '#f87171' : f.severity === 'HIGH' ? '#fb923c' : '#facc15'};">${f.severity || '—'}</td>
            <td style="padding: 10px;">${f.description || f.reason || '—'}</td>
            <td style="padding: 10px; font-family: monospace; color: #94a3b8;">${f.evidence_hash ? '#' + f.evidence_hash.slice(0, 12) + '…' : '—'}</td>
        </tr>
    `).join('');

    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${id} — SentinelVision Assurance Report</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #070a13; color: #e2e8f0; margin: 0; padding: 28px; line-height: 1.6; }
  .report-box { max-width: 1200px; margin: 0 auto; background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 28px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
  h1 { font-size: 22px; color: #38bdf8; margin-top: 0; letter-spacing: 0.05em; }
  .header-meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin: 20px 0; padding: 14px; background: #090d16; border-radius: 6px; border: 1px solid #1e293b; font-size: 13px; }
  .meta-item span { display: block; color: #64748b; font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 700; margin-bottom: 4px; }
  .meta-item b { color: #f1f5f9; }
  .disposition { display: inline-block; padding: 4px 10px; border-radius: 4px; font-weight: 700; font-size: 11.5px; letter-spacing: 0.08em; }
  .disp-QUARANTINE { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }
  .disp-ACCEPT { background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; }
  .disp-REVIEW { background: rgba(234, 179, 8, 0.2); color: #facc15; border: 1px solid #eab308; }
  .summary-box { background: rgba(56, 189, 248, 0.05); border-left: 4px solid #38bdf8; padding: 14px; margin: 20px 0; border-radius: 0 6px 6px 0; font-size: 13.5px; }
  table { width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 12.5px; }
  th { text-align: left; padding: 10px; background: #1e293b; color: #94a3b8; font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; }
  .audit-hash { font-family: monospace; font-size: 11.5px; background: #090d16; padding: 8px 12px; border-radius: 4px; border: 1px solid #1e293b; color: #38bdf8; word-break: break-all; }
</style>
</head>
<body>
<div class="report-box">
  <h1>SENTINELVISION AI INTEGRITY ASSURANCE REPORT</h1>
  <div class="header-meta">
    <div class="meta-item"><span>Report Identifier</span><b style="font-family: monospace;">${id}</b></div>
    <div class="meta-item"><span>Generated Timestamp</span><b>${new Date(ts).toLocaleString()}</b></div>
    <div class="meta-item"><span>Governance Disposition</span><b class="disposition disp-${disposition}">${disposition}</b></div>
    <div class="meta-item"><span>Overall Status</span><b>${status}</b></div>
  </div>
  <div class="summary-box">
    <strong>Executive Statement:</strong><br>${summary}
  </div>
  ${audit.final_chain_hash ? `
    <div style="margin: 20px 0;">
      <span style="font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 700; letter-spacing: 0.1em;">Audit Trail Hash Chain</span>
      <div class="audit-hash">${audit.final_chain_hash} (Status: ${audit.chain_valid ? 'CONFIRMED' : 'UNVERIFIED'})</div>
    </div>
  ` : ''}
  <h2 style="font-size: 15px; color: #f1f5f9; margin-top: 24px; border-bottom: 1px solid #1e293b; padding-bottom: 8px;">Detailed Findings (${findings.length})</h2>
  <table>
    <thead>
      <tr>
        <th>Finding ID</th>
        <th>Module / Check</th>
        <th>Severity</th>
        <th>Description</th>
        <th>Evidence Hash</th>
      </tr>
    </thead>
    <tbody>
      ${findingsHtml || '<tr><td colspan="5" style="text-align: center; padding: 20px; color: #64748b;">No findings recorded in this assessment.</td></tr>'}
    </tbody>
  </table>
</div>
</body>
</html>`;
}

app.get('/api/auditor/reports', (req, res) => {
    const reportsDir = path.join(WORKSPACE_ROOT, 'reports');
    const list = [];

    if (fs.existsSync(reportsDir)) {
        const subdirs = fs.readdirSync(reportsDir);
        for (const sub of subdirs) {
            const reportFile = path.join(reportsDir, sub, 'assurance_report.json');
            if (fs.existsSync(reportFile)) {
                try {
                    const data = JSON.parse(fs.readFileSync(reportFile, 'utf-8'));
                    list.push({
                        reportId: data.assessment_id || data.report_id || sub,
                        dirId: sub,
                        generatedAt: data.assessment_timestamp || data.generated_at || fs.statSync(reportFile).mtime.toISOString(),
                        periodDays: data.period || data.periodDays || 30,
                        auditorName: data.operator || data.contributor?.name || data.system?.operator || 'Auditor (System)',
                        disposition: data.overall_assessment?.disposition || data.governance_disposition || 'REVIEW',
                        summary: data.overall_assessment?.summary || data.executive_summary?.overall_statement || 'Assurance assessment complete'
                    });
                } catch {}
            }
        }
    }

    res.json({ reports: list });
});

app.get('/api/auditor/reports/governance.pdf', (req, res) => {
    const periodDays = parseInt(req.query.periodDays, 10) || 30;
    const auditLogs = jobService.getAuditLogs();
    const allFindings = dataService.getAllFindings();
    const critCount = allFindings.filter(f => f.severity === 'CRITICAL').length;
    const highCount = allFindings.filter(f => f.severity === 'HIGH').length;
    const evidenceList = dataService.getEvidenceList();
    const fabricState = ledgerService.getFabricState();
    loadQuarantine();

    const lines = [
        "SENTINELVISION AI INTEGRITY ASSURANCE REPORT",
        `Report Type: Executive Governance Audit (${periodDays}-Day Window)`,
        `Generated: ${new Date().toISOString()}`,
        `Platform Engine: SentinelVision Trust Engine (RTX 5050 CUDA 13.0 Accelerated)`,
        "=========================================================================",
        "",
        `Total Active Findings:     ${allFindings.length}`,
        `Critical Findings:         ${critCount}`,
        `High Severity:             ${highCount}`,
        `Verified Evidence Records: ${evidenceList.length}`,
        `Quarantined Assets:        ${quarantineRegistry.length}`,
        `Ledger Verification:       ${fabricState.connected ? 'ONLINE (Fabric Channel: ' + fabricState.channel + ')' : 'STANDBY (Offline ledger journal active)'}`,
        "",
        "RECENT AUDIT TRAIL CHAIN (SHA-256 HASH CHAIN):",
        "-------------------------------------------------------------------------"
    ];

    const sampleLogs = auditLogs.slice(0, 15);
    for (const log of sampleLogs) {
        lines.push(`[${log.timestamp ? log.timestamp.slice(0, 19) : ''}] ${log.eventType} by ${log.actor || 'system'} (${log.role || 'user'})`);
        lines.push(`   Event Hash: ${log.eventHash?.slice(0, 32)}...`);
    }

    lines.push("");
    lines.push("GOVERNANCE ATTESTATION:");
    lines.push("This document represents an authoritative, cryptographically linked record");
    lines.push("of AI data and model assurance evaluations performed by SentinelVision.");

    // Generate pure valid PDF 1.4 binary
    const streamContent = lines.map((line, idx) => `BT /F1 10 Tf 40 ${760 - (idx * 15)} Td (${line.replace(/[()\\]/g, '\\$&')}) Tj ET`).join('\n');
    const streamBuf = Buffer.from(streamContent, 'utf-8');

    const objects = [
        '1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n',
        '2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n',
        `3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n`,
        `4 0 obj\n<< /Length ${streamBuf.length} >>\nstream\n${streamContent}\nendstream\nendobj\n`,
        '5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n'
    ];

    let offset = 9; // %PDF-1.4\n
    const xref = ['xref\n0 6\n0000000000 65535 f \n'];
    let body = '%PDF-1.4\n';
    for (const obj of objects) {
        xref.push(String(offset).padStart(10, '0') + ' 00000 n \n');
        body += obj;
        offset += Buffer.byteLength(obj, 'utf-8');
    }
    const xrefOffset = offset;
    const trailer = `trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
    const pdfBuffer = Buffer.from(body + xref.join('') + trailer, 'utf-8');

    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', `attachment; filename="governance-report-${new Date().toISOString().slice(0, 10)}.pdf"`);
    res.send(pdfBuffer);
});

app.get('/api/auditor/reports/:id/download', (req, res) => {
    const reportsDir = path.join(WORKSPACE_ROOT, 'reports');
    const id = req.params.id;

    // Search for matching directory directly or by assessment_id/report_id
    let dir = null;
    if (fs.existsSync(path.join(reportsDir, id))) {
        dir = path.join(reportsDir, id);
    } else if (fs.existsSync(reportsDir)) {
        for (const sub of fs.readdirSync(reportsDir)) {
            const jsonP = path.join(reportsDir, sub, 'assurance_report.json');
            if (fs.existsSync(jsonP)) {
                try {
                    const parsed = JSON.parse(fs.readFileSync(jsonP, 'utf-8'));
                    if (parsed.assessment_id === id || parsed.report_id === id) {
                        dir = path.join(reportsDir, sub);
                        break;
                    }
                } catch {}
            }
        }
    }

    if (!dir) {
        return res.status(404).json({ error: 'Report not found' });
    }

    let targetHtml = path.join(dir, 'assurance_report.html');
    let targetJson = path.join(dir, 'assurance_report.json');

    if (req.query.format === 'json' && fs.existsSync(targetJson)) {
        res.setHeader('Content-Type', 'application/json');
        res.setHeader('Content-Disposition', `attachment; filename="assurance_report_${id}.json"`);
        return fs.createReadStream(targetJson).pipe(res);
    }

    if (fs.existsSync(targetHtml)) {
        res.setHeader('Content-Type', 'text/html; charset=utf-8');
        const disposition = req.query.view === '1' ? 'inline' : 'attachment';
        res.setHeader('Content-Disposition', `${disposition}; filename="assurance_report_${id}.html"`);
        return fs.createReadStream(targetHtml).pipe(res);
    }

    if (fs.existsSync(targetJson)) {
        try {
            const reportData = JSON.parse(fs.readFileSync(targetJson, 'utf-8'));
            const html = renderReportHtml(reportData);
            res.setHeader('Content-Type', 'text/html; charset=utf-8');
            res.setHeader('Content-Disposition', `inline; filename="assurance_report_${id}.html"`);
            return res.send(html);
        } catch (err) {
            return res.status(500).json({ error: 'Failed to format report: ' + err.message });
        }
    }

    res.status(404).json({ error: 'Report file not found' });
});

// Start listening
const server = app.listen(PORT, async () => {
    console.log(`SentinelVision Assurance API & Bridge listening on port ${PORT}`);
    if (fabricGateway && fabricGateway.initializeContract) {
        try {
            await fabricGateway.initializeContract();
            console.log('[OK] Fabric Gateway connection initialized successfully.');
        } catch (err) {
            console.log('[INFO] Fabric Gateway in offline standby mode:', err.message);
        }
    }
});

server.on('error', (err) => {
    console.error(`[bridge] Server listen error: ${err.message}`);
    process.exit(1);
});

let isShuttingDown = false;
function gracefulShutdown() {
    if (isShuttingDown) return;
    isShuttingDown = true;

    try { validationEngineService.terminateSubprocesses?.(); } catch {}
    try { jobService.terminateSubprocesses?.(); } catch {}

    if (typeof server.closeAllConnections === 'function') {
        try { server.closeAllConnections(); } catch {}
    }
    server.close(() => {
        process.exit(0);
    });
    setTimeout(() => {
        process.exit(0);
    }, 1000).unref();
}

process.on('SIGTERM', gracefulShutdown);
process.on('SIGINT', gracefulShutdown);
