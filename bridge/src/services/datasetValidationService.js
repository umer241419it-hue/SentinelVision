'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const HISTORY_FILE = path.resolve(__dirname, '../../../data/dataset_validations.json');

const BLOCKED_EXTENSIONS = [
    '.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.mp4', '.avi', '.zip',
    '.rar', '.tar', '.py', '.pt', '.pth', '.onnx', '.h5', '.pkl', '.exe'
];

function detectBinaryMagic(buf) {
    if (!buf || buf.length < 8) return null;
    const eq = (...bytes) => bytes.every((b, i) => buf[i] === b);
    if (eq(0x50, 0x4b, 0x03, 0x04) || eq(0x50, 0x4b, 0x05, 0x06) || eq(0x50, 0x4b, 0x07, 0x08)) return 'zip';
    if (eq(0x7f, 0x45, 0x4c, 0x46)) return 'elf';
    if (eq(0x4d, 0x5a)) return 'pe';
    if (eq(0x80, 0x02)) return 'pickle';
    if (buf.slice(0, 8).toString('utf-8') === '\x89HDF\r\n\x1a\n') return 'hdf5';
    if (eq(0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c)) return '7z';
    if (eq(0x52, 0x61, 0x72, 0x21)) return 'rar';
    if (eq(0xff, 0xd8, 0xff)) return 'jpeg';
    if (eq(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a)) return 'png';
    return null;
}

function looksBinary(buf) {
    const n = Math.min(buf.length, 8192);
    if (n === 0) return false;
    let suspicious = 0;
    for (let i = 0; i < n; i++) {
        const c = buf[i];
        if (c === 0) return true;
        if (c < 9 || (c > 13 && c < 32)) suspicious += 1;
    }
    return suspicious / n > 0.05;
}

let validationHistory = [];

function loadHistory() {
    if (fs.existsSync(HISTORY_FILE)) {
        try {
            validationHistory = JSON.parse(fs.readFileSync(HISTORY_FILE, 'utf-8'));
        } catch {
            validationHistory = [];
        }
    }
}

function saveHistory() {
    try {
        fs.mkdirSync(path.dirname(HISTORY_FILE), { recursive: true });
        fs.writeFileSync(HISTORY_FILE, JSON.stringify(validationHistory, null, 2), 'utf-8');
    } catch (err) {
        console.error('Failed to save validation history:', err.message);
    }
}

loadHistory();

function validateDatasetFile(kind, fileBuffer, originalName, contributor = null) {
    const ext = path.extname(originalName).toLowerCase();
    const sha256 = crypto.createHash('sha256').update(fileBuffer).digest('hex');
    const sizeBytes = fileBuffer?.length || 0;
    const errors = [];
    const warnings = [];

    // 1. Extension checks
    if (BLOCKED_EXTENSIONS.includes(ext)) {
        return {
            status: 'rejected',
            filename: originalName,
            format: kind.toUpperCase(),
            errors: [`Blocked file extension '${ext}'`],
            warnings: [],
            sizeBytes,
            sha256,
            timestamp: new Date().toISOString(),
        };
    }

    // 2. Binary / Magic checks
    const magic = detectBinaryMagic(fileBuffer);
    if (magic) {
        return {
            status: 'rejected',
            filename: originalName,
            format: kind.toUpperCase(),
            errors: [`Content is binary (${magic}); renamed files cannot bypass validation`],
            warnings: [],
            timestamp: new Date().toISOString()
        };
    }

    if (looksBinary(fileBuffer)) {
        return {
            status: 'rejected',
            filename: originalName,
            format: kind.toUpperCase(),
            errors: ['Content is not decodable text; renamed files cannot bypass validation'],
            warnings: [],
            timestamp: new Date().toISOString()
        };
    }

    let stats = {
        imageCount: 0,
        annotationCount: 0,
        categoryCount: 0
    };

    const textContent = fileBuffer.toString('utf-8');

    if (kind === 'coco') {
        try {
            const data = JSON.parse(textContent);
            if (!data.images || !Array.isArray(data.images)) {
                errors.push("Missing required 'images' array in COCO JSON");
            } else {
                stats.imageCount = data.images.length;
            }

            if (!data.annotations || !Array.isArray(data.annotations)) {
                warnings.push("Missing or empty 'annotations' array in COCO JSON");
            } else {
                stats.annotationCount = data.annotations.length;
            }

            if (!data.categories || !Array.isArray(data.categories)) {
                warnings.push("Missing or empty 'categories' array in COCO JSON");
            } else {
                stats.categoryCount = data.categories.length;
            }

            if (data.images && data.images.length === 0) {
                warnings.push('Dataset contains 0 images');
            }
        } catch (err) {
            errors.push(`Invalid JSON syntax: ${err.message}`);
        }
    } else if (kind === 'yolo') {
        const lines = textContent.split(/\r?\n/).filter(l => l.trim().length > 0);
        stats.annotationCount = lines.length;
        let lineErrors = 0;

        lines.slice(0, 100).forEach((l, idx) => {
            const parts = l.trim().split(/\s+/);
            if (parts.length < 5) {
                if (lineErrors < 5) errors.push(`Line ${idx + 1}: expected at least 5 values (class x y w h), found ${parts.length}`);
                lineErrors++;
            }
        });
        stats.categoryCount = 1;
        stats.imageCount = 1;
    }

    const status = errors.length > 0 ? 'invalid' : warnings.length > 0 ? 'warning' : 'valid';

    const report = {
        validationId: `val-${crypto.randomBytes(4).toString('hex')}`,
        filename: originalName,
        format: kind.toUpperCase(),
        status,
        imageCount: stats.imageCount,
        annotationCount: stats.annotationCount,
        categoryCount: stats.categoryCount,
        errors,
        warnings,
        sizeBytes,
        sha256,
        timestamp: new Date().toISOString(),
        contributorId: contributor?.id || 'unassigned',
        contributorName: contributor?.name || 'Unassigned'
    };

    validationHistory.unshift(report);
    if (validationHistory.length > 100) validationHistory.pop();
    saveHistory();

    return report;
}

function listValidations() {
    return validationHistory;
}

module.exports = {
    validateDatasetFile,
    listValidations
};
