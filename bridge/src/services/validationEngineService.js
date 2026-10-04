'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const WORKSPACE_ROOT = path.resolve(__dirname, '../../../');
const DATA_INTEGRITY_ROOT = path.join(WORKSPACE_ROOT, 'data-integrity');
const MODEL_INTEGRITY_ROOT = path.join(WORKSPACE_ROOT, 'model-integrity');

function mkdirp(p) { fs.mkdirSync(p, { recursive: true }); }
function writeJson(p, value) { mkdirp(path.dirname(p)); fs.writeFileSync(p, JSON.stringify(value, null, 2), 'utf8'); }

const activeSubprocesses = new Set();

function runProcess(command, args, cwd, env) {
    return new Promise((resolve) => {
        const child = spawn(command, args, { cwd, env: env || process.env, stdio: ['ignore', 'pipe', 'pipe'] });
        activeSubprocesses.add(child);
        let stdout = ''; let stderr = '';
        child.stdout.on('data', c => { stdout += c.toString(); });
        child.stderr.on('data', c => { stderr += c.toString(); });
        const clean = () => activeSubprocesses.delete(child);
        child.on('error', err => { clean(); resolve({ code: -1, stdout, stderr, error: err.message }); });
        child.on('close', code => { clean(); resolve({ code: code == null ? -1 : code, stdout, stderr }); });
    });
}

function terminateSubprocesses() {
    for (const child of activeSubprocesses) {
        try { child.kill('SIGTERM'); } catch {}
    }
    activeSubprocesses.clear();
}

function pythonEnv() {
    return { ...process.env, PYTHONPATH: [WORKSPACE_ROOT, path.join(WORKSPACE_ROOT, 'crypto-utils'), DATA_INTEGRITY_ROOT, MODEL_INTEGRITY_ROOT, path.join(WORKSPACE_ROOT, 'shared'), path.join(WORKSPACE_ROOT, 'inference-provenance/src'), path.join(WORKSPACE_ROOT, 'drift-monitor')].join(':') };
}

function imageName(name) { return /\.(jpg|jpeg|png|bmp|tif|tiff|webp)$/i.test(name || ''); }
function baseName(name) { return path.basename(name || '').replace(/\.[^.]+$/, '').toLowerCase(); }

