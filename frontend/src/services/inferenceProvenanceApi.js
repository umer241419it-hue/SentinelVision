import { authFetch } from './authApi';

export function runInferenceProvenance({ contributorId, modelId }) {
  return authFetch('/api/inference-provenance/run', {
    method: 'POST',
    body: JSON.stringify({ contributorId, modelId })
  });
}

export function getInferenceRun(runId) {
  return authFetch(`/api/runs/${encodeURIComponent(runId)}`);
}

export function listInferenceEvidence() {
  return authFetch('/api/inference-provenance/records').then((d) => d.records || []);
}
