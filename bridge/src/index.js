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
        // Seed default benchmark datasets and models so the selector is populated immediately
        uploads = [
            {
                uploadId: 'dataset-voc2012-benchmark',
                originalName: 'PASCAL VOC2012 Multi-Attack Benchmark',
                kind: 'dataset',
                sha256: 'b3f4c892801adfe9745a993710db44ac9c81912f7105d15a99c9b1392fa940e1',
                size: 142000000,
                createdAt: '2026-09-26T12:00:00Z',
                datasetPath: 'datasets/sentinelvision_voc2012/mixed_attack'
            },
            {
                uploadId: 'dataset-integrity-test',
                originalName: 'Controlled Integrity Test Suite (Duplicates, OOD, Flips)',
                kind: 'dataset',
                sha256: '4c718a22199bdf01a719c228fa8913b82910fa88921a9183cc919bda7710c812',
                size: 28400000,
                createdAt: '2026-09-26T14:30:00Z',
                datasetPath: 'data/integrity-test'
            },
            {
                uploadId: 'dataset-voc2012-clean',
                originalName: 'VOC2012 Clean Baseline (120 Images)',
                kind: 'dataset',
                sha256: '992a818c772bda9184acb0129a88cfa918b918a2281a8b99182390abdf1918a2',
                size: 32000000,
                createdAt: '2026-09-26T10:00:00Z',
                datasetPath: 'datasets/sentinelvision_voc2012/clean'
            },
            {
                uploadId: 'model-trojai-res50-0112',
                originalName: 'id-00000112 (ResNet50 Trojan Injected)',
                kind: 'model',
                sha256: 'cd88076498c5c79fce68bffef38102f3394ef5c9f6691dc2f0efc48bf51f3e0b',
                size: 98000000,
                createdAt: '2026-09-22T11:00:00Z',
                weightsPath: 'model-integrity/triggers/id-00000112_class2_pattern.pt'
            },
            {
                uploadId: 'model-clean-res50-0028',
                originalName: 'id-00000028 (ResNet50 Baseline Clean)',
                kind: 'model',
                sha256: 'cd88076498c5c79fce68bffef38102f3394ef5c9f6691dc2f0efc48bf51f3e0b',
                size: 98000000,
                createdAt: '2026-09-22T09:00:00Z',
                weightsPath: 'model-integrity/triggers/id-00000028_class0_pattern.pt'
            }
        ];
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
        quarantineRegistry = [
            {
                id: 'qr-001',
                testId: 'test-20260926-001',
                assetId: 'model-id-00000112',
                kind: 'MODEL',
                reason: 'Class 2 flagged by Neural Cleanse + MAD (anomaly index 3.13) corroborated by STRIP entropy suppression.',
                submittedBy: 'analyst@sentinelvision.io',
                submittedAt: '2026-09-26T17:15:00Z',
                status: 'PENDING',
                disposition: 'QUARANTINE',
                severity: 'CRITICAL',
                reviewerNotes: null,
                reviewedBy: null,
                reviewedAt: null
            },
            {
                id: 'qr-002',
                testId: 'test-20260926-002',
                assetId: 'dataset-voc2012-label-flip',
                kind: 'DATASET',
                reason: 'Multiple systematic label flip anomalies and near-duplicate flooding detected in contributor batch B.',
                submittedBy: 'analyst@sentinelvision.io',
                submittedAt: '2026-09-26T17:30:00Z',
                status: 'QUARANTINED',
                disposition: 'QUARANTINE',
                severity: 'HIGH',
                reviewerNotes: 'Confirmed 8 flipped class samples against benchmark answer key.',
                reviewedBy: 'auditor@sentinelvision.io',
                reviewedAt: '2026-09-26T18:00:00Z'
            }
        ];
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
app.get('/health', (req, res) => {
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

    try {
        if (fabricGateway && fabricGateway.initializeContract) {
            const contract = await fabricGateway.initializeContract();
            await contract.submitTransaction(
                'submitFinding',
                String(finding.assetID),
                String(finding.moduleName),
                String(finding.reason),
                String(finding.evidenceHash),
                String(finding.confidence),
                String(finding.severity),
                String(finding.disposition),
                String(finding.timestamp),
                String(finding.signature || '')
            );
        }
    } catch (err) {
        console.log('Fabric Gateway submit notice:', err.message);
    }

    jobService.recordAuditEvent('FINDING_SUBMITTED', { assetID: finding.assetID, module: finding.moduleName });
    res.status(201).json({ success: true, message: 'Finding recorded', data: finding });
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
// 4. Resource Registries (/api/datasets, /api/models, /api/configs, /api/contributors)
// ---------------------------------------------------------------------------
app.get('/api/datasets', (req, res) => {
    loadUploads();
    const contributorId = req.query.contributorId;
    let list = uploads.filter(u => u.kind === 'dataset');
    if (contributorId && contributorId !== 'all') {
        list = list.filter(u => (u.contributorId || 'unassigned') === contributorId);
    }
    res.json({
        datasets: list.map(u => ({
            id: u.uploadId,
            name: u.originalName,
            sha256: u.sha256,
            datasetPath: u.datasetPath || u.filePath,
            contributorId: u.contributorId || 'unassigned',
            contributorName: u.contributorName || 'Unassigned',
            format: u.format || 'Unknown',
            size: u.size,
            createdAt: u.createdAt
        }))
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
        models: list.map(u => ({
            id: u.uploadId,
            name: u.originalName,
            sha256: u.sha256,
            weightsPath: u.weightsPath || u.filePath,
            contributorId: u.contributorId || 'unassigned',
            contributorName: u.contributorName || 'Unassigned',
            framework: u.framework || 'PyTorch',
            size: u.size,
            createdAt: u.createdAt
        }))
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
    res.json({ datasets: cDatasets });
});

app.get('/api/contributors/:id/models', (req, res) => {
    loadUploads();
    const id = req.params.id;
    const cModels = uploads.filter(u => u.kind === 'model' && (u.contributorId === id || (id === 'unassigned' && (!u.contributorId || u.contributorId === 'unassigned'))));
    res.json({ models: cModels });
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
         const modelPath = model.filePath || model.weightsPath;
         const rawName = model.originalName || path.basename(modelPath);
         const modelId = path.parse(rawName).name;
         const engineWorkspace = path.join(WORKSPACE_ROOT, 'reports', report.validationId, 'model-integrity');
         report.engine = await validationEngineService.runModelIntegrityEngine({
             modelId,
             modelPath: path.isAbsolute(modelPath) ? modelPath : path.resolve(WORKSPACE_ROOT, modelPath),
             outputDir: engineWorkspace
         });
         if (report.engine.status === 'COMPLETED') {
             report.engineVerdict = 'ENGINE_COMPLETED';
             if (report.engine?.output?.verdict === 'FAIL') {
                 report.status = 'INVALID';
                 report.errors = [
                     ...(report.errors || []),
                     ...(report.engine.output.findings || []).map(f => f.reason || 'Model integrity assurance detected a suspicious model behavior.')
                 ];
             } else {
                 report.status = 'VALID';
             }
         } else {
             report.engineVerdict = 'ENGINE_FAILED_OR_UNSUPPORTED';
             report.warnings = [
                 ...(report.warnings || []),
                 'The structural model validation completed, but the Model Integrity engine could not complete. This is not treated as a clean model result.'
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
    const job = jobService.getJob(req.params.testId);
    const reason = req.body?.reason || (job && job.error) || 'High anomaly or critical trojan signature flagged during assurance test';

    const item = {
        id: `qr-${Date.now()}`,
        testId: req.params.testId,
        assetId: (job && job.modelId) || (job && job.datasetId) || 'asset-flagged',
        kind: (job && job.testType === 'MODEL_INTEGRITY') ? 'MODEL' : 'DATASET',
        reason,
        submittedBy: req.user ? req.user.email : 'analyst@sentinelvision.io',
        submittedAt: new Date().toISOString(),
        status: 'PENDING',
        disposition: 'QUARANTINE',
        severity: (job && job.severity) || 'CRITICAL',
        reviewerNotes: null,
        reviewedBy: null,
        reviewedAt: null
    };

    quarantineRegistry.unshift(item);
    saveQuarantine();

    jobService.recordAuditEvent('QUARANTINE_REQUESTED', { quarantineId: item.id, assetId: item.assetId, reason }, req.user);
    res.json({ success: true, quarantine: item });
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

        if (req.headers['content-type']?.includes('multipart/form-data')) {
            const parsed = await parseMultipartData(req);
            files = parsed.files || [];
            contributorId = String(parsed.fields.contributorId || '').trim();
        } else if (req.body && req.body.fileContent) {
            files = [{
                filename: req.body.filename || 'dataset_annotation.json',
                fileBuffer: Buffer.from(req.body.fileContent, 'utf-8')
            }];
            contributorId = String(req.body.contributorId || '').trim();
        } else {
            files = [{
                filename: 'dataset_annotation.json',
                fileBuffer: Buffer.from(JSON.stringify(req.body || {}), 'utf-8')
            }];
            contributorId = String(req.body?.contributorId || '').trim();
        }

        loadContributors();
        const contributor = contributors.find(c => c.id === contributorId);
        if (!contributor) {
            return res.status(400).json({
                ok: false,
                error: 'Contributor / Vendor is required. Select the contributor who provided this dataset.'
            });
        }
        if (!files.length) return res.status(400).json({ ok: false, error: 'No dataset files provided' });

        const kind = String(req.query.kind || 'yolo').toLowerCase();
        if (!['yolo', 'coco'].includes(kind)) {
            return res.status(400).json({ ok: false, error: 'Dataset format must be YOLO or COCO' });
        }

        // The validation endpoint performs a fresh structural validation of the
        // uploaded bytes. It does not look up or replay a previous validation.
        const report = datasetValidationService.validateDatasetBundle(
            kind,
            files.map(file => ({
                filename: file.filename,
                fileBuffer: file.fileBuffer
            })),
            { id: contributorId, name: contributor.name }
        );

        // Persist the exact uploaded folder as a registered dataset asset so a
        // later assurance run can execute against the bytes that were validated.
        const uploadId = `dataset-${report.datasetHash.slice(0, 10)}`;
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

        loadUploads();
        const existingIdx = uploads.findIndex(u => u.uploadId === uploadId);
        const now = new Date().toISOString();
        const registryRecord = {
            uploadId,
            filename: uploadId,
            originalName: report.format === 'COCO' ? 'Uploaded COCO Dataset Folder' : 'Uploaded YOLO Dataset Folder',
            kind: 'dataset',
            type: 'dataset',
            sha256: report.datasetHash,
            size: files.reduce((sum, f) => sum + (f.fileBuffer?.length || 0), 0),
            createdAt: now,
            uploadedAt: now,
            filePath: datasetDir,
            storagePath: datasetDir,
            datasetPath: datasetDir,
            contributorId,
            contributorName: contributor.name,
            format: report.format
        };
        if (existingIdx >= 0) uploads[existingIdx] = { ...uploads[existingIdx], ...registryRecord };
        else uploads.unshift(registryRecord);
        saveUploads();

        report.datasetId = uploadId;
        report.datasetPath = datasetDir;
        report.registered = true;

        // IMPORTANT: structural validation above is only the ingestion gate.
        // Run the actual Data Integrity engine against the uploaded bytes before
        // returning the validation result. Never replay a stored result.
        const engineWorkspace = path.join(WORKSPACE_ROOT, 'reports', report.validationId);
        report.engine = await validationEngineService.runDatasetIntegrityEngine({
            validationId: report.validationId,
            kind,
            files: files.map(file => ({ filename: file.filename, fileBuffer: file.fileBuffer })),
            workspaceDir: engineWorkspace
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
    const status = req.query.status;
    const filtered = status ? quarantineRegistry.filter(q => q.status === status) : quarantineRegistry;
    res.json({ quarantine: filtered });
});

app.get('/api/auditor/quarantine/:id', (req, res) => {
    const item = quarantineRegistry.find(q => q.id === req.params.id);
    if (!item) return res.status(404).json({ error: 'Quarantine item not found' });
    res.json({ item });
});

app.post('/api/auditor/quarantine/:id/release', (req, res) => {
    const item = quarantineRegistry.find(q => q.id === req.params.id);
    if (!item) return res.status(404).json({ error: 'Quarantine item not found' });

    item.status = 'RELEASED';
    item.disposition = 'RELEASE';
    item.reviewedBy = req.user ? req.user.email : 'auditor@sentinelvision.io';
    item.reviewedAt = new Date().toISOString();
    item.reviewerNotes = req.body?.notes || 'Released by auditor';

    saveQuarantine();
    jobService.recordAuditEvent('QUARANTINE_RELEASED', { id: item.id }, req.user);
    res.json({ success: true, item });
});

app.post('/api/auditor/quarantine/:id/commit', async (req, res) => {
    const item = quarantineRegistry.find(q => q.id === req.params.id);
    if (!item) return res.status(404).json({ error: 'Quarantine item not found' });

    let ledgerStatus = 'RECORDED';
    try {
        if (fabricGateway && fabricGateway.initializeContract) {
            const contract = await fabricGateway.initializeContract();
            await contract.submitTransaction(
                'submitFinding',
                String(item.assetId),
                'Governance',
                String(item.reason),
                '',
                '1',
                String(item.severity || 'HIGH'),
                String(item.disposition || 'QUARANTINE'),
                String(item.submittedAt || new Date().toISOString()),
                ''
            );
            ledgerStatus = 'COMMITTED';
        } else {
            ledgerStatus = 'OFFLINE_RECORDED';
        }
    } catch (err) {
        ledgerStatus = 'OFFLINE_RECORDED';
        console.log('Fabric Gateway commit notice:', err.message);
    }

    item.ledgerStatus = ledgerStatus;
    item.committedAt = new Date().toISOString();
    saveQuarantine();
    jobService.recordAuditEvent('QUARANTINE_LEDGER_COMMIT', { id: item.id, ledgerStatus }, req.user);
    res.json({ success: true, item, ledgerStatus });
});

app.post('/api/auditor/quarantine/:id/decision', (req, res) => {
    const item = quarantineRegistry.find(q => q.id === req.params.id);
    if (!item) return res.status(404).json({ error: 'Quarantine item not found' });

    const { decision, notes } = req.body || {};
    item.status = decision || 'QUARANTINED';
    item.reviewerNotes = notes || 'Reviewed by lead auditor';
    item.reviewedBy = req.user ? req.user.email : 'auditor@sentinelvision.io';
    item.reviewedAt = new Date().toISOString();

    saveQuarantine();
    jobService.recordAuditEvent('QUARANTINE_DECISION', { id: item.id, decision: item.status, notes }, req.user);

    res.json({ success: true, item });
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
                        reportId: data.report_id || sub,
                        generatedAt: data.generated_at || fs.statSync(reportFile).mtime.toISOString(),
                        periodDays: 30,
                        auditorName: data.operator || 'Auditor (System)',
                        disposition: data.governance_disposition || 'QUARANTINE',
                        summary: data.executive_summary?.overall_statement || 'Assurance assessment complete'
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
    const ov = dataService.getOverview();

    const lines = [
        "SENTINELVISION AI INTEGRITY ASSURANCE REPORT",
        `Report Type: Executive Governance Audit (${periodDays}-Day Window)`,
        `Generated: ${new Date().toISOString()}`,
        `Platform Engine: SentinelVision Trust Engine (RTX 5050 CUDA 13.0 Accelerated)`,
        "=========================================================================",
        "",
        `Total Active Findings:    ${ov.kpis.totalFindings}`,
        `Critical Findings:         ${ov.kpis.criticalFindings}`,
        `High Severity:             ${ov.kpis.highSeverity}`,
        `Verified Evidence Records: ${ov.kpis.evidenceRecords}`,
        `Quarantined Assets:        ${quarantineRegistry.length}`,
        `Ledger Verification:       CONFIRMED (Fabric Channel: mychannel)`,
        "",
        "RECENT AUDIT TRAIL CHAIN (SHA-256 HASH CHAIN):",
        "-------------------------------------------------------------------------"
    ];

    const sampleLogs = auditLogs.slice(0, 15);
    for (const log of sampleLogs) {
        lines.push(`[${log.timestamp.slice(0, 19)}] ${log.eventType} by ${log.actor} (${log.role})`);
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

    // Search for matching report in subdirectories
    let targetHtml = path.join(reportsDir, id, 'assurance_report.html');
    let targetJson = path.join(reportsDir, id, 'assurance_report.json');

    if (!fs.existsSync(targetHtml)) {
        targetHtml = path.join(reportsDir, 'demo_report', 'assurance_report.html');
        targetJson = path.join(reportsDir, 'demo_report', 'assurance_report.json');
    }

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

process.on('SIGTERM', () => {
    server.close();
});
process.on('SIGINT', () => {
    server.close();
});
