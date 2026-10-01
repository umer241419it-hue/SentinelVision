// SentinelVision live service layer.
// Dashboard data always comes from the local Express bridge; demo/mock mode is removed.

export const BRIDGE_BASE_URL = import.meta.env.VITE_BRIDGE_URL || 'http://127.0.0.1:3000';

async function bridgeFetch(path, options = {}) {
  const res = await fetch(BRIDGE_BASE_URL + path, {
    ...options,
    headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...(options.headers || {}) }
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(body?.error || body?.details || `Bridge request failed: ${res.status} ${res.statusText}`);
    err.status = res.status;
    throw err;
  }
  return body;
}

export async function getFindings() {
  const data = await bridgeFetch('/findings');
  return Array.isArray(data) ? data : (data?.findings || []);
}
export async function getFindingById(id) {
  const data = await bridgeFetch(`/findings/${encodeURIComponent(id)}`);
  return data?.data || data || null;
}
export function getDriftResults() { return bridgeFetch('/drift/results'); }
export function getDataIntegrityResults() { return bridgeFetch('/integrity/results'); }
export function getModelIntegrityResults() { return bridgeFetch('/model-integrity/results'); }
export function getEvidence() { return bridgeFetch('/evidence'); }
export function verifyEvidence(evidenceId) { return bridgeFetch(`/evidence/${encodeURIComponent(evidenceId)}/verify`); }
export function getLedgerTransactions() { return bridgeFetch('/ledger/transactions'); }

export async function getSystemHealth() {
  const raw = await bridgeFetch('/health');
  if (raw?.services) return raw;
  const subsystems = raw?.subsystems || {};
  const statusMap = { ONLINE: 'PASS', ACTIVE: 'PASS', HEALTHY: 'PASS', READY: 'PASS', OPERATIONAL: 'PASS', STANDBY: 'WARNING' };
  const services = Object.entries(subsystems).map(([name, value]) => ({
    name,
    status: statusMap[String(value?.status || '').toUpperCase()] || 'WARNING',
    detail: value?.device || value?.framework || value?.storageEngine || value?.channel || `status=${value?.status || 'UNKNOWN'}`,
    uptime: raw.timestamp ? new Date(raw.timestamp).toLocaleTimeString() : '—'
  }));
  const score = services.length ? Math.round((services.filter((s) => s.status === 'PASS').length / services.length) * 100) : 0;
  return { ...raw, score, overall: score === 100 ? 'PASS' : score >= 75 ? 'WARNING' : 'FAIL', services, history: [{ time: new Date(raw.timestamp || Date.now()).toLocaleTimeString(), score }] };
}

export async function getBridgeStatus() {
  try { return { ...(await bridgeFetch('/health')), mock: false }; }
  catch { return { status: 'DOWN', mock: false }; }
}

export async function getOverview() {
  const data = await bridgeFetch('/overview');
  return { ...data, threats: (data.threats || []).map((t) => ({ ...t, level: t.level || t.severity || 'INFO' })) };
}

export async function getActivitySeries(range = '24H') {
  const points = await bridgeFetch(`/overview/activity?range=${encodeURIComponent(range)}`);
  return (points || []).map((p) => ({ ...p, dataIntegrity: p.dataIntegrity ?? p.data ?? 0, modelIntegrity: p.modelIntegrity ?? p.model ?? 0 }));
}
