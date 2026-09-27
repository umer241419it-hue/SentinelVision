'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const WORKSPACE_ROOT = path.resolve(__dirname, '..');
const DATA_DIR = path.join(WORKSPACE_ROOT, 'data');
const CONTRIBUTORS_FILE = path.join(DATA_DIR, 'contributors.json');
const UPLOADS_META_FILE = path.join(DATA_DIR, 'uploads_meta.json');
const DEMO_DIR = path.join(WORKSPACE_ROOT, 'demo/contributors');

function sha256FileSafe(filePath) {
    if (!fs.existsSync(filePath)) return null;
    try {
        const buf = fs.readFileSync(filePath);
        return crypto.createHash('sha256').update(buf).digest('hex');
    } catch {
        return null;
    }
}

function ensureDir(dir) {
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
}

function ensureSymlink(target, linkPath) {
    try {
        if (fs.existsSync(linkPath)) {
            const stat = fs.lstatSync(linkPath);
            if (stat.isSymbolicLink()) return; // Already exists
            fs.unlinkSync(linkPath);
        }
        const relTarget = path.relative(path.dirname(linkPath), target);
        fs.symlinkSync(relTarget, linkPath);
    } catch (err) {
        console.warn(`Could not create symlink ${linkPath} -> ${target}: ${err.message}`);
    }
}

const DEMO_VENDORS = [
    {
        id: 'vendor-alpha',
        name: 'Vendor Alpha',
        type: 'DEMO_VENDOR',
        folder: 'vendor_alpha',
        description: 'Certified baseline provider — clean reference dataset & baseline neural weights',
        status: 'ACTIVE',
        createdAt: '2026-09-20T08:00:00Z',
        updatedAt: '2026-09-20T08:00:00Z'
    },
    {
        id: 'vendor-beta',
        name: 'Vendor Beta',
        type: 'DEMO_VENDOR',
        folder: 'vendor_beta',
        description: 'External evaluation partner — controlled integrity test suite & anomaly assessment models',
        status: 'ACTIVE',
        createdAt: '2026-09-21T09:30:00Z',
        updatedAt: '2026-09-21T09:30:00Z'
    },
    {
        id: 'vendor-gamma',
        name: 'Vendor Gamma',
        type: 'DEMO_VENDOR',
        folder: 'vendor_gamma',
        description: 'Third-party research vendor — comprehensive multi-attack benchmark & adversarial assessment models',
        status: 'ACTIVE',
        createdAt: '2026-09-22T11:15:00Z',
        updatedAt: '2026-09-22T11:15:00Z'
    }
];

