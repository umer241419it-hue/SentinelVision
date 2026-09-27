'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const crypto = require('crypto');

const WORKSPACE_ROOT = path.resolve(__dirname, '../../../');
const RUN_LOGS_DIR = path.join(WORKSPACE_ROOT, 'reports/runs');
const JOBS_FILE = path.join(WORKSPACE_ROOT, 'data/jobs.json');
const AUDIT_FILE = path.join(WORKSPACE_ROOT, 'data/audit_trail.json');
const UPLOADS_META_FILE = path.join(WORKSPACE_ROOT, 'data/uploads_meta.json');
const CONTRIBUTORS_FILE = path.join(WORKSPACE_ROOT, 'data/contributors.json');

for (const dir of [RUN_LOGS_DIR, path.dirname(JOBS_FILE)]) {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

let jobs = {};
let auditTrail = [];

function loadState() {
    try { if (fs.existsSync(JOBS_FILE)) jobs = JSON.parse(fs.readFileSync(JOBS_FILE, 'utf-8')); } catch { jobs = {}; }
    try { if (fs.existsSync(AUDIT_FILE)) auditTrail = JSON.parse(fs.readFileSync(AUDIT_FILE, 'utf-8')); } catch { auditTrail = []; }
}
function saveState() {
    try {
        fs.writeFileSync(JOBS_FILE, JSON.stringify(jobs, null, 2), 'utf-8');
        fs.writeFileSync(AUDIT_FILE, JSON.stringify(auditTrail, null, 2), 'utf-8');
    } catch (err) { console.error('Failed to save job/audit state:', err.message); }
}
loadState();

function recordAuditEvent(eventType, payload, user = null) {
    const prevHash = auditTrail.length ? auditTrail[auditTrail.length - 1].eventHash : '0'.repeat(64);
    const event = {
        eventId: `ev-${crypto.randomBytes(6).toString('hex')}`,
        eventType,
        timestamp: new Date().toISOString(),
        actor: user ? user.email : 'system',
        role: user ? user.role : 'SYSTEM',
        payload,
        previousHash: prevHash
    };
    event.eventHash = crypto.createHash('sha256')
        .update(`${event.eventId}|${event.eventType}|${event.timestamp}|${event.actor}|${JSON.stringify(event.payload)}|${prevHash}`)
        .digest('hex');
    auditTrail.push(event);
    saveState();
    return event;
}

function loadContributors() {
    try {
        return fs.existsSync(CONTRIBUTORS_FILE)
            ? JSON.parse(fs.readFileSync(CONTRIBUTORS_FILE, 'utf-8'))
            : [];
    } catch {
        return [];
    }
}

function loadUploads() {
    try {
        return fs.existsSync(UPLOADS_META_FILE)
            ? JSON.parse(fs.readFileSync(UPLOADS_META_FILE, 'utf-8'))
            : [];
    } catch {
        return [];
    }
}

function resolveAsset(assetId, kind) {
    if (!assetId) return null;
    const item = loadUploads().find(u => u.uploadId === assetId && u.kind === kind);
    if (!item) return null;
    const relative = kind === 'dataset' ? item.datasetPath : item.weightsPath;
    const candidate = relative
        ? (path.isAbsolute(relative) ? relative : path.resolve(WORKSPACE_ROOT, relative))
        : item.filePath;
    return { ...item, resolvedPath: candidate };
}

function resolveConfig(configId, fallback) {
    const map = {
        'cfg-data-default': path.join(WORKSPACE_ROOT, 'data-integrity/config.json'),
        'cfg-benchmark-voc': path.join(WORKSPACE_ROOT, 'data-integrity/benchmark_config.json'),
        'cfg-drift-default': path.join(WORKSPACE_ROOT, 'drift-monitor/config.json')
    };
    const p = map[configId] || fallback;
    return fs.existsSync(p) ? p : fallback;
}

function makeEnv() {
    return {
        ...process.env,
        PYTHONPATH: [
            WORKSPACE_ROOT,
            path.join(WORKSPACE_ROOT, 'crypto-utils'),
            path.join(WORKSPACE_ROOT, 'data-integrity'),
            path.join(WORKSPACE_ROOT, 'model-integrity'),
            path.join(WORKSPACE_ROOT, 'inference-provenance/src'),
            path.join(WORKSPACE_ROOT, 'drift-monitor')
        ].join(':')
    };
}

function runCommand(command, args, cwd, env, logStream, onOutput) {
    return new Promise((resolve) => {
        const child = spawn(command, args, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'] });
        const write = (chunk, stderr = false) => {
            const text = chunk.toString();
            logStream.write(text);
            onOutput?.(text, stderr);
        };
        child.stdout.on('data', c => write(c));
        child.stderr.on('data', c => write(c, true));
        child.on('error', err => resolve({ code: -1, error: err.message }));
        child.on('close', code => resolve({ code: code ?? -1 }));
    });
}

function setCheck(job, key, status, details) {
    job.checks[key] = { status, ...(details ? { details } : {}) };
    saveState();
}

function summarizeData(job, resultPath = null) {
    const p = resultPath || path.join(WORKSPACE_ROOT, 'data-integrity/results/integrity_results.json');
    if (!fs.existsSync(p)) return;
    try {
        const r = JSON.parse(fs.readFileSync(p, 'utf-8'));
        if (Array.isArray(r.sample_findings)) {
            const n = r.sample_findings.length;
            const groups = Array.isArray(r.group_analysis?.group_findings) ? r.group_analysis.group_findings.length : 0;
            job.findingsCount = n + groups;
            job.trustStatus = n > 0 || groups > 0 ? 'WARNING' : 'PASS';
            job.disposition = n > 0 || groups > 0 ? 'REVIEW' : 'ACCEPT';
            setCheck(job, 'DATA_INTEGRITY', job.trustStatus === 'PASS' ? 'PASS' : 'WARNING',
                `${n} sample findings and ${groups} group-level findings from the unified integrity scan.`);
        } else {
            const s = r.summary || {};
            const n = Number(s.images_flagged || 0);
            job.findingsCount = n;
            job.trustStatus = n > 0 ? 'WARNING' : 'PASS';
            job.disposition = n > 0 ? 'REVIEW' : 'ACCEPT';
            setCheck(job, 'DATA_INTEGRITY', job.trustStatus === 'PASS' ? 'PASS' : 'WARNING',
                `${n} findings across ${s.images_checked || 0} samples; checks: ${(s.checks_run || []).join(', ')}`);
        }
    } catch (err) {
        setCheck(job, 'DATA_INTEGRITY', 'FAIL', `Could not parse integrity results: ${err.message}`);
    }
}

function summarizeModel(job, resultPath = null) {
    const p = resultPath || path.join(WORKSPACE_ROOT, 'model-integrity/findings.json');
    if (!fs.existsSync(p)) return;
    try {
        const findings = JSON.parse(fs.readFileSync(p, 'utf-8'));
        const list = Array.isArray(findings) ? findings : [];
        const critical = list.filter(f => ['CRITICAL', 'HIGH'].includes(String(f.severity || '').toUpperCase()));
        job.findingsCount = Math.max(job.findingsCount || 0, list.length);
        const status = critical.length ? 'FAIL' : list.length ? 'WARNING' : 'PASS';
        job.trustStatus = status;
        job.disposition = status === 'FAIL' ? 'QUARANTINE' : status === 'WARNING' ? 'REVIEW' : 'ACCEPT';
        setCheck(job, 'MODEL_INTEGRITY', status,
            `${list.length} model findings; ${critical.length} high/critical`);
    } catch (err) {
        setCheck(job, 'MODEL_INTEGRITY', 'FAIL', `Could not parse model findings: ${err.message}`);
    }
}

function summarizeDrift(job, resultPath = null) {
    const p = resultPath || path.join(WORKSPACE_ROOT, 'drift-monitor/results/drift_results.json');
    if (!fs.existsSync(p)) return;
    try {
        const r = JSON.parse(fs.readFileSync(p, 'utf-8'));
        const results = Array.isArray(r.results) ? r.results : [];
        const alerts = results.filter(x => x.assessment && x.assessment !== 'STABLE');
        const status = alerts.length ? 'WARNING' : 'PASS';
        setCheck(job, 'DATA_DRIFT', status, `${alerts.length} non-stable windows out of ${results.length}`);
        if (status === 'WARNING' && job.trustStatus === 'PASS') {
            job.trustStatus = 'WARNING';
            job.disposition = 'REVIEW';
        }
    } catch (err) {
        setCheck(job, 'DATA_DRIFT', 'FAIL', `Could not parse drift results: ${err.message}`);
    }
}

async function executeJob(job, normType, dataset, model, configId, logStream) {
    const env = makeEnv();
    const datasetPath = dataset?.resolvedPath;
    const modelIdForDetector = model?.originalName || model?.uploadId || null;

    const dataConfig = resolveConfig(configId, path.join(WORKSPACE_ROOT, 'data-integrity/config.json'));
    const driftConfig = resolveConfig(configId === 'cfg-drift-default' ? configId : null, path.join(WORKSPACE_ROOT, 'drift-monitor/config.json'));

    const run = async (label, command, args, cwd) => {
        job.currentStep = label;
        saveState();
        logStream.write(`\n--- ${label} ---\nCommand: ${command} ${args.join(' ')}\n`);
        const result = await runCommand(command, args, cwd, env, logStream);
        if (result.code !== 0) throw new Error(`${label} exited with code ${result.code}${result.error ? `: ${result.error}` : ''}`);
    };

    if (normType === 'DATA_INTEGRITY' || normType === 'FULL_ASSURANCE' || normType === 'TRUST_CHECK') {
        if (!datasetPath || !fs.existsSync(datasetPath) || !fs.statSync(datasetPath).isDirectory()) {
            throw new Error('Selected dataset is not an executable image-directory dataset. Upload/registry entries must resolve to a directory containing labeled images and a labels sidecar.');
        }
        const labels = path.join(datasetPath, 'label_key.json');
        if (!fs.existsSync(labels)) {
            throw new Error(`No label_key.json found for selected dataset: ${datasetPath}`);
        }
        const isUnifiedDataset = fs.existsSync(path.join(datasetPath, 'JPEGImages')) &&
            fs.existsSync(path.join(datasetPath, 'Annotations'));
        if (isUnifiedDataset) {
            const scanOutputDir = path.join(WORKSPACE_ROOT, 'reports', job.run_id, 'data-integrity');
            fs.mkdirSync(scanOutputDir, { recursive: true });
            await run('DATA INTEGRITY', 'python3', [
                'sentinelvision_cli.py', 'integrity', 'scan',
                '--dataset', datasetPath,
                '--config', dataConfig,
                '--output-dir', scanOutputDir
            ], WORKSPACE_ROOT);
            job.dataResultsPath = path.join(scanOutputDir, 'scan_findings.json');
            summarizeData(job, job.dataResultsPath);
        } else {
            await run('DATA INTEGRITY', 'python3', [
                '-m', 'src.run_data_integrity',
                '--config', dataConfig,
                '--input', datasetPath,
                '--labels', labels,
                '--checks', 'duplicate,ood,label_flip',
                '--run-id', job.run_id
            ], path.join(WORKSPACE_ROOT, 'data-integrity'));
            summarizeData(job);
        }
    }

    if (normType === 'MODEL_INTEGRITY' || normType === 'FULL_ASSURANCE' || normType === 'TRUST_CHECK') {
        if (!model) {
            if (normType === 'MODEL_INTEGRITY') throw new Error('A model must be selected for MODEL_INTEGRITY.');
            setCheck(job, 'MODEL_INTEGRITY', 'SKIPPED', 'No model was selected.');
        } else {
            fs.mkdirSync(path.join(WORKSPACE_ROOT, 'reports', job.run_id, 'model-integrity'), { recursive: true });
            await run('MODEL INTEGRITY', 'python3', [
                'src/strip_detector.py',
                '--model-path', model.resolvedPath,
                '--model-id', path.parse(model.originalName || path.basename(model.resolvedPath)).name,
                '--output', path.join(WORKSPACE_ROOT, 'reports', job.run_id, 'model-integrity', 'strip_results.json'),
                '--hashes-output', path.join(WORKSPACE_ROOT, 'reports', job.run_id, 'model-integrity', 'strip_hashes.json')
            ], path.join(WORKSPACE_ROOT, 'model-integrity'));
            job.modelResultsPath = path.join(WORKSPACE_ROOT, 'reports', job.run_id, 'model-integrity', 'strip_results.json');
            summarizeModel(job, job.modelResultsPath);
        }
    }

    if (normType === 'DISTRIBUTION_SHIFT' || normType === 'DATA_DRIFT' || normType === 'FULL_ASSURANCE' || normType === 'TRUST_CHECK') {
        if (!datasetPath || !fs.existsSync(datasetPath) || !fs.statSync(datasetPath).isDirectory()) {
            throw new Error('Selected dataset cannot be used as the drift input.');
        }
        const driftOutput = path.join(WORKSPACE_ROOT, 'reports', job.run_id, 'drift-monitor', 'drift_results.json');
        fs.mkdirSync(path.dirname(driftOutput), { recursive: true });
        await run('DISTRIBUTION SHIFT', 'python3', [
            '-m', 'src.run_drift_monitor',
            '--config', driftConfig,
            '--input', datasetPath,
            '--run-id', job.run_id,
            '--output', driftOutput
        ], path.join(WORKSPACE_ROOT, 'drift-monitor'));
        job.driftResultsPath = driftOutput;
        summarizeDrift(job, driftOutput);
    }

    if (normType === 'INFERENCE_INTEGRITY' || normType === 'INFERENCE_SEAL' || normType === 'FULL_ASSURANCE' || normType === 'TRUST_CHECK') {
        await run('INFERENCE PROVENANCE', 'python3', ['inference-provenance/src/demo_verify_full.py'], WORKSPACE_ROOT);
        setCheck(job, 'INFERENCE_SEAL', 'PASS', 'Inference provenance verification completed.');
    }

    if (normType === 'FULL_ASSURANCE' || normType === 'TRUST_CHECK') {
        const reportOutputDir = path.join(WORKSPACE_ROOT, 'reports', job.run_id);
        fs.mkdirSync(reportOutputDir, { recursive: true });
        const reportArgs = [
            '-m', 'governance.cli', 'assess',
            '--data-results', job.dataResultsPath || path.join(WORKSPACE_ROOT, 'data-integrity/results/integrity_results.json'),
            '--model-findings', job.modelResultsPath || path.join(WORKSPACE_ROOT, 'model-integrity/findings.json'),
            '--drift-results', job.driftResultsPath || path.join(WORKSPACE_ROOT, 'drift-monitor/results/drift_results.json'),
            '--inference-records', path.join(WORKSPACE_ROOT, 'inference-provenance/seal_coverage_results.json'),
            '--output', reportOutputDir
        ];
        if (job.contributorId && job.contributorId !== 'unassigned') {
            reportArgs.push('--contributor-id', job.contributorId);
            reportArgs.push('--contributor-name', job.contributorName || job.contributorId);
        }
        if (job.datasetId) reportArgs.push('--dataset-id', job.datasetId);
        if (job.modelId) reportArgs.push('--model-id', job.modelId);

        await run('GOVERNANCE REPORT', 'python3', reportArgs, WORKSPACE_ROOT);
        const reportJson = path.join(reportOutputDir, 'assurance_report.json');
        if (!fs.existsSync(reportJson)) throw new Error('Governance command completed but assurance_report.json was not produced.');
        job.reportPath = reportJson;
        const report = JSON.parse(fs.readFileSync(reportJson, 'utf-8'));
        report.contributor = {
            id: job.contributorId || 'unassigned',
            name: job.contributorName || 'Unassigned'
        };
        if (!report.assets) report.assets = {};
        report.assets.contributor = {
            id: job.contributorId || 'unassigned',
            name: job.contributorName || 'Unassigned'
        };
        if (Array.isArray(report.findings)) {
            report.findings.forEach(f => {
                f.contributorId = job.contributorId || 'unassigned';
                f.contributorName = job.contributorName || 'Unassigned';
            });
        }
        fs.writeFileSync(reportJson, JSON.stringify(report, null, 2), 'utf-8');

        job.disposition = report.governance_disposition || job.disposition || 'REVIEW';
        job.trustStatus = job.disposition === 'ACCEPT' ? 'PASS' : job.disposition === 'REVIEW' ? 'WARNING' : 'FAIL';
        job.findingsCount = Array.isArray(report.findings) ? report.findings.length : job.findingsCount;
    }
}

function startJob({ testType = 'FULL_ASSURANCE', datasetId, modelId, configId, user, contributorId: explicitContribId, contributorName: explicitContribName, batchId }) {
    const runId = `test-${Date.now()}-${crypto.randomBytes(3).toString('hex')}`;
    const logPath = path.join(RUN_LOGS_DIR, `${runId}.log`);
    const logStream = fs.createWriteStream(logPath, { flags: 'a' });
    const normType = String(testType || 'FULL_ASSURANCE').toUpperCase();
    const dataset = resolveAsset(datasetId, 'dataset');
    const model = resolveAsset(modelId, 'model');

    const contributorId = explicitContribId || dataset?.contributorId || model?.contributorId || 'unassigned';
    let contributorName = explicitContribName || dataset?.contributorName || model?.contributorName;
    if (!contributorName || contributorName === 'Unassigned') {
        const contribList = loadContributors();
        const c = contribList.find(x => x.id === contributorId);
        contributorName = c ? c.name : (contributorId === 'unassigned' ? 'Unassigned' : contributorId);
    }

    const job = {
        run_id: runId,
        testId: runId,
        batchId: batchId || null,
        testType: normType,
        status: 'RUNNING',
        currentStep: 'Resolving selected assets',
        contributorId,
        contributorName,
        datasetId: datasetId || null,
        datasetName: dataset?.originalName || datasetId || null,
        modelId: modelId || null,
        modelName: model?.originalName || null,
        startTime: new Date().toISOString(),
        endTime: null,
        durationMs: null,
        gpuUsed: true,
        gpuDevice: process.env.SENTINELVISION_GPU || 'CUDA (detected by Python engines)',
        trustStatus: null,
        findingsCount: 0,
        severity: null,
        disposition: null,
        checks: {
            DATA_INTEGRITY: { status: 'QUEUED' },
            DATA_DRIFT: { status: 'QUEUED' },
            MODEL_INTEGRITY: { status: 'QUEUED' },
            INFERENCE_SEAL: { status: 'QUEUED' }
        },
        reportPath: null,
        logPath,
        error: null,
        initiatedBy: user ? user.email : 'operator'
    };

    jobs[runId] = job;
    saveState();
    recordAuditEvent('JOB_STARTED', { runId, testType: normType, datasetId, modelId, contributorId, contributorName, batchId: job.batchId }, user);

    (async () => {
        try {
            if (!dataset && ['DATA_INTEGRITY', 'DATA_DRIFT', 'DISTRIBUTION_SHIFT', 'FULL_ASSURANCE', 'TRUST_CHECK'].includes(normType)) {
                throw new Error(`Dataset '${datasetId || '(none)'}' was not found in the asset registry.`);
            }
            await executeJob(job, normType, dataset, model, configId, logStream);
            if (job.trustStatus == null) {
                job.trustStatus = 'PASS';
                job.disposition = 'ACCEPT';
            }
            job.status = 'COMPLETED';
            job.currentStep = 'Completed';
        } catch (err) {
            job.status = 'FAILED';
            job.trustStatus = 'FAIL';
            job.disposition = 'REVIEW';
            job.error = err.message;
            job.currentStep = 'Failed';
            logStream.write(`\n[ERROR] ${err.stack || err.message}\n`);
        } finally {
            const end = new Date();
            job.endTime = end.toISOString();
            job.durationMs = end.getTime() - new Date(job.startTime).getTime();
            saveState();
            logStream.write(`\n=== Job ${job.status} ===\n`);
            logStream.end();
            recordAuditEvent('JOB_COMPLETED', {
                runId,
                status: job.status,
                trustStatus: job.trustStatus,
                durationMs: job.durationMs,
                contributorId: job.contributorId,
                contributorName: job.contributorName,
                batchId: job.batchId,
                error: job.error || null
            }, user);
        }
    })();

    return job;
}

function getJob(runId) { return jobs[runId] || null; }
function listJobs() { return Object.values(jobs).sort((a, b) => new Date(b.startTime) - new Date(a.startTime)); }
function getAuditLogs() { return auditTrail.slice().reverse(); }

module.exports = { startJob, getJob, listJobs, getAuditLogs, recordAuditEvent };
