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

        if (req.headers['content-type']?.includes('multipart/form-data')) {
            const parsed = await parseMultipartData(req);
            files = parsed.files || [];
            contributorId = String(parsed.fields.contributorId || '').trim();
            modelId = String(parsed.fields.modelId || '').trim();
            const requestedDatasetId = String(parsed.fields.datasetId || '').trim();
            if (requestedDatasetId) {
                loadUploads();
                const existing = uploads.find(u => u.kind === 'dataset' && u.uploadId === requestedDatasetId);
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