function parseYoloLabels(files) {
    const yaml = files.find(f => /\.ya?ml$/i.test(f.filename));
    const classNames = [];
    if (yaml) {
        const text = yaml.fileBuffer.toString('utf8');
        const m = text.match(/(?:^|\n)\s*names\s*:\s*(?:\[(.*?)\]|\n((?:\s+-\s+.*\n?)+))/is);
        if (m && m[1]) classNames.push(...m[1].split(',').map(x => x.trim().replace(/^['\"]|['\"]$/g, '')).filter(Boolean));
        else if (m && m[2]) classNames.push(...m[2].split(/\r?\n/).map(x => x.replace(/^\s*-\s*/, '').trim()).filter(Boolean));
    }
    const labels = new Map();
    for (const f of files.filter(x => /\.txt$/i.test(x.filename) && !/classes?\.txt$/i.test(x.filename))) {
        const line = f.fileBuffer.toString('utf8').split(/\r?\n/).map(x => x.trim()).find(Boolean);
        if (!line) continue;
        const id = Number(line.split(/\s+/)[0]);
        if (!Number.isInteger(id) || id < 0) continue;
        labels.set(baseName(f.filename), classNames[id] || String(id));
    }
    return labels;
}

function parseCocoLabels(files) {
    const json = files.find(f => {
        if (!/\.json$/i.test(f.filename)) return false;
        try { const d = JSON.parse(f.fileBuffer.toString('utf8')); return Array.isArray(d.images) || Array.isArray(d.annotations); } catch { return false; }
    });
    const labels = new Map();
    if (!json) return labels;
    const d = JSON.parse(json.fileBuffer.toString('utf8'));
    const categories = new Map((d.categories || []).map(c => [c.id, c.name || String(c.id)]));
    const imageById = new Map((d.images || []).map(i => [i.id, path.basename(i.file_name || '')]));
    for (const ann of d.annotations || []) {
        const name = imageById.get(ann.image_id);
        if (!name || labels.has(baseName(name))) continue;
        labels.set(baseName(name), categories.get(ann.category_id) || String(ann.category_id));
    }
    return labels;
}

function safeName(name) {
    return path.basename(String(name || 'file')).replace(/[^a-zA-Z0-9._-]/g, '_');
}

function writeLabel(labelMapPath, labels) { writeJson(labelMapPath, labels); }

function parseYoloLabelsForEngine(files) {
    const yaml = files.find(f => /\.(ya?ml)$/i.test(f.filename));
    let classNames = [];
    if (yaml) {
        const text = yaml.fileBuffer.toString('utf8');
        const m = text.match(/(?:^|\n)\s*names\s*:\s*(?:\[(.*?)\]|\n((?:\s+-\s+.*\n?)+))/is);
        if (m && m[1]) classNames = m[1].split(',').map(x => x.trim().replace(/^['\"]|['\"]$/g, '')).filter(Boolean);
        else if (m && m[2]) classNames = m[2].split(/\r?\n/).map(x => x.replace(/^\s*-\s*/, '').trim()).filter(Boolean);
    }
    const labels = {};
    for (const f of files.filter(x => /\.txt$/i.test(x.filename) && !/classes?\.txt$/i.test(x.filename))) {
        const line = f.fileBuffer.toString('utf8').split(/\r?\n/).map(x => x.trim()).find(Boolean);
        if (!line) continue;
        const id = Number(line.split(/\s+/)[0]);
        if (!Number.isInteger(id) || id < 0) continue;
        labels[baseName(f.filename)] = classNames[id] || String(id);
    }
    return { labels, classNames };
}

function prepareEngineDataset(files, kind, workspaceDir) {
    const inputDir = path.join(workspaceDir, 'engine-input');
    mkdirp(inputDir);
    const normalized = (files || []).map(f => ({ filename: String(f.filename || ''), fileBuffer: f.fileBuffer || Buffer.alloc(0) }));
    const imageFiles = normalized.filter(f => imageName(f.filename));
    if (!imageFiles.length) throw new Error('The real Data Integrity engine requires image files. Include images with annotations.');
    const labels = {};
    const usedNames = new Set();
    const originalToFlat = new Map();
    const uniqueImageName = filename => {
        const base = safeName(filename);
        if (!usedNames.has(base)) { usedNames.add(base); return base; }
        const stem = path.parse(base).name, ext = path.extname(base);
        let i = 2, next = stem + '_' + i + ext;
        while (usedNames.has(next)) { i++; next = stem + '_' + i + ext; }
        usedNames.add(next); return next;
    };
    for (const file of imageFiles) {
        const flat = uniqueImageName(file.filename);
        fs.writeFileSync(path.join(inputDir, flat), file.fileBuffer);
        originalToFlat.set(baseName(file.filename), flat);
    }
    if (kind === 'yolo') {
        const parsed = parseYoloLabelsForEngine(normalized);
        for (const [base, label] of Object.entries(parsed.labels)) {
            const flat = originalToFlat.get(base);
            if (flat) labels[flat] = label;
        }
    }
    // If not all labels resolved, check JSON label files (COCO or key-value label dictionaries)
    if (Object.keys(labels).length < imageFiles.length) {
        for (const f of normalized.filter(x => /\.json$/i.test(x.filename))) {
            try {
                const d = JSON.parse(f.fileBuffer.toString('utf8'));
                if (Array.isArray(d.images) || Array.isArray(d.annotations)) {
                    const categories = new Map((d.categories || []).map(c => [c.id, c.name || String(c.id)]));
                    const imageById = new Map((d.images || []).map(i => [i.id, path.basename(i.file_name || '')]));
                    const firstLabel = new Map();
                    for (const ann of d.annotations || []) if (!firstLabel.has(ann.image_id)) firstLabel.set(ann.image_id, categories.get(ann.category_id) || String(ann.category_id));
                    for (const [imageId, originalName] of imageById.entries()) {
                        const flat = originalToFlat.get(baseName(originalName));
                        if (flat && !labels[flat]) labels[flat] = firstLabel.get(imageId) || 'background';
                    }
                } else if (typeof d === 'object' && d !== null) {
                    const rawLabels = d.labels && typeof d.labels === 'object' && !Array.isArray(d.labels) ? d.labels : d;
                    for (const [key, val] of Object.entries(rawLabels)) {
                        const flat = originalToFlat.get(baseName(key));
                        if (flat && !labels[flat]) {
                            const lbl = (typeof val === 'object' && val !== null) ? (val.given_label || val.label) : val;
                            if (lbl) labels[flat] = String(lbl);
                        }
                    }
                }
            } catch {}
        }
    }
    const missing = [...originalToFlat.values()].filter(name => !labels[name]);
    if (missing.length) throw new Error('The real Data Integrity engine requires exactly one label per image. Missing labels for ' + missing.length + ' image(s), e.g. ' + missing.slice(0, 3).join(', '));
    const labelPath = path.join(inputDir, 'label_key.json');
    writeLabel(labelPath, labels);
    return { inputDir, labelPath, imageCount: imageFiles.length };
}

async function runDatasetIntegrityEngine({ validationId, kind, files, workspaceDir, datasetId = null, datasetName = null }) {
    const engineRoot = path.join(workspaceDir, 'data-engine'); mkdirp(engineRoot);
    let prepared;
    try { prepared = prepareEngineDataset(files, kind, engineRoot); } catch (err) {
        return { engine: 'SentinelVision Data Integrity Assurance (Python)', status: 'FAILED', simulated: false, exitCode: -1, datasetId, datasetName, resultsPath: null, stdout: '', stderr: err.message, error: err.message, findings: [] };
    }
    const configPath = path.join(DATA_INTEGRITY_ROOT, 'config.json');
    const result = await runProcess(process.env.PYTHON || 'python3', ['-m', 'src.run_data_integrity', '--config', configPath, '--input', prepared.inputDir, '--labels', prepared.labelPath, '--checks', 'duplicate,ood,label_flip', '--run-id', validationId], DATA_INTEGRITY_ROOT, pythonEnv());
    const resultsPath = path.join(DATA_INTEGRITY_ROOT, 'results', 'integrity_results.json');
    let parsed = null;
    try { if (fs.existsSync(resultsPath)) parsed = JSON.parse(fs.readFileSync(resultsPath, 'utf8')); } catch (err) { parsed = null; }
    if (result.code !== 0 || !parsed) return { engine: 'SentinelVision Data Integrity Assurance (Python)', status: 'FAILED', simulated: false, exitCode: result.code, datasetId, datasetName, resultsPath, stdout: result.stdout, stderr: result.stderr, error: result.error || 'Data Integrity engine exited with code ' + result.code, findings: [] };
    const findings = Array.isArray(parsed.results) ? parsed.results.map(entry => ({ type: 'DATA_INTEGRITY_FINDING', file: entry.image_id, severity: entry.severity, confidence: entry.confidence, message: entry.reason, evidenceHash: entry.evidence_hash, disposition: entry.disposition })) : [];
    return { engine: 'SentinelVision Data Integrity Assurance (Python)', status: 'COMPLETED', simulated: false, exitCode: result.code, datasetId, datasetName, imagesPresentedToEngine: prepared.imageCount, output: parsed.summary || {}, findings, resultsPath, stdout: result.stdout, stderr: result.stderr, error: null };
}

async function runModelIntegrityEngine({ modelId, modelPath, outputDir }) {
    mkdirp(outputDir); const resolvedModel = path.resolve(modelPath);
    if (!fs.existsSync(resolvedModel)) return { engine: 'SentinelVision Model Integrity Assurance (Python STRIP)', status: 'FAILED', simulated: false, exitCode: -1, modelId, output: null, resultsPath: null, stdout: '', stderr: 'Model file not found: ' + resolvedModel, error: 'Model file not found: ' + resolvedModel };
    const modelRoot = MODEL_INTEGRITY_ROOT;
    const manifestPath = path.join(modelRoot, 'calibration_manifest.json');
    const dataDir = path.join(modelRoot, 'data', 'trojai_sample');
    const triggersDir = path.join(modelRoot, 'triggers');
    const outputPath = path.join(outputDir, 'strip_results.json');
    const hashesPath = path.join(outputDir, 'strip_hashes.json');
    if (!fs.existsSync(manifestPath)) return { engine: 'SentinelVision Model Integrity Assurance (Python STRIP)', status: 'FAILED', simulated: false, exitCode: -1, modelId, output: null, resultsPath: outputPath, stdout: '', stderr: 'Model Integrity calibration_manifest.json is missing.', error: 'Model Integrity calibration_manifest.json is missing.' };
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    const manifestEntry = manifest.find(item => String(item.model_id) === String(modelId));
    if (!manifestEntry) return { engine: 'SentinelVision Model Integrity Assurance (Python STRIP)', status: 'UNSUPPORTED', simulated: false, exitCode: 2, modelId, output: null, resultsPath: outputPath, stdout: '', stderr: 'No calibration manifest entry exists for model ' + modelId + '. The real STRIP engine is calibrated only for registered model IDs.', error: 'Model is not calibrated for the real STRIP engine.' };
    if (!fs.existsSync(path.join(dataDir, modelId, 'example_data'))) return { engine: 'SentinelVision Model Integrity Assurance (Python STRIP)', status: 'UNSUPPORTED', simulated: false, exitCode: 2, modelId, output: null, resultsPath: outputPath, stdout: '', stderr: 'Registered STRIP example_data is missing for model ' + modelId + '.', error: 'Registered STRIP example_data is missing.' };
    const result = await runProcess(process.env.PYTHON || 'python3', ['src/strip_detector.py', '--model-path', resolvedModel, '--model-id', String(modelId), '--data-dir', dataDir, '--triggers-dir', triggersDir, '--manifest', manifestPath, '--output', outputPath, '--hashes-output', hashesPath], modelRoot, pythonEnv());
    let rows = null; try { if (fs.existsSync(outputPath)) rows = JSON.parse(fs.readFileSync(outputPath, 'utf8')); } catch {}
    if (result.code !== 0 || !Array.isArray(rows)) return { engine: 'SentinelVision Model Integrity Assurance (Python STRIP)', status: 'FAILED', simulated: false, exitCode: result.code, modelId, output: null, resultsPath: outputPath, stdout: result.stdout, stderr: result.stderr, error: result.error || 'STRIP engine exited with code ' + result.code, findings: [] };
    const top = rows.length ? rows.reduce((a, b) => Number(b.entropy_deficit || 0) > Number(a.entropy_deficit || 0) ? b : a) : null;

    // The real project verdict is produced by scoring.py, which combines the
    // live STRIP result with the calibrated Neural Cleanse/MAD result.
    const madPath = path.join(modelRoot, 'mad_results.json');
    let score = null;
    if (fs.existsSync(madPath)) {
        const madAll = JSON.parse(fs.readFileSync(madPath, 'utf8'));
        const madEntry = madAll.find(item => String(item.model_id) === String(modelId));
        if (madEntry) {
            const scoreDir = path.join(outputDir, 'scoring');
            mkdirp(scoreDir);
            const scoreManifest = path.join(scoreDir, 'calibration_manifest.json');
            const scoreMad = path.join(scoreDir, 'mad_results.json');
            const scoreStrip = path.join(scoreDir, 'strip_results.json');
            const scoreOutput = path.join(scoreDir, 'scoring_results.json');
            writeJson(scoreManifest, [manifestEntry]);
            writeJson(scoreMad, [madEntry]);
            writeJson(scoreStrip, rows);
            const scoreRun = await runProcess(
                process.env.PYTHON || 'python3',
                ['src/scoring.py', '--manifest', scoreManifest, '--mad', scoreMad, '--strip', scoreStrip, '--output', scoreOutput, '--model-id', String(modelId)],
                modelRoot,
                pythonEnv()
            );
            if (scoreRun.code === 0 && fs.existsSync(scoreOutput)) {
                const scored = JSON.parse(fs.readFileSync(scoreOutput, 'utf8'));
                score = Array.isArray(scored) ? scored[0] : null;
            }
        }
    }

    const output = {
        verdict: score?.disposition || 'REVIEW',
        model_id: modelId,
        classes_evaluated: rows.length,
        top_class: top ? top.class : null,
        max_entropy_deficit: top ? top.entropy_deficit : null,
        strip_results: rows,
        scoring: score,
        verdict_source: score ? 'Neural Cleanse/MAD + live STRIP scoring.py' : 'live STRIP only; calibrated MAD result unavailable'
    };
    return { engine: 'SentinelVision Model Integrity Assurance (Python STRIP)', status: 'COMPLETED', simulated: false, exitCode: result.code, modelId, output, resultsPath: outputPath, stdout: result.stdout, stderr: result.stderr, error: null };
}

module.exports = { runDatasetIntegrityEngine, runModelIntegrityEngine, terminateSubprocesses };