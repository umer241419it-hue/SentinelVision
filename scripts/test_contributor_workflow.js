// SentinelVision — Contributor / Vendor Workflow Integration Test
// Tests:
// 1. Contributor listing & counts
// 2. Contributor detail
// 3. New contributor creation
// 4. Missing contributor on upload -> 400 error
// 5. Nonexistent contributor on upload -> 400 error
// 6. Multiple dataset upload under Vendor Alpha
// 7. Multiple model upload under Vendor Beta
// 8. Contributor exposure in /api/datasets and /api/models
// 9. Assurance job context retention

const http = require('http');

const PORT = 3000;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const REQUEST_TIMEOUT_MS = 15000;

function request(method, path, body = null, headers = {}) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, BASE_URL);
    const options = {
      method,
      hostname: url.hostname,
      port: url.port,
      path: url.pathname + url.search,
      headers: {
        ...headers
      }
    };

    let payload = null;
    if (body) {
      if (typeof body === 'object' && !Buffer.isBuffer(body) && !(headers['Content-Type'] || '').includes('multipart')) {
        payload = JSON.stringify(body);
        options.headers['Content-Type'] = 'application/json';
        options.headers['Content-Length'] = Buffer.byteLength(payload);
      } else if (Buffer.isBuffer(body)) {
        payload = body;
        options.headers['Content-Length'] = body.length;
      }
    }

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        let json = null;
        try { json = JSON.parse(data); } catch { json = data; }
        resolve({ status: res.statusCode, headers: res.headers, body: json });
      });
    });

    const timeout = setTimeout(() => {
      req.destroy(new Error(`Request timed out after ${REQUEST_TIMEOUT_MS}ms: ${method} ${path}`));
    }, REQUEST_TIMEOUT_MS);
    req.on('error', (err) => {
      clearTimeout(timeout);
      reject(err);
    });
    req.on('close', () => clearTimeout(timeout));
    if (payload) req.write(payload);
    req.end();
  });
}

function buildMultipart(fields, files, boundary = '----SentinelVisionBoundary' + Date.now()) {
  const parts = [];
  for (const [k, v] of Object.entries(fields)) {
    parts.push(Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="${k}"\r\n\r\n${v}\r\n`));
  }
  for (const f of files) {
    parts.push(Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="${f.filename}"\r\nContent-Type: application/octet-stream\r\n\r\n`));
    parts.push(Buffer.isBuffer(f.content) ? f.content : Buffer.from(f.content));
    parts.push(Buffer.from('\r\n'));
  }
  parts.push(Buffer.from(`--${boundary}--\r\n`));
  return {
    buffer: Buffer.concat(parts),
    boundary
  };
}

