import { useCallback, useEffect, useRef, useState } from 'react';
import {
  UploadCloud, PlayCircle, FlaskConical, Loader2, RefreshCw, FileJson, FileText, Cpu,
  CheckCircle2, XCircle, AlertTriangle, ShieldAlert
} from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { StatusBadge } from '../components/Badges';
import {
  uploadAsset, listUploads, runTrustCheck, listMyTests, submitForQuarantine
} from '../services/workflowApi';
import './AnalystWorkspace.css';

const CHECK_ORDER = ['DATA_INTEGRITY', 'DATA_DRIFT', 'MODEL_INTEGRITY', 'INFERENCE_SEAL'];
const CHECK_LABELS = {
  DATA_INTEGRITY: 'DATA INTEGRITY',
  DATA_DRIFT: 'DATA DRIFT',
  MODEL_INTEGRITY: 'MODEL INTEGRITY',
  INFERENCE_SEAL: 'INFERENCE SEAL'
};

// Dataset uploads are COCO/YOLO-only (task §1/§2):
// COCO → .json · YOLO → .txt/.yaml/.yml. Images, zips and model binaries
// are rejected by the client accept lists AND server-side by the gate.
const DATASET_LANES = [
  { kind: 'dataset-coco', label: 'COCO', hint: '.json annotations', accept: '.json', icon: FileJson },
  { kind: 'dataset-yolo', label: 'YOLO', hint: '.txt · .yaml · .yml', accept: '.txt,.yaml,.yml', icon: FileText }
];

function checkIcon(status) {
  if (status === 'PASS') return <CheckCircle2 size={13} />;
  if (status === 'FAIL') return <XCircle size={13} />;
  if (status === 'WARNING') return <AlertTriangle size={13} />;
  return <Loader2 size={13} className="spin" />;
}

/**
 * AnalystWorkspace — UPLOAD → VALIDATE → TRUSTWORTHINESS → PASS / QUARANTINE.
 * Orchestrates the EXISTING SentinelVision algorithms through the bridge;
 * no algorithm logic lives in the UI (task spec §1, §13–§18).
 */
