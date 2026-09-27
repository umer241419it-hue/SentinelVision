'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const WORKSPACE_ROOT = path.resolve(__dirname, '../../../');
const DATA_INTEGRITY_ROOT = path.join(WORKSPACE_ROOT, 'data-integrity');
const MODEL_INTEGRITY_ROOT = path.join(WORKSPACE_ROOT, 'model-integrity');

function mkdirp(p) { fs.mkdirSync(p, { recursive: true }); }
function writeJson(p, value) { mkdirp(path.dirname(p)); fs.writeFileSync(p, JSON.stringify(value, null, 2), 'utf8'); }

function runProcess(command, args, cwd, env) {
    return new Promise((resolve) => {
        const child = spawn(command, args, { cwd, env: env || process.env, stdio: ['ignore', 'pipe', 'pipe'] });
        let stdout = ''; let stderr = '';
        child.stdout.on('data', c => { stdout += c.toString(); });
        child.stderr.on('data', c => { stderr += c.toString(); });
        child.on('error', err => resolve({ code: -1, stdout, stderr, error: err.message }));
        child.on('close', code => resolve({ code: code == null ? -1 : code, stdout, stderr }));
    });
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

async function runDatasetIntegrityEngine({ validationId, kind, files, workspaceDir }) {
    const engineRoot = path.join(workspaceDir, 'data-engine');
    const inputDir = path.join(engineRoot, 'images');
    mkdirp(inputDir);
    const labels = kind === 'coco' ? parseCocoLabels(files) : parseYoloLabels(files);
    const imageFiles = files.filter(f => imageName(f.filename));
    const copied = [];
    for (const file of imageFiles) {
        const ext = path.extname(file.filename).toLowerCase();
        const stem = baseName(file.filename);
        if (!labels.has(stem)) continue;
        const targetName = stem + ext;
        fs.writeFileSync(path.join(inputDir, targetName), file.fileBuffer);
        copied.push(targetName);
    }
    if (!copied.length) return { status: 'NOT_RUN', reason: 'No image files with usable annotations were available to the Data Integrity engine.' };
    const labelKey = {};
    for (const name of copied) labelKey[name] = labels.get(baseName(name));
    const labelsPath = path.join(engineRoot, 'label_key.json');
    writeJson(labelsPath, labelKey);
    const baseConfigPath = path.join(DATA_INTEGRITY_ROOT, 'config.json');
    const baseConfig = JSON.parse(fs.readFileSync(baseConfigPath, 'utf8'));
    baseConfig.output = { ...(baseConfig.output || {}), embedding_cache: 'cache/embeddings.npz', evidence_store: 'evidence_store', results: 'results/integrity_results.json' };
    const configPath = path.join(engineRoot, 'config.json');
    writeJson(configPath, baseConfig);
    const result = await runProcess('python3', ['-m', 'src.run_data_integrity', '--config', configPath, '--input', inputDir, '--labels', labelsPath, '--checks', 'duplicate,ood,label_flip', '--run-id', validationId], DATA_INTEGRITY_ROOT, pythonEnv());
    const outputPath = path.join(engineRoot, 'results', 'integrity_results.json');
    let engineOutput = null;
    if (fs.existsSync(outputPath)) { try { engineOutput = JSON.parse(fs.readFileSync(outputPath, 'utf8')); } catch {} }
    return { status: result.code === 0 ? 'COMPLETED' : 'FAILED', exitCode: result.code, imagesPresentedToEngine: copied.length, output: engineOutput ? engineOutput.summary : null, resultsPath: outputPath, stdout: result.stdout.slice(-12000), stderr: result.stderr.slice(-12000), error: result.error || null };
}

async function runModelIntegrityEngine({ modelId, modelPath, outputDir }) {
    mkdirp(outputDir);
    const outputPath = path.join(outputDir, 'strip_results.json');
    const args = ['src/strip_detector.py', '--model-path', modelPath, '--model-id', modelId, '--output', outputPath, '--hashes-output', path.join(outputDir, 'strip_hashes.json')];
    const result = await runProcess('python3', args, MODEL_INTEGRITY_ROOT, pythonEnv());
    let output = null;
    if (fs.existsSync(outputPath)) { try { output = JSON.parse(fs.readFileSync(outputPath, 'utf8')); } catch {} }
    return { engine: 'model-integrity/src/strip_detector.py', status: result.code === 0 ? 'COMPLETED' : 'FAILED', exitCode: result.code, modelId, output, resultsPath: outputPath, stdout: result.stdout.slice(-12000), stderr: result.stderr.slice(-12000), error: result.error || null };
}

module.exports = { runDatasetIntegrityEngine, runModelIntegrityEngine };