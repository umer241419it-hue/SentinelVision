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
            sizeBytes,
            sha256,
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
            sizeBytes,
            sha256,
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


function normalizeRelativePath(value) {
    return String(value || '')
        .replace(/\\/g, '/')
        .replace(/^\/+/, '')
        .split('/')
        .filter(part => part && part !== '.' && part !== '..')
        .join('/');
}

function isImagePath(name) {
    return /\.(jpg|jpeg|png|webp|bmp)$/i.test(name);
}

function baseWithoutExt(name) {
    return name.replace(/\.[^.]+$/, '').toLowerCase();
}

function validateYoloBundle(files, errors, warnings) {
    const imageFiles = files.filter(f => isImagePath(f.filename));
    const labelFiles = files.filter(f => /\.txt$/i.test(f.filename) && !/classes?\.txt$/i.test(f.filename));
    const yamlFiles = files.filter(f => /\.(ya?ml)$/i.test(f.filename));
    const imageByBase = new Map(imageFiles.map(f => [baseWithoutExt(f.filename), f.filename]));
    const labelByBase = new Map(labelFiles.map(f => [baseWithoutExt(f.filename), f.filename]));

    if (!imageFiles.length) errors.push('No image files found in the uploaded dataset folder');
    if (!labelFiles.length) errors.push('No YOLO annotation .txt files found in the uploaded dataset folder');
    if (!yamlFiles.length) warnings.push('No .yaml/.yml dataset configuration was found; class names could not be verified from a dataset config');

    let annotations = 0;
    let malformed = 0;
    const referencedClassIds = new Set();

    for (const file of labelFiles) {
        const text = file.fileBuffer.toString('utf8');
        const lines = text.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
        for (let i = 0; i < lines.length; i++) {
            const parts = lines[i].split(/\s+/);
            if (parts.length < 5) {
                malformed++;
                if (malformed <= 10) errors.push(`${file.filename}: line ${i + 1} must contain class x y width height`);
                continue;
            }
            const classId = Number(parts[0]);
            const nums = parts.slice(1, 5).map(Number);
            if (!Number.isInteger(classId) || classId < 0 || nums.some(n => !Number.isFinite(n))) {
                malformed++;
                if (malformed <= 10) errors.push(`${file.filename}: line ${i + 1} contains non-numeric YOLO values`);
                continue;
            }
            if (nums.some(n => n < 0 || n > 1)) {
                malformed++;
                if (malformed <= 10) errors.push(`${file.filename}: line ${i + 1} has bounding-box values outside [0,1]`);
                continue;
            }
            referencedClassIds.add(classId);
            annotations++;
        }
    }

    let missingLabels = 0;
    for (const image of imageFiles) {
        if (!labelByBase.has(baseWithoutExt(image.filename))) missingLabels++;
    }
    let labelsWithoutImages = 0;
    for (const label of labelFiles) {
        if (!imageByBase.has(baseWithoutExt(label.filename))) labelsWithoutImages++;
    }
    if (missingLabels) warnings.push(`${missingLabels} image(s) have no matching YOLO label file`);
    if (labelsWithoutImages) errors.push(`${labelsWithoutImages} label file(s) have no matching image`);

    let classNames = [];
    const yaml = yamlFiles[0];
    if (yaml) {
        const yamlText = yaml.fileBuffer.toString('utf8');
        const namesMatch = yamlText.match(/(?:^|\n)\s*names\s*:\s*(?:\[(.*?)\]|\n((?:\s+-\s+.*\n?)+))/is);
        if (namesMatch) {
            const inline = namesMatch[1];
            if (inline) classNames = inline.split(',').map(x => x.trim().replace(/^['"]|['"]$/g, '')).filter(Boolean);
            else classNames = (namesMatch[2] || '').split(/\r?\n/).map(x => x.replace(/^\s*-\s*/, '').trim()).filter(Boolean);
        }
    }
    if (classNames.length) {
        const unknown = [...referencedClassIds].filter(id => id >= classNames.length);
        if (unknown.length) errors.push(`Unknown YOLO class id(s): ${unknown.slice(0, 20).join(', ')}`);
    } else if (referencedClassIds.size) {
        warnings.push('Class IDs were syntactically validated, but no class-name list was available for semantic class-range validation');
    }

    return {
        images: imageFiles.length,
        annotation_files: labelFiles.length,
        annotations,
        classes: classNames.length || referencedClassIds.size,
        images_without_annotations: missingLabels,
        annotations_without_images: labelsWithoutImages,
        malformed_annotations: malformed
    };
}

function validateCocoBundle(files, errors, warnings) {
    const imageFiles = files.filter(f => isImagePath(f.filename));
    const jsonFiles = files.filter(f => /\.json$/i.test(f.filename));
    if (!jsonFiles.length) {
        errors.push('No COCO JSON annotation file was found in the uploaded dataset folder');
        return { images: imageFiles.length, annotation_files: 0, annotations: 0, classes: 0, images_without_annotations: 0, annotations_without_images: 0 };
    }

    const annotationFile = jsonFiles.find(f => {
        try {
            const d = JSON.parse(f.fileBuffer.toString('utf8'));
            return Array.isArray(d.images) || Array.isArray(d.annotations) || Array.isArray(d.categories);
        } catch { return false; }
    }) || jsonFiles[0];

    let data;
    try {
        data = JSON.parse(annotationFile.fileBuffer.toString('utf8'));
    } catch (err) {
        errors.push(`${annotationFile.filename}: invalid JSON syntax: ${err.message}`);
        return { images: imageFiles.length, annotation_files: jsonFiles.length, annotations: 0, classes: 0, images_without_annotations: 0, annotations_without_images: 0 };
    }

    if (!Array.isArray(data.images)) errors.push("COCO JSON is missing required 'images' array");
    if (!Array.isArray(data.annotations)) warnings.push("COCO JSON is missing or has no 'annotations' array");
    if (!Array.isArray(data.categories)) warnings.push("COCO JSON is missing or has no 'categories' array");

    const images = Array.isArray(data.images) ? data.images : [];
    const annotations = Array.isArray(data.annotations) ? data.annotations : [];
    const categories = Array.isArray(data.categories) ? data.categories : [];
    const ids = new Set(images.map(x => x.id));
    const categoryIds = new Set(categories.map(x => x.id));
    const uploadedBasenames = new Set(imageFiles.map(x => path.basename(x.filename).toLowerCase()));

    let missingImageFiles = 0;
    for (const image of images) {
        const name = String(image.file_name || '').replace(/\\/g, '/');
        if (!name || !uploadedBasenames.has(path.basename(name).toLowerCase())) missingImageFiles++;
    }
    let orphanAnnotations = 0;
    let unknownCategories = 0;
    for (const ann of annotations) {
        if (!ids.has(ann.image_id)) orphanAnnotations++;
        if (categoryIds.size && !categoryIds.has(ann.category_id)) unknownCategories++;
        if (!Array.isArray(ann.bbox) || ann.bbox.length !== 4 || ann.bbox.some(n => !Number.isFinite(Number(n)))) {
            errors.push(`COCO annotation ${ann.id ?? 'unknown'} has an invalid bbox`);
            break;
        }
        const [x, y, w, h] = ann.bbox.map(Number);
        if (w < 0 || h < 0) errors.push(`COCO annotation ${ann.id ?? 'unknown'} has a negative bbox size`);
        if (x + w < 0 || y + h < 0) errors.push(`COCO annotation ${ann.id ?? 'unknown'} has an invalid bbox origin`);
    }
    if (missingImageFiles) warnings.push(`${missingImageFiles} COCO image record(s) do not match an uploaded image file`);
    if (orphanAnnotations) errors.push(`${orphanAnnotations} annotation(s) reference an image_id not present in the COCO images array`);
    if (unknownCategories) errors.push(`${unknownCategories} annotation(s) reference an unknown category_id`);

    return {
        images: images.length || imageFiles.length,
        annotation_files: jsonFiles.length,
        annotations: annotations.length,
        classes: categories.length,
        images_without_annotations: Math.max(0, images.length - new Set(annotations.map(a => a.image_id)).size),
        annotations_without_images: orphanAnnotations
    };
}

function validateDatasetBundle(kind, files, contributor = null) {
    const startedAt = new Date().toISOString();
    const normalized = (files || []).map(f => ({
        filename: normalizeRelativePath(f.filename || 'unnamed'),
        fileBuffer: f.fileBuffer || Buffer.alloc(0)
    })).filter(f => f.filename);

    const errors = [];
    const warnings = [];
    const hashes = [];
    const seenPaths = new Set();

    for (const file of normalized) {
        if (seenPaths.has(file.filename)) errors.push(`Duplicate path in upload: ${file.filename}`);
        seenPaths.add(file.filename);
        hashes.push(`${file.filename}:${crypto.createHash('sha256').update(file.fileBuffer).digest('hex')}`);
        if (file.fileBuffer.length === 0) errors.push(`Empty file: ${file.filename}`);
    }

    const stats = kind === 'coco'
        ? validateCocoBundle(normalized, errors, warnings)
        : validateYoloBundle(normalized, errors, warnings);

    if (normalized.length > 1 && !normalized.some(f => isImagePath(f.filename))) {
        errors.push('Dataset upload contains multiple files but no supported image files');
    }
    if (!normalized.length) errors.push('No dataset files were uploaded');

    const status = errors.length ? 'invalid' : warnings.length ? 'warning' : 'valid';
    const aggregateHash = crypto.createHash('sha256')
        .update(hashes.sort().join('|'))
        .digest('hex');

    const report = {
        validationId: `val-${crypto.randomBytes(4).toString('hex')}`,
        filename: `${normalized.length} uploaded dataset file(s)`,
        contributorId: contributor?.id || 'unassigned',
        contributorName: contributor?.name || 'Unassigned',
        status,
        format: String(kind || '').toUpperCase(),
        sizeBytes: normalized.reduce((sum, f) => sum + f.fileBuffer.length, 0),
        sha256: aggregateHash,
        timestamp: new Date().toISOString(),
        files_processed: normalized.length,
        errors: errors.length,
        warnings: warnings.length,
        error_details: errors.map(message => ({ type: 'VALIDATION_ERROR', message })),
        warning_details: warnings.map(message => ({ type: 'VALIDATION_WARNING', message })),
        stats: {
            images: stats.images || 0,
            annotation_files: stats.annotation_files || 0,
            annotations: stats.annotations || 0,
            classes: stats.classes || 0,
            images_without_annotations: stats.images_without_annotations || 0,
            annotations_without_images: stats.annotations_without_images || 0,
            empty_annotation_files: normalized.filter(f => f.fileBuffer.length === 0).length,
            invalid_files: errors.length,
            duplicate_files: Math.max(0, normalized.length - seenPaths.size),
            unknown_class_ids: 0,
            out_of_bounds_boxes: stats.malformed_annotations || 0
        },
        files: normalized.map(f => ({
            path: f.filename,
            sizeBytes: f.fileBuffer.length,
            sha256: crypto.createHash('sha256').update(f.fileBuffer).digest('hex')
        })),
        datasetHash: aggregateHash,
        startedAt,
        completedAt: new Date().toISOString()
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
    validateDatasetBundle,
    listValidations
};
