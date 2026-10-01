import { useEffect, useState } from 'react';
import { BadgeCheck, FileCheck2, Link2, Loader2, RefreshCw, ShieldCheck, XCircle } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { listContributors, getContributorModels } from '../services/workflowApi';
import { runInferenceProvenance, getInferenceRun, listInferenceEvidence } from '../services/inferenceProvenanceApi';
import './InferenceProvenance.css';

export default function InferenceProvenance({ notify }) {
  const [contributors, setContributors] = useState([]);
  const [models, setModels] = useState([]);
  const [records, setRecords] = useState([]);
  const [contributorId, setContributorId] = useState('');
  const [modelId, setModelId] = useState('');
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      const [cs, rs] = await Promise.all([listContributors(), listInferenceEvidence()]);
      setContributors(cs);
      setRecords(rs);
    } catch (err) {
      notify?.(err.message, 'error');
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    setModelId('');
    setRun(null);
    if (!contributorId) {
      setModels([]);
      return;
    }
    getContributorModels(contributorId)
      .then(setModels)
      .catch((err) => notify?.(err.message, 'error'));
  }, [contributorId]);

  async function execute() {
    if (!contributorId || !modelId) {
      notify?.('Select the contributor and uploaded model.', 'error');
      return;
    }
    setBusy(true);
    setRun(null);
    try {
      const started = await runInferenceProvenance({ contributorId, modelId });
      let current = started?.test || started;
      const normalizeRun = (value) => ({
        ...value,
        runId: value?.runId || value?.run_id || value?.testId || value?.id || '',
        status: String(value?.status || 'RUNNING').toUpperCase(),
        checks: Array.isArray(value?.checks) ? value.checks : []
      });
      current = normalizeRun(current);
      setRun(current);

      const terminal = new Set(['COMPLETED', 'FAILED', 'ERROR', 'CANCELLED']);
      for (let i = 0; i < 180 && !terminal.has(current.status); i += 1) {
        if (!current.runId) break;
        await new Promise((resolve) => setTimeout(resolve, 1000));
        current = normalizeRun(await getInferenceRun(current.runId));
        setRun(current);
      }

      await refresh();
      if (current.status === 'COMPLETED') {
        notify?.('Inference provenance verification completed.', 'success');
      } else {
        notify?.('Inference provenance verification did not complete successfully.', 'error');
      }
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="anim-fade ip-grid">
      <GlassCard className="ip-config">
        <div className="card-header">
          <h3>01 · INFERENCE PROVENANCE</h3><span className="text-muted" style={{fontSize: 10}}>LIVE LOCAL VERIFICATION</span>
          <button className="hud-btn icon-only" onClick={refresh} title="Refresh"><RefreshCw size={13} /></button>
        </div>

        <div className="ip-note">
          <ShieldCheck size={16} />
          <span>Verify cryptographic binding between inference input, model digest, execution configuration and output using the existing SentinelVision provenance verifier.</span>
        </div>

        <label className="ip-label">CONTRIBUTOR / VENDOR *</label>
        <select className="ip-select" value={contributorId} onChange={(e) => setContributorId(e.target.value)} disabled={busy}>
          <option value="">SELECT CONTRIBUTOR / VENDOR</option>
          {contributors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>

        <label className="ip-label">UPLOADED MODEL *</label>
        <select className="ip-select" value={modelId} onChange={(e) => setModelId(e.target.value)} disabled={busy || !contributorId}>
          <option value="">{contributorId ? 'SELECT UPLOADED MODEL' : 'SELECT CONTRIBUTOR FIRST'}</option>
          {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>

        <div className="ip-contract">
          <div><Link2 size={15} /><span><b>INPUT BINDING</b><small>Input hash is bound into the sealed inference record.</small></span></div>
          <div><FileCheck2 size={15} /><span><b>MODEL BINDING</b><small>Model weights digest is recorded with the inference.</small></span></div>
          <div><BadgeCheck size={15} /><span><b>OUTPUT INTEGRITY</b><small>Output summary, timestamp and nonce are cryptographically sealed.</small></span></div>
        </div>

        <button className="auth-submit ip-action" onClick={execute} disabled={busy || !modelId}>
          {busy ? <><Loader2 size={14} className="spin" /> VERIFYING…</> : <><ShieldCheck size={14} /> RUN PROVENANCE VERIFICATION</>}
        </button>
      </GlassCard>

      <GlassCard className="ip-result">
        <div className="card-header"><h3>02 · VERIFICATION STATUS</h3></div>
        {!run ? (
          <div className="ip-empty">SELECT A MODEL AND RUN VERIFICATION</div>
        ) : (
          <div className="ip-result-body">
            <div className="ip-status-row">
              <span className={String(run.status).toUpperCase() === 'COMPLETED' ? 'ip-status pass' : 'ip-status'}>{run.status || 'RUNNING'}</span>
              <span className="ip-run-id">{run.runId || run.testId || run.id}</span>
            </div>
            <div className="ip-checks">
              {(Array.isArray(run.checks) ? run.checks : []).map((check, index) => (
                <div className="ip-check" key={check.name || index}>
                  {String(check.status).toUpperCase() === 'PASS' ? <BadgeCheck size={15} /> : <XCircle size={15} />}
                  <span><b>{check.name}</b><small>{check.message || check.detail || check.status}</small></span>
                </div>
              ))}
            </div>
          </div>
        )}
      </GlassCard>

      <GlassCard className="ip-records">
        <div className="card-header"><h3>03 · SEALED EVIDENCE RECORDS</h3><span className="ip-count">{records.length} RECORDS</span></div>
        {records.length === 0 ? (
          <div className="ip-empty">NO INFERENCE PROVENANCE RECORDS FOUND</div>
        ) : (
          <div className="ip-record-list">
            {records.slice(0, 12).map((r) => (
              <div className="ip-record" key={r.evidenceId || r.id}>
                <div><strong>{r.sealID || r.assetID || r.evidenceId || 'SEAL'}</strong><span>{r.timestamp || '—'}</span></div>
                <div><span>MODEL: {r.modelAssetId || r.modelId || '—'}</span><span className={r.signatureStatus === 'TAMPERED' ? 'bad' : 'good'}>{r.signatureStatus || 'SEALED'}</span></div>
                <code>{r.evidenceHash || r.contentHash || '—'}</code>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
