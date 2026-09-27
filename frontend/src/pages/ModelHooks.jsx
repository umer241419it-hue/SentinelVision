import { useEffect, useState } from 'react';
import { Activity, Link2, Loader2, RefreshCw, ShieldCheck, Power, Radio } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { listContributors, getContributorModels } from '../services/workflowApi';
import { listModelHooks, registerModelHook, disableModelHook } from '../services/modelHooksApi';
import './ModelHooks.css';

export default function ModelHooks({ notify }) {
  const [contributors, setContributors] = useState([]);
  const [models, setModels] = useState([]);
  const [hooks, setHooks] = useState([]);
  const [contributorId, setContributorId] = useState('');
  const [modelId, setModelId] = useState('');
  const [driftMonitoring, setDriftMonitoring] = useState(true);
  const [inferenceProvenance, setInferenceProvenance] = useState(true);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      const [cs, hs] = await Promise.all([listContributors(), listModelHooks()]);
      setContributors(cs);
      setHooks(hs);
    } catch (err) { notify?.(err.message, 'error'); }
  }

  useEffect(() => { refresh(); }, []);

  useEffect(() => {
    setModelId('');
    if (!contributorId) { setModels([]); return; }
    getContributorModels(contributorId).then(setModels).catch((err) => notify?.(err.message, 'error'));
  }, [contributorId]);

  async function saveHook() {
    if (!contributorId || !modelId) return notify?.('Select the contributor and model.', 'error');
    if (!driftMonitoring && !inferenceProvenance) return notify?.('Select at least one monitoring hook.', 'error');
    setBusy(true);
    try {
      const hook = await registerModelHook({ modelId, contributorId, driftMonitoring, inferenceProvenance });
      await refresh();
      notify?.(`Hook ${hook.hookId} registered for ${hook.modelName}.`, 'success');
    } catch (err) { notify?.(err.message, 'error'); }
    finally { setBusy(false); }
  }

  async function disable(hookId) {
    try { await disableModelHook(hookId); await refresh(); notify?.('Model hook disabled.', 'success'); }
    catch (err) { notify?.(err.message, 'error'); }
  }

  return (
    <div className="anim-fade mh-grid">
      <GlassCard className="mh-config">
        <div className="card-header">
          <h3>01 · ATTACH MODEL HOOKS</h3>
          <button className="hud-btn icon-only" onClick={refresh} title="Refresh"><RefreshCw size={13} /></button>
        </div>
        <div className="mh-note"><ShieldCheck size={15}/><span>Register the controls that must travel with this model during downstream monitoring and inference.</span></div>

        <label className="mh-label">CONTRIBUTOR / VENDOR *</label>
        <select className="mh-select" value={contributorId} onChange={(e)=>setContributorId(e.target.value)} disabled={busy}>
          <option value="">SELECT CONTRIBUTOR / VENDOR</option>
          {contributors.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}
        </select>

        <label className="mh-label">MODEL *</label>
        <select className="mh-select" value={modelId} onChange={(e)=>setModelId(e.target.value)} disabled={busy || !contributorId}>
          <option value="">SELECT MODEL</option>
          {models.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}
        </select>

        <div className="mh-hooks">
          <label className={`mh-hook ${driftMonitoring ? 'active' : ''}`}>
            <input type="checkbox" checked={driftMonitoring} onChange={(e)=>setDriftMonitoring(e.target.checked)} />
            <Activity size={17}/><span><b>DRIFT MONITORING</b><small>Register the model for distribution-shift monitoring against reference/live windows.</small></span>
          </label>
          <label className={`mh-hook ${inferenceProvenance ? 'active' : ''}`}>
            <input type="checkbox" checked={inferenceProvenance} onChange={(e)=>setInferenceProvenance(e.target.checked)} />
            <Link2 size={17}/><span><b>INFERENCE PROVENANCE</b><small>Register cryptographic inference sealing for input/model/config/output provenance.</small></span>
          </label>
        </div>

        <button className="auth-submit mh-action" onClick={saveHook} disabled={busy || !modelId}>
          {busy ? <><Loader2 size={14} className="spin"/> REGISTERING…</> : <><Radio size={14}/> ATTACH HOOKS</>}
        </button>
      </GlassCard>

      <GlassCard className="mh-status">
        <div className="card-header"><h3>02 · ACTIVE MODEL HOOKS</h3></div>
        {hooks.length === 0 && <div className="mh-empty">NO MODEL HOOKS REGISTERED</div>}
        <div className="mh-list">
          {hooks.map(h=>(
            <div className="mh-row" key={h.hookId}>
              <div className="mh-row-main"><strong>{h.modelName}</strong><span>{h.contributorName} · {h.hookId}</span></div>
              <div className="mh-badges">
                {h.status === 'ACTIVE' && h.driftMonitoring && <span className="mh-badge drift"><Activity size={11}/> DRIFT</span>}
                {h.status === 'ACTIVE' && h.inferenceProvenance && <span className="mh-badge prov"><Link2 size={11}/> PROVENANCE</span>}
                <span className={`mh-status-pill ${h.status === 'ACTIVE' ? 'on' : 'off'}`}>{h.status}</span>
              </div>
              {h.status === 'ACTIVE' && <button className="hud-btn mh-disable" onClick={()=>disable(h.hookId)} title="Disable"><Power size={13}/> DISABLE</button>}
            </div>
          ))}
        </div>
      </GlassCard>

      <GlassCard className="mh-info">
        <div className="card-header"><h3>03 · INTEGRATION CONTRACT</h3></div>
        <div className="mh-contract">
          <div><Activity size={16}/><span><b>Drift</b> — hook registration associates the selected model with the existing drift-monitor reference/live-window pipeline.</span></div>
          <div><Link2 size={16}/><span><b>Inference</b> — hook registration marks the model for the existing <code>sealed_predict()</code> provenance wrapper.</span></div>
          <div><ShieldCheck size={16}/><span><b>Integrity</b> — contributor attribution and model identity remain attached to the hook record.</span></div>
        </div>
      </GlassCard>
    </div>
  );
}