export default function AnalystWorkspace({ notify }) {
  const [uploads, setUploads] = useState([]);
  const [tests, setTests] = useState([]);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [quarantining, setQuarantining] = useState(null); // testId
  const [reason, setReason] = useState('');
  const [lastTest, setLastTest] = useState(null);
  const datasetCocoRef = useRef(null);
  const datasetYoloRef = useRef(null);
  const modelRef = useRef(null);
  const datasetRef = useRef({ datasetId: '' });

  const refresh = useCallback(async () => {
    try {
      const [u, t] = await Promise.all([listUploads(), listMyTests()]);
      setUploads(u);
      setTests(t);
    } catch (err) {
      notify?.(err.message, 'error');
    }
  }, [notify]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function doUpload(kind, file) {
    if (!file) return;
    setBusy(true);
    try {
      const up = await uploadAsset(kind, file);
      notify?.(`${kind.toUpperCase()} uploaded · ${up.uploadId} · sha256 ${up.sha256?.slice(0, 12) || '…'}`, 'success');
      await refresh();
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setBusy(false);
      if (datasetCocoRef.current) datasetCocoRef.current.value = '';
      if (datasetYoloRef.current) datasetYoloRef.current.value = '';
      if (modelRef.current) modelRef.current.value = '';
    }
  }

  const datasets = uploads.filter((u) => u.kind === 'dataset');
  const models = uploads.filter((u) => u.kind === 'model');

  async function runTrust() {
    const ds = datasetRef.current?.datasetId;
    if (!ds) {
      notify?.('Select a dataset first.', 'error');
      return;
    }
    setRunning(true);
    setLastTest(null);
    try {
      const model = modelRef.current?.datasetId || null;
      const data = await runTrustCheck({ datasetId: ds, modelId: model });
      setLastTest(data.test);
      notify?.(`Trust check complete · ${data.test.testId} → ${data.test.trustStatus}`, data.test.trustStatus === 'PASS' ? 'success' : 'warning');
      await refresh();
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setRunning(false);
    }
  }

  async function quarantine(testId) {
    setQuarantining(testId);
    try {
      await submitForQuarantine(testId, reason || null);
      notify?.(`Test ${testId} submitted for quarantine review.`, 'success');
      setReason('');
      await refresh();
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setQuarantining(null);
    }
  }

  return (
    <div className="anim-fade aw-grid">
      {/* ---- Step 1: UPLOAD ---- */}
      <GlassCard className="aw-upload">
        <div className="card-header">
          <h3>01 · UPLOAD ASSETS</h3>
          <span className="hdr-meta">COCO (.json) · YOLO (.txt/.yaml/.yml) · MODEL (.pt/.pth/.onnx)</span>
        </div>
        <div className="aw-drop-row">
          {DATASET_LANES.map(({ kind, label, hint, accept, icon: Icon }) => (
            <button
              key={kind}
              className="aw-drop"
              disabled={busy}
              onClick={() => (kind === 'dataset-coco' ? datasetCocoRef : datasetYoloRef).current?.click()}
            >
              <Icon size={18} />
              <strong>{label}</strong>
              <span>{hint}</span>
            </button>
          ))}
          <button className="aw-drop" disabled={busy} onClick={() => modelRef.current?.click()}>
            <Cpu size={18} />
            <strong>MODEL</strong>
            <span>.pt · .pth · .onnx</span>
          </button>
        </div>
        <input
          ref={datasetCocoRef} type="file" accept=".json" hidden
          onChange={(e) => doUpload('dataset', e.target.files?.[0])}
        />
        <input
          ref={datasetYoloRef} type="file" accept=".txt,.yaml,.yml" hidden
          onChange={(e) => doUpload('dataset', e.target.files?.[0])}
        />
        <input
          ref={modelRef} type="file" accept=".pt,.pth,.onnx" hidden
          onChange={(e) => doUpload('model', e.target.files?.[0])}
        />
        <div className="aw-uplist">
          {uploads.slice(0, 6).map((u) => (
            <div key={u.uploadId} className="aw-uprow">
              <span className={`aw-kind ${u.kind}`}>{u.kind === 'model' ? 'MDL' : 'DS'}</span>
              <span className="aw-upname" title={u.originalName}>{u.originalName}</span>
              <span className="mono aw-upid">{u.uploadId}</span>
              <StatusBadge status="STORED" />
            </div>
          ))}
          {uploads.length === 0 && <div className="aw-empty">NO ASSETS UPLOADED YET</div>}
        </div>
      </GlassCard>

      {/* ---- Step 2: TRUSTWORTHINESS ---- */}
      <GlassCard className="aw-trust">
        <div className="card-header">
          <h3>02 · RUN TRUSTWORTHINESS CHECK</h3>
          <span className="hdr-meta">ORCHESTRATES EXISTING MODULES — UNMODIFIED</span>
        </div>
        <div className="aw-pick-row">
          <label className="aw-pick">
            <span>DATASET</span>
            <select
              defaultValue=""
              onChange={(e) => { if (datasetRef.current) datasetRef.current.datasetId = e.target.value; }}
            >
              <option value="">— select dataset —</option>
              {datasets.map((d) => (
                <option key={d.uploadId} value={d.uploadId}>{d.uploadId} · {d.originalName}</option>
              ))}
            </select>
          </label>
          <label className="aw-pick">
            <span>MODEL (OPTIONAL)</span>
            <select
              defaultValue=""
              onChange={(e) => { if (modelRef.current) modelRef.current.datasetId = e.target.value; }}
            >
              <option value="">— none —</option>
              {models.map((m) => (
                <option key={m.uploadId} value={m.uploadId}>{m.uploadId} · {m.originalName}</option>
              ))}
            </select>
          </label>
          <button className="auth-submit aw-run" onClick={runTrust} disabled={running}>
            {running ? <><Loader2 size={14} className="spin" /> RUNNING…</> : <><PlayCircle size={14} /> RUN CHECK</>}
          </button>
        </div>

        {running && (
          <div className="aw-progress mono">
            <span className="auth-boot-dot" /> INVOKING DATA INTEGRITY · DRIFT · MODEL INTEGRITY · INFERENCE SEAL…
          </div>
        )}

        {lastTest && !running && (
          <div className="aw-result">
            <div className={`aw-verdict v-${(lastTest.trustStatus || '').toLowerCase()}`}>
              <span className="aw-verdict-label">TRUSTWORTHINESS STATUS</span>
              <span className="aw-verdict-val">{lastTest.trustStatus}</span>
              <span className="mono aw-verdict-id">{lastTest.testId}</span>
            </div>
            <div className="aw-checks">
              {CHECK_ORDER.map((k) => {
                const c = lastTest.checks?.[k];
                if (!c) return null;
                return (
                  <div key={k} className={`aw-check st-${(c.status || '').toLowerCase()}`}>
                    {checkIcon(c.status)}
                    <span className="aw-check-name">{CHECK_LABELS[k]}</span>
                    <span className="aw-check-status">{c.status}</span>
                  </div>
                );
              })}
            </div>
            {lastTest.trustStatus !== 'PASS' && (
              <button
                className="hud-btn aw-quar"
                disabled={quarantining === lastTest.testId}
                onClick={() => quarantine(lastTest.testId)}
              >
                {quarantining === lastTest.testId
                  ? <><Loader2 size={12} className="spin" /> SUBMITTING…</>
                  : <><ShieldAlert size={12} /> SUBMIT FOR QUARANTINE REVIEW</>}
              </button>
            )}
          </div>
        )}
      </GlassCard>

      {/* ---- Step 3: MY TESTS ---- */}
      <GlassCard className="aw-tests">
        <div className="card-header">
          <h3>03 · MY TESTS</h3>
          <button className="hud-btn icon-only" onClick={refresh} title="Refresh">
            <RefreshCw size={13} />
          </button>
        </div>
        <div className="aw-testlist">
          {tests.map((t) => (
            <div key={t.testId} className="aw-testrow">
              <span className="mono aw-tid">{t.testId}</span>
              <span className="aw-tname" title={t.datasetName}>{t.datasetName || t.datasetId}</span>
              <StatusBadge status={t.trustStatus} />
            </div>
          ))}
          {tests.length === 0 && <div className="aw-empty">NO TESTS RUN YET — UPLOAD A DATASET AND RUN A CHECK</div>}
        </div>
      </GlassCard>
    </div>
  );
}
