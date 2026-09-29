// SentinelVision — COCO/YOLO dataset validation service layer.
//
// Mirrors the bridge's dataset-validation gate (task §11: "Validation occurs
// server-side as well as client-side"). Client-side checks are a UX pre-
// filter ONLY — the bridge re-validates every byte server-side and its
// verdict is authoritative.

import { authFetch, BRIDGE_BASE_URL } from './authApi';

// ---------------------------------------------------------------------------
// Shared constants (kept in sync with bridge/src/services/datasetValidationService.js)
// ---------------------------------------------------------------------------
export const ALLOWED_EXTENSIONS = ['.json', '.txt', '.yaml', '.yml', '.jpg', '.jpeg', '.png', '.webp', '.bmp'];

export const BLOCKED_EXTENSIONS = [
  '.gif', '.mp4', '.avi', '.zip',
  '.rar', '.tar', '.py', '.pt', '.pth', '.onnx', '.h5', '.pkl', '.exe'
];

export const KIND_RULES = {
  coco: { label: 'COCO', extensions: ['.json', '.jpg', '.jpeg', '.png', '.webp', '.bmp'], accept: '.json,.jpg,.jpeg,.png,.webp,.bmp' },
  yolo: { label: 'YOLO', extensions: ['.txt', '.yaml', '.yml', '.jpg', '.jpeg', '.png', '.webp', '.bmp'], accept: '.txt,.yaml,.yml,.jpg,.jpeg,.png,.webp,.bmp' }
};

const MAX_FILE_MB = 20;

function extOf(name) {
  const base = String(name || '');
  const dot = base.lastIndexOf('.');
  return dot <= 0 ? '' : base.slice(dot).toLowerCase();
}

// ---------------------------------------------------------------------------
// Client-side gate (fast pre-filter; server repeats everything)
// ---------------------------------------------------------------------------

/** Magic-byte + NUL sniffing so renamed binaries fail fast in the UI too. */
function looksBinary(buf) {
  const n = Math.min(buf.length, 8192);
  if (n === 0) return false;
  let suspicious = 0;
  for (let i = 0; i < n; i++) {
    const c = buf[i];
    if (c === 0) return true;
    if (c < 9 || (c > 13 && c < 32)) suspicious += 1;
  }
  return suspicious / n > 0.05;
}

function detectBinaryMagic(buf) {
  if (!buf || buf.length < 8) return null;
  const eq = (...bytes) => bytes.every((b, i) => buf[i] === b);
  if (eq(0x50, 0x4b, 0x03, 0x04) || eq(0x50, 0x4b, 0x05, 0x06) || eq(0x50, 0x4b, 0x07, 0x08)) return 'zip';
  if (eq(0x7f, 0x45, 0x4c, 0x46)) return 'elf';
  if (eq(0x4d, 0x5a)) return 'pe';
  if (eq(0x80, 0x02)) return 'pickle';
  if (String.fromCharCode(...buf.slice(0, 8)) === '\x89HDF\r\n\x1a\n') return 'hdf5';
  if (eq(0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c)) return '7z';
  if (eq(0x52, 0x61, 0x72, 0x21)) return 'rar';
  if (eq(0xff, 0xd8, 0xff)) return 'jpeg';
  if (eq(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a)) return 'png';
  return null;
}

/**
 * Validate one File object client-side before upload.
 * Returns { ok, reason } — ok=false means "don't even send it".
 */
export async function clientValidateFile(file, kind) {
  const ext = extOf(file.name);
  const rules = KIND_RULES[kind];
  if (!rules) return { ok: false, reason: `Unknown dataset kind '${kind}'` };
  if (BLOCKED_EXTENSIONS.includes(ext)) {
    return { ok: false, reason: `Blocked file extension '${ext}'` };
  }
  if (!rules.extensions.includes(ext)) {
    return { ok: false, reason: `Unsupported extension '${ext}' for ${rules.label} uploads (allowed: ${rules.extensions.join(', ')})` };
  }
  if (file.size > MAX_FILE_MB * 1024 * 1024) {
    return { ok: false, reason: `File exceeds the ${MAX_FILE_MB}MB limit` };
  }
  const buf = new Uint8Array(await file.slice(0, 8192).arrayBuffer());
  const magic = detectBinaryMagic(buf);
  if (magic) {
    return { ok: false, reason: `Content is binary (${magic}); renamed files cannot bypass validation` };
  }
  if (looksBinary(buf)) {
    return { ok: false, reason: 'Content is not decodable text; renamed files cannot bypass validation' };
  }
  return { ok: true };
}

// ---------------------------------------------------------------------------
// Bridge calls
// ---------------------------------------------------------------------------

/**
 * Upload + validate a dataset. Returns the bridge's validation report
 * (status: valid|warning|invalid|rejected). HTTP 201/422/400 map to
 * {ok:true, report}, the report itself carries the verdict.
 */
export async function uploadAndValidateDataset(kind, files, contributorId, datasetId = '') {
  const token = localStorage.getItem('sv-token');
  const fd = new FormData();
  fd.append('contributorId', contributorId || '');
  if (datasetId) fd.append('datasetId', datasetId);
  for (const f of files) fd.append('files', f, f.webkitRelativePath || f.name);
  const res = await fetch(`${BRIDGE_BASE_URL}/api/datasets/validate?kind=${encodeURIComponent(kind)}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: fd
  });
  const body = await res.json().catch(() => null);
  if (!body) {
    throw new Error(`Validation request failed: ${res.status}`);
  }
  if (!res.ok) {
    throw new Error(body.error || `Validation request failed: ${res.status}`);
  }
  return { httpStatus: res.status, report: body.report || body };
}

export function listDatasets(contributorId = 'all') {
  const q = contributorId && contributorId !== 'all'
    ? `?contributorId=${encodeURIComponent(contributorId)}`
    : '';
  return authFetch(`/api/datasets${q}`).then((d) => d.datasets || []);
}

export function listDatasetValidations(limit = 50) {
  return authFetch(`/api/datasets/validations?limit=${limit}`).then((d) => d.validations || []);
}
