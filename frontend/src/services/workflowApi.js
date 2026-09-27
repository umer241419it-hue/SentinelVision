// SentinelVision — role workflow service layer.
//
// Wrappers over the bridge's role-scoped endpoints.
// All calls require the JWT persisted by authApi; the bridge enforces
// RBAC server-side (requireAuth + requireRole) — the UI only hides modules.
// Existing algorithms are invoked via the bridge orchestration layer; this
// file only packages requests for them (task spec §1: no algorithm changes).

import { authFetch, BRIDGE_BASE_URL } from './authApi';

// ---------------------------------------------------------------------------
// Contributor / Vendor Management
// ---------------------------------------------------------------------------
export function listContributors() {
  return authFetch('/api/contributors').then((d) => d.contributors || []);
}

export function getContributor(id) {
  return authFetch(`/api/contributors/${encodeURIComponent(id)}`).then((d) => d.contributor);
}

export function createContributor(data) {
  return authFetch('/api/contributors', {
    method: 'POST',
    body: JSON.stringify(data)
  });
}

export function updateContributor(id, data) {
  return authFetch(`/api/contributors/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(data)
  });
}

export function getContributorDatasets(id) {
  return authFetch(`/api/contributors/${encodeURIComponent(id)}/datasets`).then((d) => d.datasets || []);
}

export function getContributorModels(id) {
  return authFetch(`/api/contributors/${encodeURIComponent(id)}/models`).then((d) =>
    (d.models || []).map((m) => ({
      ...m,
      id: m.id || m.uploadId,
      name: m.name || m.originalName || m.filename,
      sha256: m.sha256,
      framework: m.framework || 'Unknown',
      contributorId: m.contributorId || id,
      contributorName: m.contributorName || 'Unknown'
    }))
  );
}

// ---------------------------------------------------------------------------
// Analyst — uploads (multipart single & multiple)
// ---------------------------------------------------------------------------
export async function uploadAsset(kind, file, contributorId = '') {
  if (!contributorId || contributorId === 'unassigned') {
    throw new Error(`Select the contributor who provided this ${kind}.`);
  }
  const result = await uploadMultipleAssets(kind, [file], contributorId);
  const first = result?.results?.[0];
  if (!first || !['SUCCESS', 'EXISTS'].includes(first.status)) {
    throw new Error(first?.error || `Upload failed for ${file?.name || kind}`);
  }
  return first;
}

export async function uploadMultipleAssets(kind, files, contributorId = 'unassigned') {
  const token = localStorage.getItem('sv-token');
  const endpoint = kind === 'model' ? '/api/models/upload' : '/api/datasets/upload';
  const fd = new FormData();
  fd.append('contributorId', contributorId);
  for (const f of files) {
    fd.append('files', f);
  }
  const res = await fetch(`${BRIDGE_BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: fd
  });
  const body = await res.json().catch(() => null);
  if (!res.ok && !body?.results) {
    const err = new Error(body?.details || body?.error || `Upload failed: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return body;
}

export function listUploads(contributorId) {
  const q = contributorId && contributorId !== 'all' ? `?contributorId=${encodeURIComponent(contributorId)}` : '';
  return authFetch(`/api/uploads${q}`).then((d) => d.uploads || []);
}

// ---------------------------------------------------------------------------
// Analyst — trustworthiness / training / tests / batches
// ---------------------------------------------------------------------------
export function runTrustCheck({ datasetId, modelId, labelsPath, contributorId, contributorName, batchId }) {
  return authFetch('/api/trust/run', {
    method: 'POST',
    body: JSON.stringify({ datasetId, modelId, labelsPath, contributorId, contributorName, batchId })
  });
}

export function runTrustBatch({ contributorId, pairs, configId, testType }) {
  return authFetch('/api/trust/batch', {
    method: 'POST',
    body: JSON.stringify({ contributorId, pairs, configId, testType })
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