function setup() {
    console.log('[*] Setting up SentinelVision Contributor/Vendor Demo Assets...');
    ensureDir(DATA_DIR);
    ensureDir(DEMO_DIR);

    // 1. Maintain or initialize contributors.json
    let existingContributors = [];
    if (fs.existsSync(CONTRIBUTORS_FILE)) {
        try {
            existingContributors = JSON.parse(fs.readFileSync(CONTRIBUTORS_FILE, 'utf-8'));
        } catch {
            existingContributors = [];
        }
    }

    const contributorMap = new Map();
    for (const c of existingContributors) {
        contributorMap.set(c.id, c);
    }
    for (const v of DEMO_VENDORS) {
        const { folder, ...meta } = v;
        if (!contributorMap.has(v.id)) {
            contributorMap.set(v.id, meta);
        } else {
            // merge description/status without overwriting user changes
            const existing = contributorMap.get(v.id);
            contributorMap.set(v.id, { ...meta, ...existing });
        }
    }
    const finalContributors = Array.from(contributorMap.values());
    fs.writeFileSync(CONTRIBUTORS_FILE, JSON.stringify(finalContributors, null, 2), 'utf-8');
    console.log(`[OK] Registered ${finalContributors.length} contributors in data/contributors.json`);

    // 2. Load existing uploads_meta.json
    let uploads = [];
    if (fs.existsSync(UPLOADS_META_FILE)) {
        try {
            uploads = JSON.parse(fs.readFileSync(UPLOADS_META_FILE, 'utf-8'));
        } catch {
            uploads = [];
        }
    }

    // Default assets map
    const assetAssignments = {
        'dataset-voc2012-clean': {
            contributorId: 'vendor-alpha',
            contributorName: 'Vendor Alpha',
            format: 'VOC2012'
        },
        'model-clean-res50-0028': {
            contributorId: 'vendor-alpha',
            contributorName: 'Vendor Alpha',
            framework: 'PyTorch'
        },
        'dataset-integrity-test': {
            contributorId: 'vendor-beta',
            contributorName: 'Vendor Beta',
            format: 'ImageFolder/JSON'
        },
        'model-trojai-res50-0112': {
            contributorId: 'vendor-beta',
            contributorName: 'Vendor Beta',
            framework: 'PyTorch'
        },
        'dataset-voc2012-benchmark': {
            contributorId: 'vendor-gamma',
            contributorName: 'Vendor Gamma',
            format: 'VOC2012'
        }
    };

    // Ensure model for gamma exists in uploads if missing
    const hasGammaModel = uploads.some(u => u.uploadId === 'model-trojai-res50-0664' || (u.kind === 'model' && u.contributorId === 'vendor-gamma'));
    if (!hasGammaModel) {
        const m664Path = path.join(WORKSPACE_ROOT, 'model-integrity/triggers/id-00000664_class0_pattern.pt');
        const m664Hash = sha256FileSafe(m664Path) || '7b254c84d6a2b0f576b05afdedd27c1cbb1280044ac1bb93da922b91619ac929';
        const m664Size = fs.existsSync(m664Path) ? fs.statSync(m664Path).size : 604160;

        uploads.push({
            uploadId: 'model-trojai-res50-0664',
            originalName: 'id-00000664 (ResNet50 Backdoor Injected)',
            kind: 'model',
            sha256: m664Hash,
            size: m664Size,
            createdAt: '2026-09-22T14:00:00Z',
            weightsPath: 'model-integrity/triggers/id-00000664_class0_pattern.pt',
            framework: 'PyTorch',
            contributorId: 'vendor-gamma',
            contributorName: 'Vendor Gamma'
        });
    }

    // Apply assignments to existing uploads
    for (const u of uploads) {
        if (assetAssignments[u.uploadId]) {
            const assign = assetAssignments[u.uploadId];
            u.contributorId = assign.contributorId;
            u.contributorName = assign.contributorName;
            if (assign.format && !u.format) u.format = assign.format;
            if (assign.framework && !u.framework) u.framework = assign.framework;
        } else if (!u.contributorId) {
            u.contributorId = 'unassigned';
            u.contributorName = 'Unassigned';
        }
    }

    fs.writeFileSync(UPLOADS_META_FILE, JSON.stringify(uploads, null, 2), 'utf-8');
    console.log(`[OK] Updated data/uploads_meta.json with contributor associations`);

    // 3. Populate demo/contributors/ structure with metadata and symlinks
    for (const vendor of DEMO_VENDORS) {
        const vDir = path.join(DEMO_DIR, vendor.folder);
        const vDsDir = path.join(vDir, 'datasets');
        const vMdlDir = path.join(vDir, 'models');
        ensureDir(vDir);
        ensureDir(vDsDir);
        ensureDir(vMdlDir);

        const vDatasets = uploads.filter(u => u.kind === 'dataset' && u.contributorId === vendor.id);
        const vModels = uploads.filter(u => u.kind === 'model' && u.contributorId === vendor.id);

        // Create symlinks to real files where applicable
        for (const ds of vDatasets) {
            const realPath = path.resolve(WORKSPACE_ROOT, ds.datasetPath || ds.filePath);
            if (fs.existsSync(realPath)) {
                ensureSymlink(realPath, path.join(vDsDir, path.basename(realPath)));
            }
        }
        for (const mdl of vModels) {
            const realPath = path.resolve(WORKSPACE_ROOT, mdl.weightsPath || mdl.filePath);
            if (fs.existsSync(realPath)) {
                ensureSymlink(realPath, path.join(vMdlDir, path.basename(realPath)));
            }
        }

        const vMeta = {
            contributorId: vendor.id,
            name: vendor.name,
            type: vendor.type,
            description: vendor.description,
            status: vendor.status,
            createdAt: vendor.createdAt,
            updatedAt: vendor.updatedAt,
            datasets: vDatasets.map(d => ({
                id: d.uploadId,
                name: d.originalName,
                path: d.datasetPath || d.filePath,
                sha256: d.sha256,
                size: d.size,
                format: d.format || 'Standard'
            })),
            models: vModels.map(m => ({
                id: m.uploadId,
                name: m.originalName,
                path: m.weightsPath || m.filePath,
                sha256: m.sha256,
                size: m.size,
                framework: m.framework || 'PyTorch'
            }))
        };

        fs.writeFileSync(path.join(vDir, 'metadata.json'), JSON.stringify(vMeta, null, 2), 'utf-8');
        console.log(`[OK] Created demo/contributors/${vendor.folder}/metadata.json (${vDatasets.length} datasets, ${vModels.length} models)`);
    }

    console.log('[OK] Setup complete! Demo contributor asset structure is ready.');
}

if (require.main === module) {
    setup();
}

module.exports = { setup, DEMO_VENDORS };
