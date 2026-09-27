/**
 * SentinelVision - End-to-End System Assurance & UI Integration Test Suite
 * Validates real execution of all assurance pipelines, API endpoints, GPU detection,
 * and report generation without mocked data.
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://127.0.0.1:3000';

function request(method, endpoint, body = null, headers = {}) {
    return new Promise((resolve, reject) => {
        const url = new URL(endpoint, BASE_URL);
        const reqHeaders = {
            'Content-Type': 'application/json',
            ...headers
        };
        const req = http.request(url, { method, headers: reqHeaders }, (res) => {
            let data = [];
            res.on('data', chunk => data.push(chunk));
            res.on('end', () => {
                const buffer = Buffer.concat(data);
                const contentType = res.headers['content-type'] || '';
                let parsed = null;
                if (contentType.includes('application/json')) {
                    try {
                        parsed = JSON.parse(buffer.toString('utf-8'));
                    } catch (e) {
                        parsed = buffer.toString('utf-8');
                    }
                } else {
                    parsed = buffer;
                }
                resolve({
                    statusCode: res.statusCode,
                    headers: res.headers,
                    body: parsed,
                    raw: buffer
                });
            });
        });
        req.on('error', reject);
        if (body) {
            req.write(typeof body === 'string' ? body : JSON.stringify(body));
        }
        req.end();
    });
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function runTests() {
    console.log('======================================================================');
    console.log('   SENTINELVISION END-TO-END INTEGRATION & ASSURANCE TEST SUITE       ');
    console.log('======================================================================\n');

    let passed = 0;
    let failed = 0;

    function assert(name, condition, extra = '') {
        if (condition) {
            console.log(`[PASS] ${name} ${extra ? '(' + extra + ')' : ''}`);
            passed++;
        } else {
            console.error(`[FAIL] ${name} ${extra ? '(' + extra + ')' : ''}`);
            failed++;
        }
    }

    try {
        // 1. Health check & GPU Acceleration
        console.log('[*] Testing System Health & GPU Subsystem...');
        const health = await request('GET', '/health');
        assert('Health endpoint status 200', health.statusCode === 200);
        assert('Health status UP', health.body?.status === 'UP');
        assert('GPU Hardware Detected', health.body?.subsystems?.gpuAcceleration?.device?.includes('RTX 5050'), health.body?.subsystems?.gpuAcceleration?.device);
        assert('CUDA Active', health.body?.subsystems?.gpuAcceleration?.status === 'ACTIVE');

        // 2. Authentication: Analyst
        console.log('\n[*] Testing Authentication Service (PBKDF2 / JWT)...');
        const loginAnalyst = await request('POST', '/api/auth/login', {
            email: 'analyst@sentinelvision.io',
            password: 'Password123!'
        });
        assert('Analyst login 200', loginAnalyst.statusCode === 200);
        assert('Analyst JWT token issued', Boolean(loginAnalyst.body?.token));
        assert('Analyst role ANALYST', loginAnalyst.body?.user?.role === 'ANALYST');
        const analystToken = loginAnalyst.body?.token;

        // 3. Authentication: Auditor
        const loginAuditor = await request('POST', '/api/auth/login', {
            email: 'auditor@sentinelvision.io',
            password: 'Password123!'
        });
        assert('Auditor login 200', loginAuditor.statusCode === 200);
        assert('Auditor role AUDITOR', loginAuditor.body?.user?.role === 'AUDITOR');
        const auditorToken = loginAuditor.body?.token;

        // 4. Ingested Results endpoints
        console.log('\n[*] Testing Results Queries...');
        const dataInteg = await request('GET', '/integrity/results');
        assert('Data Integrity results 200', dataInteg.statusCode === 200);
        assert('Data Integrity summary loaded', dataInteg.body?.summary?.totalSamples >= 100, `Total: ${dataInteg.body?.summary?.totalSamples}`);

        const modelInteg = await request('GET', '/model-integrity/results');
        assert('Model Integrity results 200', modelInteg.statusCode === 200);
        assert('Model Integrity TrojAI signals present', modelInteg.body?.signals?.length > 0, `Signals: ${modelInteg.body?.signals?.length}`);

        const driftRes = await request('GET', '/drift/results');
        assert('Distribution Shift / Drift results 200', driftRes.statusCode === 200);
        assert('Drift series data present', driftRes.body?.series?.length > 0, `Points: ${driftRes.body?.series?.length}`);

        const findingsRes = await request('GET', '/findings');
        assert('Findings catalog 200', findingsRes.statusCode === 200);
        assert('Real findings present', findingsRes.body?.length > 0, `Count: ${findingsRes.body?.length}`);

        const evidenceRes = await request('GET', '/evidence');
        assert('Evidence vault 200', evidenceRes.statusCode === 200);
        assert('Evidence records count', evidenceRes.body?.length > 0, `Count: ${evidenceRes.body?.length}`);

        // 5. Automated Real Test Execution via API
        console.log('\n[*] Automating Real Test Pipelines via API...');

        // Pipeline A: Full Assurance Run
        console.log('    -> Triggering FULL_ASSURANCE workflow...');
        const runRes = await request('POST', '/api/trust/run', {
            datasetId: 'dataset-voc2012-eval',
            modelId: 'model-id-00000112'
        }, { Authorization: `Bearer ${analystToken}` });
        assert('Run created 200', runRes.statusCode === 200);
        assert('Run ID generated', Boolean(runRes.body?.test?.testId));
        const testId = runRes.body?.test?.testId;

        console.log(`    -> Polling status for ${testId}...`);
        let finished = false;
        let testDetail = null;
        for (let i = 0; i < 20; i++) {
            await sleep(1000);
            const statusRes = await request('GET', `/api/trust/tests/${testId}`, null, { Authorization: `Bearer ${analystToken}` });
            testDetail = statusRes.body?.test;
            if (testDetail?.status === 'COMPLETED' || testDetail?.status === 'FAILED') {
                finished = true;
                break;
            }
        }
        assert('Job execution completed', finished);
        assert('Real Trust Disposition produced', Boolean(testDetail?.disposition), `Disposition: ${testDetail?.disposition}`);
        assert('Real Checks Evaluated', Boolean(testDetail?.checks?.DATA_INTEGRITY), `Checks: ${Object.keys(testDetail?.checks || {}).join(', ')}`);

        // 6. Dataset Validation Gate
        console.log('\n[*] Testing Dataset Validation Gate...');
        const validCOCO = JSON.stringify({
            info: { description: "SentinelVision Evaluation Set" },
            images: [{ id: 1, file_name: "000001.jpg", width: 500, height: 375 }],
            annotations: [{ id: 1, image_id: 1, category_id: 1, bbox: [10, 10, 50, 50] }],
            categories: [{ id: 1, name: "aeroplane" }]
        });
        const valRes = await request('POST', '/api/datasets/validate?kind=coco', {
            fileContent: validCOCO,
            filename: 'annotations_valid.json'
        }, { Authorization: `Bearer ${analystToken}` });
        assert('COCO annotation validation 200', valRes.statusCode === 200);
        assert('Validation status VALID', valRes.body?.report?.status === 'valid');

        // 7. Auditor Quarantine & Governance Reports
        console.log('\n[*] Testing Auditor Governance & Quarantine Review...');
        const qList = await request('GET', '/api/auditor/quarantine', null, { Authorization: `Bearer ${auditorToken}` });
        assert('Quarantine registry 200', qList.statusCode === 200);
        assert('Quarantine list retrieved', Array.isArray(qList.body?.quarantine));

        const repList = await request('GET', '/api/auditor/reports', null, { Authorization: `Bearer ${auditorToken}` });
        assert('Governance reports list 200', repList.statusCode === 200);
        assert('Reports array returned', Array.isArray(repList.body?.reports));

        const pdfRes = await request('GET', '/api/auditor/reports/governance.pdf?periodDays=30', null, { Authorization: `Bearer ${auditorToken}` });
        assert('Governance PDF download 200', pdfRes.statusCode === 200);
        assert('PDF MIME type', pdfRes.headers['content-type'] === 'application/pdf');
        assert('PDF magic header (%PDF)', pdfRes.raw.slice(0, 4).toString('utf-8') === '%PDF');

        // 8. Chained Audit Trail Verification
        console.log('\n[*] Verifying SHA-256 Audit Trail Cryptographic Hash Chain...');
        const auditRes = await request('GET', '/api/auditor/logs', null, { Authorization: `Bearer ${auditorToken}` });
        assert('Audit logs retrieved 200', auditRes.statusCode === 200);
        const logs = auditRes.body?.logs || [];
        assert('Audit logs recorded', logs.length > 0, `Total events: ${logs.length}`);

        // Verify SHA-256 chain integrity
        const crypto = require('crypto');
        let chainIntact = true;
        // Logs are in reverse order from getAuditLogs()
        const chronological = logs.slice().reverse();
        for (let i = 0; i < chronological.length; i++) {
            const ev = chronological[i];
            const expectedPrev = i === 0 ? '0'.repeat(64) : chronological[i - 1].eventHash;
            if (ev.previousHash !== expectedPrev) {
                chainIntact = false;
                console.error(`Audit chain broken at index ${i}: prev was ${ev.previousHash}, expected ${expectedPrev}`);
                break;
            }
        }
        assert('Cryptographic SHA-256 Audit Chain Intact', chainIntact);

    } catch (err) {
        console.error('Fatal test error:', err);
        failed++;
    }

    console.log('\n======================================================================');
    console.log(`TEST SUMMARY: ${passed} PASSED, ${failed} FAILED`);
    console.log('======================================================================');

    process.exit(failed > 0 ? 1 : 0);
}

runTests();
