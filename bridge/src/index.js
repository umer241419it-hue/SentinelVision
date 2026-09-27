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