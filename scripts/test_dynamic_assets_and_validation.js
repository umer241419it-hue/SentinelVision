// SentinelVision — Comprehensive Dynamic Registry and Validation Test Suite
// Covers all 7 required user test cases:
// 1. Dynamic model registry & validation
// 2. Complete model folder upload with preserved paths
// 3. Dynamic dataset registry & reuse without re-upload
// 4. Complete dataset folder upload with preserved relative paths
// 5. YOLO dataset validation
// 6. COCO dataset validation (verifying NO spurious YOLO warnings)
// 7. Failure handling for invalid asset bundles

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const authService = require('../bridge/src/services/authService');

const PORT = 3000;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const token = authService.signJwt({
  id: 'usr-analyst-001',
  email: 'analyst@sentinelvision.io',
  role: 'ANALYST',
  roles: ['ANALYST']
});

function request(method, reqPath, body = null, headers = {}) {
  return new Promise((resolve, reject) => {
    const url = new URL(reqPath, BASE_URL);
    const options = {
      method,
      hostname: url.hostname,
      port: url.port,
      path: url.pathname + url.search,
      headers: {
        Authorization: `Bearer ${token}`,
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

    req.on('error', reject);
    if (payload) req.write(payload);
    req.end();
  });
}

function buildMultipart(fields, files, boundary = '----SentinelBoundary' + Date.now()) {
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

// 1x1 valid PNG image buffer
const SAMPLE_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==',
  'base64'
);

async function run() {
  console.log('===============================================================');
  console.log(' SENTINELVISION DYNAMIC REGISTRY & VALIDATION SUITE');
  console.log('===============================================================\n');

  let passed = 0;
  let failed = 0;

  function assert(cond, name, details = '') {
    if (cond) {
      console.log(`[PASS] ${name}`);
      passed++;
    } else {
      console.error(`[FAIL] ${name} ${details ? '(' + details + ')' : ''}`);
      failed++;
    }
  }

  // -------------------------------------------------------------------------
  // TEST 1: Dynamic Model Registry
  // -------------------------------------------------------------------------
  console.log('--- TEST 1: Dynamic Model Registry ---');
  const resModels1 = await request('GET', '/api/models');
  assert(resModels1.status === 200, 'GET /api/models returns 200');
  assert(Array.isArray(resModels1.body.models), 'GET /api/models returns models array');
  const initialModelCount = resModels1.body.models.length;
  console.log(`  Initial registered models: ${initialModelCount}`);
  for (const m of resModels1.body.models) {
    assert(typeof m.available === 'boolean', `Model ${m.id} has dynamic availability (${m.available ? 'AVAILABLE' : 'UNAVAILABLE'})`);
  }

  // Upload single model
  const dummyWeights = Buffer.from('FAKE_PYTORCH_WEIGHTS_DATA_FOR_INTEGRITY_CHECK_' + Date.now());
  const mp1 = buildMultipart({ contributorId: 'vendor-alpha' }, [
    { filename: 'model_dynamic_test.pt', content: dummyWeights }
  ]);
  const resUploadModel = await request('POST', '/api/models/upload', mp1.buffer, {
    'Content-Type': `multipart/form-data; boundary=${mp1.boundary}`
  });
  assert(resUploadModel.status === 201, 'POST /api/models/upload returns 201');
  const uploadedModelId = resUploadModel.body.results?.[0]?.uploadId;
  assert(Boolean(uploadedModelId), 'Uploaded model has uploadId: ' + uploadedModelId);

  // Check that it now appears dynamically in GET /api/models
  const resModels2 = await request('GET', '/api/models');
  const foundUploadedModel = resModels2.body.models.find(m => m.id === uploadedModelId);
  assert(Boolean(foundUploadedModel), 'Uploaded model is dynamically discovered in /api/models');
  assert(foundUploadedModel?.available === true, 'Uploaded model is marked available: true on disk');

  // Validate the model
  const resValModel = await request('POST', `/api/models/validate/${encodeURIComponent(uploadedModelId)}`);
  assert(resValModel.status === 200, 'POST /api/models/validate/:id returns 200');
  assert(resValModel.body.report?.modelId === uploadedModelId, 'Model validation report matches uploadId');
  assert(resValModel.body.report?.computedSha256 != null, 'Computed SHA-256 generated for model artifact');

  // -------------------------------------------------------------------------
  // TEST 2: Model Folder Upload
  // -------------------------------------------------------------------------
  console.log('\n--- TEST 2: Model Folder Upload (Preserving Folder Structure) ---');
  const folderFiles = [
    { filename: 'custom_vision_model/model.pt', content: dummyWeights },
    { filename: 'custom_vision_model/config.json', content: JSON.stringify({ architecture: 'resnet50', num_classes: 10 }) },
    { filename: 'custom_vision_model/labels.txt', content: 'cat\ndog\ncar\nbird\n' },
    { filename: 'custom_vision_model/metadata.json', content: JSON.stringify({ author: 'Vendor Alpha', version: '1.2.0' }) }
  ];
  const mpFolder = buildMultipart({ contributorId: 'vendor-alpha' }, folderFiles);
  const resFolderUpload = await request('POST', '/api/models/upload', mpFolder.buffer, {
    'Content-Type': `multipart/form-data; boundary=${mpFolder.boundary}`
  });
  assert(resFolderUpload.status === 201, 'POST /api/models/upload for folder returns 201');
  const folderModelId = resFolderUpload.body.results?.[0]?.uploadId;
  assert(Boolean(folderModelId), 'Model folder registered with uploadId: ' + folderModelId);
  assert(resFolderUpload.body.results?.[0]?.filename === 'custom_vision_model', 'Folder name preserved as originalName: custom_vision_model');

  // Confirm folder structure on disk in data/uploads/
  const uploadsDir = path.resolve(__dirname, '../data/uploads', folderModelId);
  assert(fs.existsSync(uploadsDir), 'Model folder exists on disk in data/uploads/' + folderModelId);
  assert(fs.existsSync(path.join(uploadsDir, 'custom_vision_model/config.json')), 'Nested config.json preserved in model folder');
  assert(fs.existsSync(path.join(uploadsDir, 'custom_vision_model/model.pt')), 'Nested model.pt preserved in model folder');

  // Validate the model folder
  const resValFolder = await request('POST', `/api/models/validate/${encodeURIComponent(folderModelId)}`);
  assert(resValFolder.status === 200, 'POST /api/models/validate on model folder returns 200');
  assert(resValFolder.body.report?.errors?.length === 0, 'Model folder passes structural validation (0 errors)');
  assert(resValFolder.body.report?.extension === '.pt', 'Model folder identified primary weights extension: .pt');

  // -------------------------------------------------------------------------
  // TEST 3: Dynamic Dataset Registry & Reuse Without Re-upload
  // -------------------------------------------------------------------------
  console.log('\n--- TEST 3: Dynamic Dataset Registry & Reuse Without Re-upload ---');
  const resDatasets1 = await request('GET', '/api/datasets');
  assert(resDatasets1.status === 200, 'GET /api/datasets returns 200');
  assert(Array.isArray(resDatasets1.body.datasets), 'GET /api/datasets returns array');
  for (const d of resDatasets1.body.datasets) {
    assert(typeof d.available === 'boolean', `Dataset ${d.id} has dynamic availability: ${d.available ? 'AVAILABLE' : 'UNAVAILABLE'}`);
  }

  // Validate an existing registered dataset by ID without re-uploading files
  const existingDs = resDatasets1.body.datasets.find(d => d.available === true);
  assert(Boolean(existingDs), 'Found available registered dataset for reuse: ' + existingDs?.id);
  if (existingDs) {
    const mpReuse = buildMultipart({ contributorId: existingDs.contributorId || 'vendor-alpha', datasetId: existingDs.id }, []);
    const resReuse = await request('POST', `/api/datasets/validate?kind=${encodeURIComponent(existingDs.format.toLowerCase() || 'yolo')}`, mpReuse.buffer, {
      'Content-Type': `multipart/form-data; boundary=${mpReuse.boundary}`
    });
    assert(resReuse.status === 200, 'Validating registered dataset without re-upload returns 200');
    assert(resReuse.body.report?.datasetId === existingDs.id, 'Validation report confirmed registered dataset ID retained');
  }

  // -------------------------------------------------------------------------
  // TEST 4: Dataset Folder Upload (Preserving Relative Paths)
  // -------------------------------------------------------------------------
  console.log('\n--- TEST 4: Complete Dataset Folder Upload with Preserved Structure ---');
  const datasetFolderFiles = [
    { filename: 'my_survey_dataset/images/sample01.png', content: SAMPLE_PNG },
    { filename: 'my_survey_dataset/images/sample02.png', content: SAMPLE_PNG },
    { filename: 'my_survey_dataset/labels/sample01.txt', content: '0 0.5 0.5 0.3 0.3\n' },
    { filename: 'my_survey_dataset/labels/sample02.txt', content: '0 0.4 0.4 0.2 0.2\n' },
    { filename: 'my_survey_dataset/data.yaml', content: 'names:\n  - survey_marker\nnc: 1\n' }
  ];
  const mpDsFolder = buildMultipart({ contributorId: 'vendor-alpha' }, datasetFolderFiles);
  const resDsFolder = await request('POST', '/api/datasets/validate', mpDsFolder.buffer, {
    'Content-Type': `multipart/form-data; boundary=${mpDsFolder.boundary}`
  });
  assert(resDsFolder.status === 200, 'POST /api/datasets/validate with complete folder returns 200');
  const registeredDsId = resDsFolder.body.report?.datasetId;
  assert(Boolean(registeredDsId), 'Dataset folder registered with ID: ' + registeredDsId);
  assert(resDsFolder.body.report?.datasetName === 'my_survey_dataset', 'Dataset folder preserved root directory name: my_survey_dataset');

  // Verify directory structure on disk
  const dsOnDisk = path.resolve(__dirname, '../data/uploads', registeredDsId);
  assert(fs.existsSync(dsOnDisk), 'Dataset folder exists in data/uploads/' + registeredDsId);
  assert(fs.existsSync(path.join(dsOnDisk, 'my_survey_dataset/images/sample01.png')), 'Nested images/sample01.png preserved');
  assert(fs.existsSync(path.join(dsOnDisk, 'my_survey_dataset/labels/sample01.txt')), 'Nested labels/sample01.txt preserved');

  // -------------------------------------------------------------------------
  // TEST 5: YOLO Dataset Validation
  // -------------------------------------------------------------------------
  console.log('\n--- TEST 5: YOLO Dataset Validation ---');
  assert(resDsFolder.body.report?.format === 'YOLO', 'Dataset format correctly detected as YOLO');
  assert(resDsFolder.body.report?.stats?.images === 2, 'YOLO stats detected 2 images');
  assert(resDsFolder.body.report?.stats?.annotation_files === 2, 'YOLO stats detected 2 annotation files');
  assert(resDsFolder.body.report?.errors === 0, 'YOLO dataset has 0 structural errors');

  // -------------------------------------------------------------------------
  // TEST 6: COCO Dataset Validation (Verifying NO Spurious YOLO Warnings)
  // -------------------------------------------------------------------------
  console.log('\n--- TEST 6: COCO Dataset Validation (No Spurious YOLO Warnings) ---');
  const cocoJson = {
    images: [
      { id: 1, file_name: 'coco_img1.png', width: 64, height: 64 },
      { id: 2, file_name: 'coco_img2.png', width: 64, height: 64 }
    ],
    annotations: [
      { id: 101, image_id: 1, category_id: 1, bbox: [10, 10, 20, 20] },
      { id: 102, image_id: 2, category_id: 1, bbox: [5, 5, 15, 15] }
    ],
    categories: [
      { id: 1, name: 'vehicle' }
    ]
  };
  const cocoFiles = [
    { filename: 'coco_benchmark/images/coco_img1.png', content: SAMPLE_PNG },
    { filename: 'coco_benchmark/images/coco_img2.png', content: SAMPLE_PNG },
    { filename: 'coco_benchmark/annotations/instances.json', content: JSON.stringify(cocoJson) }
  ];
  // Deliberately omit ?kind=coco or pass ?kind=coco to verify format auto-detection
  const mpCoco = buildMultipart({ contributorId: 'vendor-alpha' }, cocoFiles);
  const resCoco = await request('POST', '/api/datasets/validate', mpCoco.buffer, {
    'Content-Type': `multipart/form-data; boundary=${mpCoco.boundary}`
  });
  assert(resCoco.status === 200, 'POST /api/datasets/validate on COCO dataset returns 200');
  assert(resCoco.body.report?.format === 'COCO', 'Format auto-detected as COCO');

  const warnings = (resCoco.body.report?.warning_details || []).map(w => w.message);
  const errors = (resCoco.body.report?.error_details || []).map(e => e.message);
  const allMessages = [...warnings, ...errors].join(' ');

  assert(!allMessages.includes('No YOLO annotation .txt files found'), 'Does NOT report "No YOLO annotation .txt files found"');
  assert(!allMessages.includes('No .yaml/.yml dataset configuration was found'), 'Does NOT report "No .yaml/.yml dataset configuration was found"');
  assert(resCoco.body.report?.stats?.images === 2, 'COCO processed 2 images');
  assert(resCoco.body.report?.stats?.annotations === 2, 'COCO processed 2 annotations');

  // -------------------------------------------------------------------------
  // TEST 7: Failure Handling
  // -------------------------------------------------------------------------
  console.log('\n--- TEST 7: Failure Handling for Invalid Folder ---');
  // Upload folder with corrupted annotations / missing required data
  const invalidFiles = [
    { filename: 'invalid_dataset/images/broken.png', content: SAMPLE_PNG },
    { filename: 'invalid_dataset/labels/broken.txt', content: 'NOT_A_VALID_YOLO_LINE\nANOTHER_CORRUPTED_LINE\n' }
  ];
  const mpInvalid = buildMultipart({ contributorId: 'vendor-alpha' }, invalidFiles);
  const resInvalid = await request('POST', '/api/datasets/validate', mpInvalid.buffer, {
    'Content-Type': `multipart/form-data; boundary=${mpInvalid.boundary}`
  });
  assert(resInvalid.status === 200, 'POST /api/datasets/validate returns 200 with report');
  assert(resInvalid.body.report?.status === 'invalid' || resInvalid.body.report?.errors > 0, 'Invalid dataset correctly flagged with status: invalid or errors > 0');
  assert(resInvalid.body.report?.error_details?.length > 0, 'Invalid dataset contains explicit error details rather than fake PASS');

  // Summary
  console.log('\n===============================================================');
  console.log(` RESULTS: ${passed} PASSED, ${failed} FAILED`);
  console.log('===============================================================');

  if (failed > 0) {
    process.exit(1);
  }
}

run().catch((err) => {
  console.error('Test execution failed:', err);
  process.exit(1);
});
