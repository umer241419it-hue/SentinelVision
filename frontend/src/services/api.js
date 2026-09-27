// SentinelVision service layer.
//
// These functions are the single integration point between the UI and the
// SentinelVision backend/bridge. Today they return mock data (MOCK_MODE=true)
// so the UI runs without any backend. When you are ready to wire up the real
// bridge, set MOCK_MODE=false and the same functions will call:
//
//   GET  http://<bridge>/health       -> Express bridge health (bridge/src/index.js)
//   POST http://<bridge>/findings     -> submit an 8-field finding to the ledger
//   GET  http://<bridge>/findings/:id -> read a finding from the ledger by assetID
//
// The real finding schema everywhere is:
//   { assetID, moduleName, reason, evidenceHash, confidence, severity, disposition, timestamp }

import {
  MOCK_FINDINGS,
  DRIFT_SUMMARY,
  buildDriftSeries,
  buildDriftWindows,
  DATA_INTEGRITY_SUMMARY,
  buildIntegrityBreakdown,
  buildIntegritySamples,
  MODEL_INTEGRITY_SUMMARY,
  MODEL_SIGNALS,
  MODEL_METADATA,
  buildEvidence,
  FABRIC_INFO,
  buildLedgerTransactions,
  SYSTEM_HEALTH,
  buildActivitySeries,
  OVERVIEW_KPIS,
  THREAT_OVERVIEW
} from '../data/mockData';

export const MOCK_MODE = false;

// Bridge base URL — same Express service as bridge/src/index.js (default port 3000).
const BRIDGE_BASE_URL = import.meta.env.VITE_BRIDGE_URL || 'http://127.0.0.1:3000';

async function bridgeFetch(path, options) {
  const res = await fetch(`${BRIDGE_BASE_URL}${path}`, options);
  if (!res.ok) {
    const err = new Error(`Bridge request failed: ${res.status} ${res.statusText}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

const delay = (ms = 260) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------------------
// Findings
// ---------------------------------------------------------------------------
export async function getFindings() {
  if (MOCK_MODE) {
    await delay();
    return MOCK_FINDINGS;
  }
  // Real integration: the bridge currently exposes single-finding reads.
  // Aggregate sources (drift/integrity results JSON) can be served by the bridge
  // later; until then keep mock mode for list views and use queryFinding for detail.
  const data = await bridgeFetch('/findings');
  return data;
}

export async function getFindingById(id) {
  if (MOCK_MODE) {
    await delay(160);
    return MOCK_FINDINGS.find((f) => f.id === id || f.assetID === id) || null;
  }
  const data = await bridgeFetch(`/findings/${encodeURIComponent(id)}`);
  return data.data;
}

// ---------------------------------------------------------------------------
// Drift monitor
// ---------------------------------------------------------------------------
export async function getDriftResults() {
  if (MOCK_MODE) {
    await delay();
    return {
      summary: DRIFT_SUMMARY,
      series: buildDriftSeries(),
      windows: buildDriftWindows()
    };
  }
  return bridgeFetch('/drift/results');
}

// ---------------------------------------------------------------------------
// Data integrity
// ---------------------------------------------------------------------------
export async function getDataIntegrityResults() {
  if (MOCK_MODE) {
    await delay();
    return {
      summary: DATA_INTEGRITY_SUMMARY,
      breakdown: buildIntegrityBreakdown(),
      samples: buildIntegritySamples()
    };
  }
  return bridgeFetch('/integrity/results');
}

// ---------------------------------------------------------------------------
// Model integrity
// ---------------------------------------------------------------------------
export async function getModelIntegrityResults() {
  if (MOCK_MODE) {
    await delay();
    return {
      summary: MODEL_INTEGRITY_SUMMARY,
      signals: MODEL_SIGNALS,
      metadata: MODEL_METADATA
    };
  }
  return bridgeFetch('/model-integrity/results');
}

// ---------------------------------------------------------------------------
// Evidence
// ---------------------------------------------------------------------------
export async function getEvidence() {
  if (MOCK_MODE) {
    await delay();
    return buildEvidence();
  }
  return bridgeFetch('/evidence');
}

// ---------------------------------------------------------------------------
// Fabric ledger
// ---------------------------------------------------------------------------
export async function getLedgerTransactions() {
  if (MOCK_MODE) {
    await delay();
    return { info: FABRIC_INFO, transactions: buildLedgerTransactions() };
  }
  return bridgeFetch('/ledger/transactions');
}

// ---------------------------------------------------------------------------
// System health (mirrors results/system_status.json)
// ---------------------------------------------------------------------------
export async function getSystemHealth() {
  if (MOCK_MODE) {
    await delay();
    return SYSTEM_HEALTH;
  }
  return bridgeFetch('/health');
}

// ---------------------------------------------------------------------------
// Bridge connectivity probe (used by Topbar/Sidebar status + Settings)
// ---------------------------------------------------------------------------
export async function getBridgeStatus() {
  if (MOCK_MODE) {
    await delay(120);
    return { status: 'UP', service: 'SentinelVision-Fabric-Bridge', mock: true };
  }
  try {
    const data = await bridgeFetch('/health');
    return { ...data, mock: false };
  } catch {
    return { status: 'DOWN', mock: false };
  }
}

// ---------------------------------------------------------------------------
// Overview aggregates
// ---------------------------------------------------------------------------
export async function getOverview() {
  if (MOCK_MODE) {
    await delay(180);
    return { kpis: OVERVIEW_KPIS, threats: THREAT_OVERVIEW };
  }
  return bridgeFetch('/overview');
}

export async function getActivitySeries(range) {
  if (MOCK_MODE) {
    await delay(140);
    return buildActivitySeries(range);
  }
  return bridgeFetch(`/overview/activity?range=${encodeURIComponent(range)}`);
}
