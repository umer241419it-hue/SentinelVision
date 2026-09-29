// SentinelVision mock data layer.
// Structures mirror the real project outputs:
//  - Findings: { assetID, moduleName, reason, evidenceHash, confidence, severity, disposition, timestamp }
//    (matches bridge/src/index.js validation and the chaincode 8-field payload)
//  - Drift evidence: MMD value vs calibrated threshold, windows, assessments
//  - Data integrity: flagged samples with checks (duplicate/ood/label_flip), severity distribution
//  - Model integrity: Neural Cleanse + MAD anomaly index, STRIP corroboration (scoring_results.json)

export const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
export const MODULES = ['DriftMonitor', 'DataIntegrity', 'ModelIntegrity'];

// Deterministic PRNG so numbers are stable across reloads/dev refreshes.
function mulberry32(seed) {
  let a = seed;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = mulberry32(0x5e11a);

function hex(len) {
  let s = '';
  for (let i = 0; i < len; i++) s += '0123456789abcdef'[Math.floor(rand() * 16)];
  return s;
}

const NOW = Date.UTC(2026, 8, 29, 9, 28, 0); // presentation session timestamp
const minutesAgo = (m) => new Date(NOW - m * 60000).toISOString();
const hoursAgo = (h) => new Date(NOW - h * 3600000).toISOString();

// ---------------------------------------------------------------------------
// Findings
// ---------------------------------------------------------------------------
const REASONS = {
  DriftMonitor: [
    'MMD 0.093 exceeds the calibrated threshold 0.0289; operational diagnostics changed with it — operational shift plausible.',
    'MMD 0.075 exceeds the calibrated threshold 0.0289 and no measured operational diagnostic explains the change; unexplained shift — surface for human review.',
    'Insufficient live samples: window below minimum_samples; INSUFFICIENT_EVIDENCE surfaced for review.'
  ],
  DataIntegrity: [
    'Near-duplicate of img_0017.png (standardized cosine 1.000 >= threshold 0.99).',
    'Potential label flip: predicted label conflicts with the weak label key for this sample.',
    'Out-of-distribution sample: embedding distance exceeds the 99th percentile of the reference battery.',
    'Near-duplicate of img_0081.png (standardized cosine 1.000 >= threshold 0.99).'
  ],
  ModelIntegrity: [
    'Class 2 flagged by Neural Cleanse + MAD (anomaly index 3.13), independently corroborated by STRIP entropy suppression — QUARANTINE recommended.',
    'Class 3 flagged by Neural Cleanse + MAD (anomaly index 4.84), STRIP points to a different class — conflicting signals, human review required.',
    'Suspicious activation pattern: probe detected concentrated activations on trigger candidates.',
    'No anomalous class detected by Neural Cleanse + MAD (max anomaly index 0.76, below threshold).'
  ]
};

function dispositionFor(severity) {
  if (severity === 'CRITICAL') return 'QUARANTINE';
  if (severity === 'HIGH') return 'REVIEW';
  if (severity === 'MEDIUM') return 'REVIEW';
  return 'ACCEPT';
}

function buildFindings(count = 42) {
  const findings = [];
  for (let i = 0; i < count; i++) {
    const mod = MODULES[i % 3];
    const reasonList = REASONS[mod];
    const sevPool = i % 3 === 0 ? ['HIGH', 'CRITICAL', 'MEDIUM', 'HIGH'] : ['MEDIUM', 'LOW', 'MEDIUM', 'HIGH', 'LOW'];
    const severity = sevPool[i % sevPool.length];
    const confidence =
      severity === 'CRITICAL' ? 0.85 + rand() * 0.14 : 0.55 + rand() * 0.4;

    findings.push({
      id: `FIND-${1000 + i}`,
      assetID:
        mod === 'DriftMonitor'
          ? `drift-reference-v1-window-${String(i).padStart(6, '0')}-${hex(12)}`
          : mod === 'DataIntegrity'
            ? `image-dup_${String(i % 10).padStart(4, '0')}_of_img_${String(17 + i).padStart(4, '0')}.png`
            : `model-${hex(8)}`,
      moduleName: mod,
      reason: reasonList[i % reasonList.length],
      evidenceHash: hex(64),
      confidence: Math.round(confidence * 100) / 100,
      severity,
      disposition: dispositionFor(severity),
      timestamp: minutesAgo(i * 37 + 3),
      contributorId: ['vendor-alpha', 'vendor-beta', 'vendor-gamma'][i % 3],
      contributorName: ['Vendor Alpha', 'Vendor Beta', 'Vendor Gamma'][i % 3],
      ledgerStatus: i % 7 === 3 ? 'PENDING' : 'COMMITTED',
      txId: i % 7 === 3 ? null : hex(64)
    });
  }
  return findings;
}

export const MOCK_FINDINGS = buildFindings(42);

// ---------------------------------------------------------------------------
// Drift monitor
// ---------------------------------------------------------------------------
export const DRIFT_SUMMARY = {
  currentScore: 0.0731,
  threshold: 0.028903,
  referenceDataset: 'reference-battery (reference-v1, 120 images, backbone=pixelstat, dim=734)',
  monitoringWindow: 'window-000018-a41c93b02d7e · 100 live images',
  detectionStatus: 'SHIFT_DETECTED',
  calibrationId: 'threshold-1aff0a55ed0f',
  lastChecked: minutesAgo(4)
};

export function buildDriftSeries() {
  const points = [];
  let base = 0.012 + rand() * 0.008;
  for (let i = 0; i < 24; i++) {
    const spike = i === 14 || i === 19 || i === 23;
    base = Math.max(0.006, base + (rand() - 0.48) * 0.006);
    const value = spike ? 0.06 + rand() * 0.09 : base;
    points.push({
      time: `${String((i + 6) % 24).padStart(2, '0')}:00`,
      drift: Math.round(value * 10000) / 10000,
      anomaly: value > DRIFT_SUMMARY.threshold,
      score: Math.round(value * 10000) / 10000
    });
  }
  return points;
}

export function buildDriftWindows(count = 12) {
  const rows = [];
  for (let i = 0; i < count; i++) {
    const mmd = i === count - 1 ? 0.093 : 0.004 + rand() * 0.03;
    const status = mmd > DRIFT_SUMMARY.threshold ? 'ALERT' : 'OK';
    rows.push({
      window: `window-${String(i).padStart(6, '0')}-${hex(12)}`,
      mmdScore: Math.round(mmd * 1000000) / 1000000,
      threshold: DRIFT_SUMMARY.threshold,
      confidence: status === 'ALERT' ? 0.9 : Math.round((0.6 + rand() * 0.3) * 100) / 100,
      status,
      timestamp: minutesAgo((count - i) * 62)
    });
  }
  return rows;
}

// ---------------------------------------------------------------------------
// Data integrity
// ---------------------------------------------------------------------------
export const DATA_INTEGRITY_SUMMARY = {
  totalSamples: 120,
  duplicates: 20,
  labelFlips: 6,
  oodSamples: 9,
  suspicious: 35,
  checksRun: ['duplicate', 'ood', 'label_flip'],
  lastRun: hoursAgo(2)
};

export function buildIntegrityBreakdown() {
  return [
    { name: 'Clean', value: 85, color: '#34d399' },
    { name: 'Duplicate', value: 20, color: '#60a5fa' },
    { name: 'Label Flip', value: 6, color: '#fbbf24' },
    { name: 'OOD', value: 9, color: '#a78bfa' }
  ];
}

export function buildIntegritySamples(count = 16) {
  const types = ['duplicate', 'ood', 'label_flip'];
  const rows = [];
  for (let i = 0; i < count; i++) {
    const type = types[i % 3];
    const severity = type === 'label_flip' ? 'HIGH' : type === 'ood' ? 'MEDIUM' : 'MEDIUM';
    rows.push({
      sampleId:
        type === 'duplicate'
          ? `dup_${String(i % 10).padStart(4, '0')}_of_img_${String(17 + i).padStart(4, '0')}.png`
          : `img_${String(200 + i).padStart(4, '0')}.png`,
      detectionType: type,
      confidence: Math.round((0.6 + rand() * 0.38) * 100) / 100,
      severity,
      disposition: dispositionFor(severity),
      evidenceHash: hex(64),
      timestamp: minutesAgo(i * 47 + 11)
    });
  }
  return rows;
}

// ---------------------------------------------------------------------------
// Model integrity
// ---------------------------------------------------------------------------
export const MODEL_INTEGRITY_SUMMARY = {
  modelId: 'id-00000112',
  modelStatus: 'QUARANTINE_RECOMMENDED',
  integrityScore: 92,
  integrityConfidence: 0.92,
  poisoningRisk: 'MEDIUM',
  triggerDetection: 'FLAGGED (class 2, anomaly index 3.13)',
  activationAnomaly: 'DETECTED — STRIP entropy suppression corroborated',
  validationStatus: 'PASSED (dual-direction MMD proof)',
  cleanModels: 7,
  reviewModels: 5,
  quarantinedModels: 3
};

export const MODEL_SIGNALS = [
  { name: 'Neural Cleanse + MAD', status: 'FLAGGED', detail: 'Class 2 anomaly index 3.13 (threshold 2.0)', ok: false },
  { name: 'STRIP Entropy', status: 'CORROBORATED', detail: 'Entropy suppression on class 2', ok: false },
  { name: 'Activation Probe', status: 'ANOMALY', detail: 'Concentrated activations on trigger candidates', ok: false },
  { name: 'Weight Hash Check', status: 'PASS', detail: 'Model artifact digest matches signed manifest', ok: true },
  { name: 'Validation Suite', status: 'PASS', detail: 'Detection rates + dual-direction MMD proof OK', ok: true }
];

export const MODEL_METADATA = {
  architecture: 'ResNet-18 (Task 1)',
  inputShape: '3×64×64',
  classes: 5,
  parameters: '11.2M',
  checkpoint: 'id-00000112/best.pt',
  trainedAt: new Date(Date.UTC(2026, 7, 11, 7, 30, 0)).toISOString()
};

// ---------------------------------------------------------------------------
// Evidence vault
// ---------------------------------------------------------------------------
export function buildEvidence(count = 14) {
  const sources = MODULES;
  const rows = [];
  for (let i = 0; i < count; i++) {
    const src = sources[i % 3];
    rows.push({
      evidenceId: hex(64),
      sourceModule: src,
      relatedFinding: `FIND-${1000 + i}`,
      createdAt: minutesAgo(i * 41 + 7),
      verificationStatus: i === 4 ? 'UNVERIFIED' : 'VERIFIED',
      schema:
        src === 'DriftMonitor'
          ? 'sentinelvision.drift-evidence/v1'
          : src === 'DataIntegrity'
            ? 'sentinelvision.integrity-evidence/v1'
            : 'sentinelvision.model-evidence/v1'
    });
  }
  return rows;
}

// ---------------------------------------------------------------------------
// Fabric ledger
// ---------------------------------------------------------------------------
export const FABRIC_INFO = {
  networkStatus: 'CONNECTED',
  channel: 'mychannel',
  chaincode: 'basic',
  latestBlock: 247,
  totalFindings: MOCK_FINDINGS.filter((f) => f.ledgerStatus === 'COMMITTED').length,
  organization: 'Org1MSP',
  node: 'peer0.org1.example.com:7051'
};

export function buildLedgerTransactions(count = 12) {
  const committed = MOCK_FINDINGS.filter((f) => f.ledgerStatus === 'COMMITTED').slice(0, count);
  return committed.map((f, i) => ({
    txId: f.txId,
    findingId: f.id,
    assetId: f.assetID,
    moduleName: f.moduleName,
    timestamp: f.timestamp,
    status: i === 0 ? 'COMMITTED' : 'COMMITTED',
    block: FABRIC_INFO.latestBlock - i
  }));
}

// ---------------------------------------------------------------------------
// System health (mirrors results/system_status.json steps)
// ---------------------------------------------------------------------------
export const SYSTEM_HEALTH = {
  overall: 'HEALTHY',
  score: 94,
  lastChecked: minutesAgo(2),
  services: [
    { name: 'Python Dependencies', status: 'PASS', detail: 'numpy=OK PIL=OK sklearn=OK scipy=OK cleanlab=OK', uptime: '14d 06h' },
    { name: 'Drift Monitor', status: 'PASS', detail: 'reference battery built: 120 images, backbone=pixelstat, dim=734', uptime: '14d 06h' },
    { name: 'Data Integrity', status: 'PASS', detail: '120 images, 41 flagged across duplicate/ood/label_flip checks', uptime: '14d 06h' },
    { name: 'Model Integrity', status: 'WARNING', detail: '3 models in QUARANTINE pending human review', uptime: '14d 06h' },
    { name: 'Fabric Bridge', status: 'PASS', detail: 'Express bridge listening on :3000, gateway initialized', uptime: '3d 11h' },
    { name: 'Hyperledger Fabric', status: 'PASS', detail: 'mychannel/basic — peer0.org1 committed 247 blocks', uptime: '3d 11h' }
  ],
  history: [
    { time: '00:00', score: 96 },
    { time: '04:00', score: 94 },
    { time: '08:00', score: 91 },
    { time: '12:00', score: 93 },
    { time: '16:00', score: 95 },
    { time: '20:00', score: 94 },
    { time: 'Now', score: 94 }
  ]
};

// ---------------------------------------------------------------------------
// Overview aggregates
// ---------------------------------------------------------------------------
export function buildActivitySeries(range = '24H') {
  const n = range === '24H' ? 24 : range === '7D' ? 7 : 30;
  const label = (i) =>
    range === '24H'
      ? `${String(i).padStart(2, '0')}:00`
      : range === '7D'
        ? ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][i]
        : `${i + 1} Sep`;

  const series = [];
  for (let i = 0; i < n; i++) {
    series.push({
      time: label(i),
      drift: Math.max(0, Math.round(rand() * 6 - (range === '24H' ? 2 : 1))),
      dataIntegrity: Math.max(0, Math.round(rand() * 8)),
      modelIntegrity: Math.max(0, Math.round(rand() * 4 - 0.6))
    });
  }
  return series;
}

export function buildSparkline(seed, n = 12) {
  const r = mulberry32(seed);
  const out = [];
  let v = 50;
  for (let i = 0; i < n; i++) {
    v = Math.max(6, Math.min(96, v + (r() - 0.5) * 26));
    out.push(Math.round(v));
  }
  return out;
}

export const OVERVIEW_KPIS = {
  systemHealth: { value: '94%', status: 'HEALTHY', trend: '+2.1%', up: true },
  activeFindings: { value: 14, status: 'OPEN', trend: '+3 today', up: true },
  driftEvents: { value: 6, status: '2 CRITICAL', trend: '+1', up: true },
  integrityAlerts: { value: 35, status: 'REVIEW', trend: '-4', up: false },
  ledgerTx: { value: 213, status: 'COMMITTED', trend: '+12', up: true }
};

export const THREAT_OVERVIEW = [
  { level: 'Critical', count: 15, color: '#f87171' },
  { level: 'High', count: 37, color: '#fb923c' },
  { level: 'Medium', count: 1, color: '#fbbf24' }
];