async function runTests() {
  console.log('=== SENTINELVISION CONTRIBUTOR WORKFLOW TEST ===\n');
  let passed = 0;
  let failed = 0;

  function assert(cond, name) {
    if (cond) {
      console.log(`[PASS] ${name}`);
      passed++;
    } else {
      console.error(`[FAIL] ${name}`);
      failed++;
    }
  }

  try {
    // 1. Check contributors list
    const res1 = await request('GET', '/api/contributors');
    assert(res1.status === 200, 'GET /api/contributors returns 200');
    assert(Array.isArray(res1.body.contributors), 'Contributors list returned');
    const alpha = res1.body.contributors.find(c => c.id === 'vendor-alpha');
    const beta = res1.body.contributors.find(c => c.id === 'vendor-beta');
    const gamma = res1.body.contributors.find(c => c.id === 'vendor-gamma');
    assert(!!alpha && !!beta && !!gamma, 'Demo contributors (Alpha, Beta, Gamma) exist');
    assert(alpha?.datasetCount >= 1 && alpha?.modelCount >= 1, 'Vendor Alpha has associated datasets and models');

    // 2. Contributor detail
    const res2 = await request('GET', '/api/contributors/vendor-alpha');
    assert(res2.status === 200, 'GET /api/contributors/vendor-alpha returns 200');
    assert(res2.body.contributor?.id === 'vendor-alpha', 'Correct contributor detail returned');
    assert(Array.isArray(res2.body.contributor?.datasets), 'Contributor datasets array present');
    assert(Array.isArray(res2.body.contributor?.models), 'Contributor models array present');

    // 3. Register a new contributor
    const testContribId = `test-vendor-${Date.now()}`;
    const res3 = await request('POST', '/api/contributors', {
      id: testContribId,
      name: 'Automated Test Vendor',
      type: 'DEMO_VENDOR',
      description: 'Temporary vendor for validation'
    });
    assert(res3.status === 201, 'POST /api/contributors creates contributor (201)');
    assert(res3.body.contributor?.id === testContribId, 'New contributor returned with assigned ID');

    // 4. Missing contributor upload must be blocked
    const dummyFile = { filename: 'test_dataset.json', content: '{"images": []}' };
    const mpNoContrib = buildMultipart({}, [dummyFile]);
    const res4 = await request('POST', '/api/datasets/upload', mpNoContrib.buffer, {
      'Content-Type': `multipart/form-data; boundary=${mpNoContrib.boundary}`
    });
    assert(res4.status === 400, 'Upload without contributor is blocked with 400 status');
    assert(typeof res4.body.error === 'string' && res4.body.error.includes('Contributor'), 'Error explains contributor is required');

    // 5. Nonexistent contributor upload must be rejected
    const mpBadContrib = buildMultipart({ contributorId: 'nonexistent-vendor-xyz' }, [dummyFile]);
    const res5 = await request('POST', '/api/datasets/upload', mpBadContrib.buffer, {
      'Content-Type': `multipart/form-data; boundary=${mpBadContrib.boundary}`
    });
    assert(res5.status === 400, 'Upload with nonexistent contributorId is rejected (400)');
    assert(typeof res5.body.error === 'string' && res5.body.error.includes('does not exist'), 'Rejection mentions contributor does not exist');

    // 6. Multiple dataset upload under Vendor Alpha
    const mpDatasets = buildMultipart(
      { contributorId: 'vendor-alpha' },
      [
        { filename: `alpha_dataset_a_${Date.now()}.json`, content: '{"images": [1, 2, 3]}' },
        { filename: `alpha_dataset_b_${Date.now()}.json`, content: '{"images": [4, 5, 6]}' }
      ]
    );
    const res6 = await request('POST', '/api/datasets/upload', mpDatasets.buffer, {
      'Content-Type': `multipart/form-data; boundary=${mpDatasets.boundary}`
    });
    assert(res6.status === 201, 'Multiple dataset upload under Vendor Alpha succeeded (201)');
    assert(res6.body.contributor?.id === 'vendor-alpha', 'Upload response confirms Vendor Alpha contributor');
    assert(res6.body.total === 2 && res6.body.successful === 2, 'All 2 datasets successfully uploaded');

    // 7. Multiple model upload under Vendor Beta
    const mpModels = buildMultipart(
      { contributorId: 'vendor-beta' },
      [
        { filename: `beta_detector_v1_${Date.now()}.pt`, content: Buffer.from('MODEL_WEIGHTS_BINARY_V1') },
        { filename: `beta_detector_v2_${Date.now()}.pt`, content: Buffer.from('MODEL_WEIGHTS_BINARY_V2') }
      ]
    );
    const res7 = await request('POST', '/api/models/upload', mpModels.buffer, {
      'Content-Type': `multipart/form-data; boundary=${mpModels.boundary}`
    });
    assert(res7.status === 201, 'Multiple model upload under Vendor Beta succeeded (201)');
    assert(res7.body.contributor?.id === 'vendor-beta', 'Upload response confirms Vendor Beta contributor');
    assert(res7.body.total === 2 && res7.body.successful === 2, 'All 2 models successfully uploaded');

    // 8. Contributor info exposed in /api/datasets and /api/models
    const res8a = await request('GET', '/api/datasets');
    const res8b = await request('GET', '/api/models');
    assert(res8a.status === 200 && Array.isArray(res8a.body.datasets), 'GET /api/datasets succeeded');
    assert(res8b.status === 200 && Array.isArray(res8b.body.models), 'GET /api/models succeeded');
    const hasContribOnDs = res8a.body.datasets.some(d => d.contributorId === 'vendor-alpha');
    const hasContribOnMdl = res8b.body.models.some(m => m.contributorId === 'vendor-beta');
    assert(hasContribOnDs, 'GET /api/datasets exposes contributorId');
    assert(hasContribOnMdl, 'GET /api/models exposes contributorId');

    // 9. Contributor filtering query
    const res9 = await request('GET', '/api/datasets?contributorId=vendor-alpha');
    assert(res9.status === 200, 'GET /api/datasets?contributorId=vendor-alpha returns 200');
    const allAlpha = res9.body.datasets.every(d => d.contributorId === 'vendor-alpha');
    assert(allAlpha, 'All returned datasets belong to vendor-alpha');

    // 10. Start assurance run and verify contributor context.
    // Use a lightweight job type so this integration test does not launch the
    // full GPU/assurance pipeline and hang while waiting for a long-running job.
    const res10 = await request('POST', '/api/trust/run', {
      testType: 'MODEL_INTEGRITY',
      datasetId: 'dataset-voc2012-clean',
      modelId: 'model-clean-res50-0028',
      contributorId: 'vendor-alpha',
      contributorName: 'Vendor Alpha'
    });
    assert(res10.status === 200, 'POST /api/trust/run returns 200');
    assert(res10.body.test?.contributorId === 'vendor-alpha', 'Assurance job retains contributorId');
    assert(res10.body.test?.contributorName === 'Vendor Alpha', 'Assurance job retains contributorName');

    console.log(`\nResults: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
  } catch (err) {
    console.error('Test execution error:', err);
    process.exit(1);
  }
}

runTests();
