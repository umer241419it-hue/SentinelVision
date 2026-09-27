// SentinelVision — role workflow service layer.
//
// Wrappers over the bridge's role-scoped endpoints.
// All calls require the JWT persisted by authApi; the bridge enforces
// RBAC server-side (requireAuth + requireRole) — the UI only hides modules.
// Existing algorithms are invoked via the bridge orchestration layer; this
// file only packages requests for them (task spec §1: no algorithm changes).

import { authFetch, BRIDGE_BASE_URL } from './authApi';

// ---------------------------------------------------------------------------
// Analyst — uploads (multipart)
// ---------------------------------------------------------------------------
export async function uploadAsset(kind, file) {
  const token = localStorage.getItem('sv-token');
  const res = await fetch(`${BRIDGE_BASE_URL}/api/uploads/${kind}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: (() => {
      const fd = new FormData();
      fd.append('file', file);
      return fd;
    })()
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(body?.details || body?.error || `Upload failed: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return body.upload;
}

export function listUploads() {
  return authFetch('/api/uploads').then((d) => d.uploads || []);
}

// ---------------------------------------------------------------------------
// Analyst — trustworthiness / training / tests
// ---------------------------------------------------------------------------
export function runTrustCheck({ datasetId, modelId, labelsPath }) {
  return authFetch('/api/trust/run', {
    method: 'POST',
    body: JSON.stringify({ datasetId, modelId, labelsPath })
  });
}

export function startTraining({ datasetId, labelsPath, params }) {
  return authFetch('/api/trust/train', {
    method: 'POST',
    body: JSON.stringify({ datasetId, labelsPath, params })
  });
}

export function listMyTests() {
  return authFetch('/api/trust/tests').then((d) => d.tests || []);
}

export function getTestDetail(testId) {
  return authFetch(`/api/trust/tests/${encodeURIComponent(testId)}`).then((d) => d.test);
}

export function submitForQuarantine(testId, reason) {
  return authFetch(`/api/trust/tests/${encodeURIComponent(testId)}/quarantine`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  });
}

// ---------------------------------------------------------------------------
// Shared — module results (analyst sees own, auditor sees all)
// ---------------------------------------------------------------------------
export function getOverviewKpis() {
  return authFetch('/api/overview');
}

export function listFindings() {
  return authFetch('/api/findings').then((d) => d.findings || []);
}

export function listAuditLogs() {
  return authFetch('/api/auditor/logs').then((d) => d.logs || []);
}

// ---------------------------------------------------------------------------
// Auditor — quarantine review / ledger / sessions / users / reports
// ---------------------------------------------------------------------------
export function listQuarantine(status) {
  const q = status ? `?status=${encodeURIComponent(status)}` : '';
  return authFetch(`/api/auditor/quarantine${q}`).then((d) => d.quarantine || []);
}

export function getQuarantineDetail(id) {
  return authFetch(`/api/auditor/quarantine/${encodeURIComponent(id)}`);
}

export function decideQuarantine(id, decision, notes) {
  return authFetch(`/api/auditor/quarantine/${encodeURIComponent(id)}/decision`, {
    method: 'POST',
    body: JSON.stringify({ decision, notes })
  });
}

export function releaseQuarantine(id) {
  return authFetch(`/api/auditor/quarantine/${encodeURIComponent(id)}/release`, {
    method: 'POST'
  });
}

export function commitQuarantineToLedger(id) {
  return authFetch(`/api/auditor/quarantine/${encodeURIComponent(id)}/commit`, {
    method: 'POST'
  });
}

export function listLedgerTransactions() {
  return authFetch('/api/auditor/ledger/transactions').then((d) => d.transactions || []);
}

export function listSessions() {
  return authFetch('/api/auditor/sessions').then((d) => d.sessions || []);
}

export function listUsers() {
  return authFetch('/api/auditor/users').then((d) => d.users || []);
}

export function setUserStatus(userId, status) {
  return authFetch(`/api/auditor/users/${encodeURIComponent(userId)}/status`, {
    method: 'POST',
    body: JSON.stringify({ status })
  });
}

export function approvePendingUser(userId) {
  return authFetch(`/api/auditor/users/pending/${encodeURIComponent(userId)}/approve`, {
    method: 'POST'
  });
}

export function listReports() {
  return authFetch('/api/auditor/reports').then((d) => d.reports || []);
}

export async function downloadGovernanceReport(periodDays = 30) {
  const token = localStorage.getItem('sv-token');
  const res = await fetch(
    `${BRIDGE_BASE_URL}/api/auditor/reports/governance.pdf?periodDays=${periodDays}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  if (!res.ok) throw new Error(`Report download failed: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `governance-report-${new Date().toISOString().slice(0, 10)}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}
