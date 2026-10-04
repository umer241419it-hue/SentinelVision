'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const WORKSPACE_ROOT = path.resolve(__dirname, '../../../');
const HISTORY_FILE = path.join(WORKSPACE_ROOT, 'data/model_validations.json');

const ALLOWED_EXTENSIONS = ['.pt', '.pth', '.onnx', '.bin', '.h5', '.keras', '.tflite', '.ckpt', '.tar', '.gz'];

let history = [];

function loadHistory() {
    try {
        if (fs.existsSync(HISTORY_FILE)) history = JSON.parse(fs.readFileSync(HISTORY_FILE, 'utf8'));
    } catch {
        history = [];
    }
}

function saveHistory() {
    fs.mkdirSync(path.dirname(HISTORY_FILE), { recursive: true });
    fs.writeFileSync(HISTORY_FILE, JSON.stringify(history, null, 2), 'utf8');
}

function sha256File(filePath) {
    const hash = crypto.createHash('sha256');
    const fd = fs.openSync(filePath, 'r');
    try {
        const buffer = Buffer.allocUnsafe(1024 * 1024);
        let bytes;
        do {
            bytes = fs.readSync(fd, buffer, 0, buffer.length, null);
            if (bytes) hash.update(buffer.subarray(0, bytes));
        } while (bytes > 0);
    } finally {
        fs.closeSync(fd);
    }
    return hash.digest('hex');
}

function findWeightsInDir(dirPath) {
    let found = null;
    function walk(p) {
        if (found) return;
        try {
            const entries = fs.readdirSync(p, { withFileTypes: true });
            for (const entry of entries) {
                const full = path.join(p, entry.name);
                if (entry.isDirectory()) {
                    walk(full);
                } else if (entry.isFile()) {
                    const ext = path.extname(entry.name).toLowerCase();
                    if (ALLOWED_EXTENSIONS.includes(ext) && !entry.name.includes('.tar.')) {
                        found = full;
                        return;
                    }
                }
            }
        } catch {}
    }
    walk(dirPath);
    return found;
}

function hashDirectory(dirPath) {
    const fileHashes = [];
    let totalSize = 0;
    function walk(p) {
        try {
            const entries = fs.readdirSync(p, { withFileTypes: true });
            for (const entry of entries) {
                const full = path.join(p, entry.name);
                if (entry.isDirectory()) {
                    walk(full);
                } else if (entry.isFile()) {
                    const rel = path.relative(dirPath, full).replace(/\\/g, '/');
                    const stat = fs.statSync(full);
                    totalSize += stat.size;
                    const h = sha256File(full);
                    fileHashes.push(`${rel}:${h}`);
                }
            }
        } catch {}
    }
    walk(dirPath);
    const agg = crypto.createHash('sha256').update(fileHashes.sort().join('|')).digest('hex');
    return { hash: agg, totalSize, fileCount: fileHashes.length };
}

function validateModelAsset(model, contributor) {
    const errors = [];
    const warnings = [];
    const rawModelPath = model?.storagePath || model?.filePath || model?.weightsPath;
    const modelPath = rawModelPath && (path.isAbsolute(rawModelPath) ? rawModelPath : path.resolve(WORKSPACE_ROOT, rawModelPath));
    const filename = model?.originalName || model?.name || path.basename(modelPath || '');
    let ext = path.extname(filename).toLowerCase();

    let computedHash = null;
    let sizeBytes = 0;

    if (!modelPath || !fs.existsSync(modelPath)) {
        warnings.push('Model asset is not present locally; the real Model Integrity engine cannot execute until the registered model bytes are available.');
    } else {
        const stat = fs.statSync(modelPath);
        if (stat.isDirectory()) {
            const dirResult = hashDirectory(modelPath);
            sizeBytes = dirResult.totalSize;
            computedHash = dirResult.hash;

            if (dirResult.fileCount === 0) {
                errors.push('Model folder is empty');
            }

            const primaryWeights = (model?.weightsPath && fs.existsSync(model.weightsPath) && !fs.statSync(model.weightsPath).isDirectory())
                ? model.weightsPath
                : findWeightsInDir(modelPath);

            if (!primaryWeights) {
                errors.push('No recognized model weight file (.pt, .pth, .onnx, .bin, .h5, etc.) found in model folder');
            } else {
                ext = path.extname(primaryWeights).toLowerCase();
            }

            if (model.sha256 && model.sha256 !== computedHash) {
                warnings.push('SHA-256 mismatch between registry metadata and the current model folder; re-register or refresh the asset hash.');
            }
        } else {
            sizeBytes = stat.size;
            if (stat.size === 0) errors.push('Model file is empty');
            if (ext && !ALLOWED_EXTENSIONS.includes(ext) && !filename.includes('.tar.')) {
                errors.push(`Unsupported model extension '${ext}'`);
            }
            computedHash = sha256File(modelPath);
            if (model.sha256 && model.sha256 !== computedHash) {
                warnings.push('SHA-256 mismatch between registry metadata and the current model file; re-register or refresh the asset hash before relying on the registry digest.');
            }
        }
    }

    if (!model?.contributorId || model.contributorId === 'unassigned') {
        errors.push('Model has no registered contributor');
    }
    if (contributor?.id && model?.contributorId && contributor.id !== model.contributorId) {
        errors.push('Selected contributor does not match the model registry attribution');
    }

    const status = errors.length ? 'INVALID' : warnings.length ? 'WARNING' : 'VALID';
    const report = {
        validationId: `mval-${crypto.randomBytes(4).toString('hex')}`,
        modelId: model?.id || model?.uploadId,
        modelName: filename,
        contributorId: model?.contributorId || contributor?.id || 'unassigned',
        contributorName: model?.contributorName || contributor?.name || 'Unassigned',
        status,
        framework: model?.framework || 'Unknown',
        extension: ext || 'Unknown',
        sizeBytes,
        registeredSha256: model?.sha256 || null,
        computedSha256: computedHash,
        errors,
        warnings,
        validatedAt: new Date().toISOString()
    };

    history.unshift(report);
    if (history.length > 100) history.pop();
    saveHistory();
    return report;
}

function updateValidation(validationId, patch) {
    const index = history.findIndex(v => v.validationId === validationId);
    if (index < 0) return null;
    history[index] = { ...history[index], ...patch };
    saveHistory();
    return history[index];
}

function listValidations() {
    return history;
}

loadHistory();

module.exports = { validateModelAsset, updateValidation, listValidations, ALLOWED_EXTENSIONS };
