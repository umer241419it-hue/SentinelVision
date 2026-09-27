import { authFetch } from './authApi';

export function listModels(contributorId = 'all') {
  const q = contributorId && contributorId !== 'all'
    ? `?contributorId=${encodeURIComponent(contributorId)}`
    : '';
  return authFetch(`/api/models${q}`).then((d) => d.models || []);
}

export function validateModel(modelId) {
  return authFetch(`/api/models/validate/${encodeURIComponent(modelId)}`, {
    method: 'POST'
  }).then((d) => d.report);
}

export function listModelValidations(limit = 50) {
  return authFetch(`/api/models/validations?limit=${limit}`).then((d) => d.validations || []);
}
