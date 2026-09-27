import { authFetch } from './authApi';

export function listModelHooks() {
  return authFetch('/api/model-hooks').then((d) => d.hooks || []);
}

export function registerModelHook(data) {
  return authFetch('/api/model-hooks', {
    method: 'POST',
    body: JSON.stringify(data)
  }).then((d) => d.hook);
}

export function disableModelHook(hookId) {
  return authFetch(`/api/model-hooks/${encodeURIComponent(hookId)}/disable`, {
    method: 'POST'
  }).then((d) => d.hook);
}
