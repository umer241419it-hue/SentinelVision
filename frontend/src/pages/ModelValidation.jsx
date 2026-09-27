import { useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, XCircle, Loader2, RefreshCw, ShieldCheck, ScanLine } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { StatusBadge } from '../components/Badges';
import DataTable from '../components/DataTable';
import { listContributors } from '../services/workflowApi';
import { listModels, validateModel, listModelValidations } from '../services/modelValidationApi';
import { uploadMultipleAssets } from '../services/workflowApi';
import './ModelValidation.css';

function fmtBytes(n) {
  if (!Number.isFinite(Number(n))) return '—';
  const x = Number(n);
  if (x < 1024) return `${x} B`;
  if (x < 1024 * 1024) return `${(x / 1024).toFixed(1)} KB`;
  return `${(x / (1024 * 1024)).toFixed(1)} MB`;
}

function fmtTime(v) {
  try { return new Date(v).toLocaleString(); } catch { return v || '—'; }
}

export default function ModelValidation({ notify }) {
  const [contributors, setContributors] = useState([]);
  const [models, setModels] = useState([]);
  const [history, setHistory] = useState([]);
  const [contributorId, setContributorId] = useState('');
  const [modelId, setModelId] = useState('');
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const uploadRef = useRef(null);
  const [uploading, setUploading] = useState(false);

  async function load() {
    try {
      const [cs, hs] = await Promise.all([listContributors(), listModelValidations()]);
      setContributors(cs);
      setHistory(hs);
    } catch (err) {
      notify?.(err.message, 'error');
    }
  }

  useEffect(() => { load(); }, []);

  useEffect(() => {
    setModelId('');
    if (!contributorId) {
      setModels([]);
      return;
    }
    listModels(contributorId).then(setModels).catch((err) => notify?.(err.message, 'error'));
  }, [contributorId]);

  const selectedModel = useMemo(() => models.find((m) => m.id === modelId), [models, modelId]);

  async function uploadModel(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!contributorId) {
      notify?.('Select the contributor / vendor before uploading the model.', 'error');
      return;
    }
    setUploading(true);
    try {
      const result = await uploadMultipleAssets('model', [file], contributorId);
      const first = result?.results?.[0];
      if (!first || !['SUCCESS', 'EXISTS'].includes(first.status)) {
        throw new Error(first?.error || 'Model upload failed');
      }
      const nextModels = await listModels(contributorId);
      setModels(nextModels);
      setModelId(first.uploadId);
      notify?.(`Model ${file.name} uploaded and registered. Run VALIDATE MODEL to perform a fresh check.`, 'success');
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setUploading(false);
    }
  }

  async function runValidation() {
    if (!contributorId || !modelId) {
      notify?.('Select both the contributor and model before validation.', 'error');
      return;
    }
    setBusy(true);
    setReport(null);
    try {
      const r = await validateModel(modelId);
      setReport(r);
      await load();
      notify?.(`Model validation: ${r.status}`, r.status === 'VALID' ? 'success' : 'error');
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="anim-fade mv-grid">
      <GlassCard className="mv-select">
        <div className="card-header">
          <h3>01 · SELECT MODEL</h3>
          <button className="hud-btn icon-only" onClick={load} title="Refresh"><RefreshCw size={13} /></button>
        </div>

        <label className="mv-label">CONTRIBUTOR / VENDOR *</label>
        <select className="mv-selectbox" value={contributorId} onChange={(e) => setContributorId(e.target.value)} disabled={busy}>
          <option value="">SELECT CONTRIBUTOR / VENDOR</option>
          {contributors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <div className="mv-help">Only models attributed to the selected provider are shown.</div>

        <label className="mv-label">MODEL *</label>
        <select className="mv-selectbox" value={modelId} onChange={(e) => setModelId(e.target.value)} disabled={busy || uploading || !contributorId}>
          <option value="">SELECT REGISTERED MODEL</option>
          {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>

        <div className="mv-upload-row">
          <button type="button" className="hud-btn mv-upload-btn" onClick={() => uploadRef.current?.click()} disabled={busy || uploading || !contributorId}>
            {uploading ? <><Loader2 size={13} className="spin" /> UPLOADING…</> : <><ScanLine size={13} /> UPLOAD MODEL FILE</>}
          </button>
          <span>Upload a real .pt, .pth, .onnx, .h5, .keras, .tflite, .ckpt or .bin file.</span>
          <input
            ref={uploadRef}
            type="file"
            hidden
            accept=".pt,.pth,.onnx,.bin,.h5,.keras,.tflite,.ckpt,.tar,.gz"
            onChange={uploadModel}
          />
        </div>

        {selectedModel && (
          <div className="mv-asset">
            <div><span>MODEL</span><b>{selectedModel.name}</b></div>
            <div><span>PROVIDER</span><b>{selectedModel.contributorName}</b></div>
            <div><span>FORMAT</span><b>{selectedModel.framework || 'Unknown'}</b></div>
            <div><span>SHA-256</span><b className="mono">{selectedModel.sha256?.slice(0, 16)}…</b></div>
          </div>
        )}

        <button className="auth-submit mv-action" disabled={busy || uploading || !modelId} onClick={runValidation}>
          {busy ? <><Loader2 size={14} className="spin" /> VALIDATING…</> : <><ShieldCheck size={14} /> VALIDATE MODEL</>}
        </button>
      </GlassCard>

      <GlassCard className="mv-report">
        <div className="card-header"><h3>02 · MODEL VALIDATION RESULT</h3>{report && <StatusBadge status={report.status === 'VALID' ? 'PASS' : 'FAIL'} />}</div>
        {!report && !busy && <div className="mv-empty">SELECT A REGISTERED MODEL — VERIFY FILE PRESENCE, FORMAT, HASH AND CONTRIBUTOR ATTRIBUTION</div>}
        {busy && <div className="mv-progress"><Loader2 size={15} className="spin" /> CHECKING MODEL REGISTRY AND FILE INTEGRITY…</div>}
        {report && !busy && (
          <div className="mv-body">
            <div className={`mv-verdict ${report.status === 'VALID' ? 'ok' : 'bad'}`}>
              {report.status === 'VALID' ? <CheckCircle2 size={20} /> : <XCircle size={20} />}
              <div><strong>{report.status}</strong><span>{report.modelName}</span></div>
            </div>
            <div className="mv-stats">
              <div><span>CONTRIBUTOR</span><b>{report.contributorName}</b></div>
              <div><span>FRAMEWORK</span><b>{report.framework}</b></div>
              <div><span>SIZE</span><b>{fmtBytes(report.sizeBytes)}</b></div>
              <div><span>EXTENSION</span><b>{report.extension}</b></div>
              <div><span>REGISTERED HASH</span><b className="mono">{report.registeredSha256?.slice(0, 18)}…</b></div>
              <div><span>COMPUTED HASH</span><b className="mono">{report.computedSha256?.slice(0, 18)}…</b></div>
            </div>
            {report.errors?.length > 0 && <div className="mv-errors">{report.errors.map((e, i) => <div key={i}><XCircle size={12} />{e}</div>)}</div>}
            {report.warnings?.length > 0 && <div className="mv-errors warn">{report.warnings.map((e, i) => <div key={i}><ScanLine size={12} />{e}</div>)}</div>}
            {report.engine && (
              <div className={`mv-engine ${report.engine.status === 'COMPLETED' ? 'ok' : 'bad'}`}>
                <div className="mv-engine-title"><ScanLine size={13} /> MODEL INTEGRITY ASSURANCE (DEMO): {report.engine.status}</div>
                <div className="mono mv-engine-meta">ENGINE: {report.engine.engine || 'SentinelVision Model Integrity Assurance (Demo)'} · MODEL ID: {report.engine.modelId}</div>
                {report.engine.output && <div className="mono mv-engine-meta">VERDICT: {report.engine.output.verdict || '—'} · FINDINGS: {(report.engine.output.findings || []).length}</div>}
                {report.engine.stderr && report.engine.status !== 'COMPLETED' && <pre className="mv-engine-log">{report.engine.stderr.slice(-3000)}</pre>}
              </div>
            )}
          </div>
        )}
      </GlassCard>

      <GlassCard className="mv-history">
        <div className="card-header"><h3>03 · VALIDATION HISTORY</h3></div>
        <DataTable
          columns={[
            { key: 'modelName', label: 'Model' },
            { key: 'contributorName', label: 'Contributor' },
            { key: 'framework', label: 'Framework' },
            { key: 'status', label: 'Verdict', render: (r) => <StatusBadge status={r.status === 'VALID' ? 'PASS' : 'FAIL'} /> },
            { key: 'computedSha256', label: 'SHA-256', render: (r) => <span className="mono">{r.computedSha256?.slice(0, 12)}…</span> },
            { key: 'validatedAt', label: 'Time', render: (r) => fmtTime(r.validatedAt) }
          ]}
          rows={history}
          emptyMessage="NO MODEL VALIDATIONS YET"
        />
      </GlassCard>
    </div>
  );
}
