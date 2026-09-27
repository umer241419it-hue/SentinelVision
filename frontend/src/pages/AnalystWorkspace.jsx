import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  UploadCloud, PlayCircle, FlaskConical, Loader2, RefreshCw, FileJson, FileText, Cpu,
  CheckCircle2, XCircle, AlertTriangle, ShieldAlert, Building2, Plus, X, Layers, FileArchive
} from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { StatusBadge } from '../components/Badges';
import {
  uploadAsset, uploadMultipleAssets, listUploads, runTrustCheck, listMyTests, getTestDetail, submitForQuarantine,
  listContributors, createContributor
} from '../services/workflowApi';
import './AnalystWorkspace.css';

const CHECK_ORDER = ['DATA_INTEGRITY', 'DATA_DRIFT', 'MODEL_INTEGRITY', 'INFERENCE_SEAL'];
const CHECK_LABELS = {
  DATA_INTEGRITY: 'DATA INTEGRITY',
  DATA_DRIFT: 'DATA DRIFT',
  MODEL_INTEGRITY: 'MODEL INTEGRITY',
  INFERENCE_SEAL: 'INFERENCE SEAL'
};

const DATASET_LANES = [
  { kind: 'dataset-multi', label: 'MULTIPLE DATASETS', hint: '.zip · .tar · .json · .xml', accept: '.zip,.tar,.gz,.tgz,.json,.xml,.csv', icon: FileArchive },
  { kind: 'dataset-coco', label: 'COCO / JSON', hint: '.json annotations', accept: '.json', icon: FileJson },
  { kind: 'dataset-yolo', label: 'YOLO', hint: '.txt · .yaml · .yml', accept: '.txt,.yaml,.yml', icon: FileText }
];

function checkIcon(status) {
  if (status === 'PASS') return <CheckCircle2 size={13} />;
  if (status === 'FAIL') return <XCircle size={13} />;
  if (status === 'WARNING') return <AlertTriangle size={13} />;
  return <Loader2 size={13} className="spin" />;
}

export default function AnalystWorkspace({ notify }) {
  const [searchParams] = useSearchParams();
  const urlContribId = searchParams.get('contributorId');

  const [uploads, setUploads] = useState([]);
  const [tests, setTests] = useState([]);
  const [contributors, setContributors] = useState([]);
  const [selectedContributor, setSelectedContributor] = useState(urlContribId || '');
  const [trustFilter, setTrustFilter] = useState('all');

  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [quarantining, setQuarantining] = useState(null);
  const [reason, setReason] = useState('');
  const [lastTest, setLastTest] = useState(null);

  // Staged files for batch upload
  const [stagedFiles, setStagedFiles] = useState([]);
  const [stagedKind, setStagedKind] = useState('dataset');
  const [uploadProgress, setUploadProgress] = useState(null);

  // Inline Contributor Creation Modal
  const [showAddContrib, setShowAddContrib] = useState(false);
  const [newContribName, setNewContribName] = useState('');
  const [newContribDesc, setNewContribDesc] = useState('');

  const datasetMultiRef = useRef(null);
  const datasetCocoRef = useRef(null);
  const datasetYoloRef = useRef(null);
  const modelMultiRef = useRef(null);
  const datasetRef = useRef({ datasetId: '' });
  const modelSelectionRef = useRef({ modelId: '' });

  const refresh = useCallback(async () => {
    try {
      const [u, t, c] = await Promise.all([listUploads(), listMyTests(), listContributors()]);
      setUploads(u);
      setTests(t);
      setContributors(c);
    } catch (err) {
      notify?.(err.message, 'error');
    }
  }, [notify, selectedContributor]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (urlContribId) {
      setSelectedContributor(urlContribId);
      setTrustFilter(urlContribId);
    }
  }, [urlContribId]);

  // Handle files selected from file input
  const handleFilesSelected = (files, kind) => {
    if (!files || files.length === 0) return;
    const fileList = Array.from(files);
    setStagedFiles(fileList);
    setStagedKind(kind);
    setUploadProgress(null);
  };

  // Perform multi-file upload
  const executeBatchUpload = async () => {
    if (stagedFiles.length === 0) return;
    if (!selectedContributor || selectedContributor.trim() === '' || selectedContributor === 'unassigned') {
      notify?.(`Select the contributor who provided this ${stagedKind}.`, 'error');
      return;
    }
    setBusy(true);
    setUploadProgress({
      status: 'UPLOADING',
      message: `Uploading ${stagedFiles.length} file(s) for ${selectedContributor}…`,
      results: []
    });

    try {
      const resp = await uploadMultipleAssets(stagedKind, stagedFiles, selectedContributor);
      setUploadProgress({
        status: 'COMPLETED',
        message: `Completed: ${resp.successful} successful, ${resp.failed} failed`,
        results: resp.results || []
      });
      notify?.(`Uploaded ${resp.successful} of ${resp.total} ${stagedKind}(s) for ${resp.contributorName || selectedContributor}`, 'success');
      setStagedFiles([]);
      await refresh();
    } catch (err) {
      setUploadProgress({
        status: 'FAILED',
        message: err.message,
        results: []
      });
      notify?.(err.message, 'error');
    } finally {
      setBusy(false);
      if (datasetMultiRef.current) datasetMultiRef.current.value = '';
      if (datasetCocoRef.current) datasetCocoRef.current.value = '';
      if (datasetYoloRef.current) datasetYoloRef.current.value = '';
      if (modelMultiRef.current) modelMultiRef.current.value = '';
    }
  };

  const handleCreateContributor = async (e) => {
    e.preventDefault();
    if (!newContribName.trim()) return;
    try {
      const resp = await createContributor({
        name: newContribName.trim(),
        description: newContribDesc.trim() || undefined
      });
      notify?.(`Registered contributor "${resp.contributor?.name}"`, 'success');
      setShowAddContrib(false);
      setNewContribName('');
      setNewContribDesc('');
      await refresh();
      if (resp.contributor?.id) {
        setSelectedContributor(resp.contributor.id);
      }
    } catch (err) {
      notify?.(err.message || 'Failed to create contributor', 'error');
    }
  };

  const filteredDatasets = uploads.filter((u) => {
    if (u.kind !== 'dataset') return false;
    if (trustFilter !== 'all') return (u.contributorId || 'unassigned') === trustFilter;
    return true;
  });

  const filteredModels = uploads.filter((u) => {
    if (u.kind !== 'model') return false;
    if (trustFilter !== 'all') return (u.contributorId || 'unassigned') === trustFilter;
    return true;
  });

  async function runTrust() {
    const dsId = datasetRef.current?.datasetId;
    if (!dsId) {
      notify?.('Select a dataset first.', 'error');
      return;
    }

    const dsObj = uploads.find((u) => u.uploadId === dsId);
    const modelId = modelSelectionRef.current?.modelId || null;
    const modelObj = uploads.find((u) => u.uploadId === modelId);

    const contributorId = dsObj?.contributorId || modelObj?.contributorId || 'unassigned';
    const contributorName = dsObj?.contributorName || modelObj?.contributorName || 'Unassigned';

    setRunning(true);
    setLastTest(null);
    try {
      const data = await runTrustCheck({
        datasetId: dsId,
        modelId,
        contributorId,
        contributorName
      });
      let current = data.test;
      setLastTest(current);

      const deadline = Date.now() + 30 * 60 * 1000;
      while (current && ['QUEUED', 'RUNNING'].includes(current.status) && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        current = await getTestDetail(data.test.testId);
        setLastTest(current);
      }

      if (current?.status === 'COMPLETED') {
        notify?.(`Trust check complete · ${current.testId} → ${current.trustStatus}`, current.trustStatus === 'PASS' ? 'success' : 'warning');
      } else if (current?.status === 'FAILED') {
        notify?.(`Trust check failed · ${current.error || 'see execution log'}`, 'error');
      } else {
        notify?.('Trust check timed out while the backend job was still running.', 'warning');
      }
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
          <span className="hdr-meta">MULTI-FILE UPLOAD WITH CONTRIBUTOR / VENDOR GROUPING</span>
        </div>

        {/* Contributor Selection */}
        <div className="aw-contrib-row">
          <label className="aw-contrib-label">Provided By *</label>
          <select
            className="aw-contrib-dropdown"
            value={selectedContributor}
            onChange={(e) => {
              if (e.target.value === '__NEW__') {
                setShowAddContrib(true);
              } else {
                setSelectedContributor(e.target.value);
              }
            }}
          >
            <option value="">— Select Contributor / Vendor * —</option>
            {contributors.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.type || 'VENDOR'})
              </option>
            ))}
            <option value="__NEW__">+ Register New Contributor…</option>
          </select>
          <button
            type="button"
            className="hud-btn ghost"
            style={{ fontSize: '11px', whiteSpace: 'nowrap' }}
            onClick={() => setShowAddContrib(true)}
          >
            <Plus size={12} style={{ marginRight: 2 }} /> New Contributor
          </button>
        </div>
        <div style={{ fontSize: '10.5px', color: 'var(--text-muted)', marginBottom: '10px', fontStyle: 'italic' }}>
          Assigns source ownership and contributor attribution to all uploaded assets.
        </div>

        {/* Drop / Choose Buttons */}
        <div className="aw-drop-row">
          <button
            className="aw-drop"
            disabled={busy}
            onClick={() => datasetMultiRef.current?.click()}
          >
            <FileArchive size={18} />
            <strong>DATASETS</strong>
            <span>Select 1 or more files</span>
          </button>

          <button
            className="aw-drop"
            disabled={busy}
            onClick={() => modelMultiRef.current?.click()}
          >
            <Cpu size={18} />
            <strong>MODELS</strong>
            <span>Select 1 or more (.pt, .onnx)</span>
          </button>
        </div>

        {/* Hidden inputs with 'multiple' attribute */}
        <input
          ref={datasetMultiRef}
          type="file"
          multiple
          hidden
          onChange={(e) => handleFilesSelected(e.target.files, 'dataset')}
        />
        <input
          ref={modelMultiRef}
          type="file"
          multiple
          hidden
          onChange={(e) => handleFilesSelected(e.target.files, 'model')}
        />

        {/* Staged files box */}
        {stagedFiles.length > 0 && (
          <div className="aw-staging-box">
            <div className="aw-staging-head">
              <span>Selected {stagedFiles.length} {stagedKind === 'model' ? (stagedFiles.length === 1 ? 'Model' : 'Models') : (stagedFiles.length === 1 ? 'Dataset' : 'Datasets')} · Provided by {contributors.find((c) => c.id === selectedContributor)?.name || selectedContributor || 'Unassigned'}</span>
              <button className="hud-btn icon-only ghost" onClick={() => setStagedFiles([])} title="Cancel">
                <X size={12} />
              </button>
            </div>
            <div className="aw-staging-list">
              {stagedFiles.map((f, i) => (
                <div key={i} className="aw-staging-item">
                  <span>{f.name}</span>
                  <span className="mono" style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                    {(f.size / (1024 * 1024)).toFixed(2)} MB
                  </span>
                </div>
              ))}
            </div>
            <button
              className="auth-submit"
              disabled={busy}
              onClick={executeBatchUpload}
              style={{ marginTop: 4, width: '100%', justifyContent: 'center' }}
            >
              {busy ? (
                <><Loader2 size={13} className="spin" /> Uploading…</>
              ) : (
                <><UploadCloud size={14} style={{ marginRight: 6 }} /> Upload {stagedFiles.length} {stagedKind === 'model' ? (stagedFiles.length === 1 ? 'Model' : 'Models') : (stagedFiles.length === 1 ? 'Dataset' : 'Datasets')}</>
              )}
            </button>
          </div>
        )}

        {/* Upload Progress & Results */}
        {uploadProgress && (
          <div className="aw-upload-progress">
            <div className="aw-prog-status">
              {uploadProgress.status === 'UPLOADING' && <Loader2 size={12} className="spin" />}
              {uploadProgress.status === 'COMPLETED' && <CheckCircle2 size={12} style={{ color: '#34d399' }} />}
              {uploadProgress.status === 'FAILED' && <XCircle size={12} style={{ color: '#ef4444' }} />}
              <span>{uploadProgress.message}</span>
            </div>
            {uploadProgress.results?.length > 0 && (
              <div style={{ marginTop: 4 }}>
                {uploadProgress.results.map((r, i) => (
                  <div key={i} className={`aw-prog-item ${(r.status || '').toLowerCase()}`}>
                    <span>{r.filename}</span>
                    <span>{r.status} {r.error ? `(${r.error})` : ''}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Uploads List with Contributor Badges */}
        <div className="aw-uplist">
          {uploads.slice(0, 8).map((u) => (
            <div key={u.uploadId} className="aw-uprow">
              <span className={`aw-kind ${u.kind}`}>{u.kind === 'model' ? 'MDL' : 'DS'}</span>
              <span className="aw-upname" title={u.originalName}>{u.originalName}</span>
              <span className="aw-contributor-tag" title="Contributor">
                {u.contributorName || u.contributorId || 'Unassigned'}
              </span>
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
          <span className="hdr-meta">ASSURANCE ENGINE PRESERVES CONTRIBUTOR / VENDOR CONTEXT</span>
        </div>

        {/* Contributor Filter */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12 }}>
          <span style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            Filter by Contributor:
          </span>
          <select
            className="aw-contrib-dropdown"
            style={{ maxWidth: '240px' }}
            value={trustFilter}
            onChange={(e) => setTrustFilter(e.target.value)}
          >
            <option value="all">All Contributors ({uploads.length} assets)</option>
            {contributors.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <div className="aw-pick-row">
          <label className="aw-pick">
            <span>DATASET</span>
            <select
              defaultValue=""
              onChange={(e) => { if (datasetRef.current) datasetRef.current.datasetId = e.target.value; }}
            >
              <option value="">— select dataset —</option>
              {contributors.map((c) => {
                const cDatasets = filteredDatasets.filter((d) => (d.contributorId || 'unassigned') === c.id);
                if (cDatasets.length === 0) return null;
                return (
                  <optgroup key={c.id} label={`${c.name} (${cDatasets.length})`}>
                    {cDatasets.map((d) => (
                      <option key={d.uploadId} value={d.uploadId}>
                        {d.originalName} ({d.uploadId})
                      </option>
                    ))}
                  </optgroup>
                );
              })}
              {filteredDatasets.filter((d) => !d.contributorId || d.contributorId === 'unassigned').length > 0 && (
                <optgroup label="Unassigned / Legacy">
                  {filteredDatasets
                    .filter((d) => !d.contributorId || d.contributorId === 'unassigned')
                    .map((d) => (
                      <option key={d.uploadId} value={d.uploadId}>
                        {d.originalName} ({d.uploadId})
                      </option>
                    ))}
                </optgroup>
              )}
            </select>
          </label>

          <label className="aw-pick">
            <span>MODEL (OPTIONAL)</span>
            <select
              defaultValue=""
              onChange={(e) => { modelSelectionRef.current.modelId = e.target.value; }}
            >
              <option value="">— none —</option>
              {contributors.map((c) => {
                const cModels = filteredModels.filter((m) => (m.contributorId || 'unassigned') === c.id);
                if (cModels.length === 0) return null;
                return (
                  <optgroup key={c.id} label={`${c.name} (${cModels.length})`}>
                    {cModels.map((m) => (
                      <option key={m.uploadId} value={m.uploadId}>
                        {m.originalName} ({m.uploadId})
                      </option>
                    ))}
                  </optgroup>
                );
              })}
              {filteredModels.filter((m) => !m.contributorId || m.contributorId === 'unassigned').length > 0 && (
                <optgroup label="Unassigned / Legacy">
                  {filteredModels
                    .filter((m) => !m.contributorId || m.contributorId === 'unassigned')
                    .map((m) => (
                      <option key={m.uploadId} value={m.uploadId}>
                        {m.originalName} ({m.uploadId})
                      </option>
                    ))}
                </optgroup>
              )}
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
              <span className="mono aw-verdict-id">
                {lastTest.testId} · Contributor: {lastTest.contributorName || lastTest.contributorId || 'Unassigned'}
              </span>
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
              <span className="aw-tname" title={t.datasetName}>
                {t.datasetName || t.datasetId}
              </span>
              <span className="aw-contributor-tag">
                {t.contributorName || t.contributorId || 'Unassigned'}
              </span>
              <StatusBadge status={t.trustStatus} />
            </div>
          ))}
          {tests.length === 0 && <div className="aw-empty">NO TESTS RUN YET — UPLOAD A DATASET AND RUN A CHECK</div>}
        </div>
      </GlassCard>

      {/* Quick Add Contributor Modal */}
      {showAddContrib && (
        <div className="contrib-modal-backdrop" onClick={() => setShowAddContrib(false)}>
          <div className="contrib-modal" onClick={(e) => e.stopPropagation()}>
            <div className="contrib-modal-head">
              <h3>REGISTER CONTRIBUTOR / VENDOR</h3>
              <button className="hud-btn icon-only ghost" onClick={() => setShowAddContrib(false)}>
                <X size={15} />
              </button>
            </div>
            <form onSubmit={handleCreateContributor}>
              <div className="contrib-modal-body">
                <div className="contrib-field">
                  <label>Contributor Name *</label>
                  <input
                    required
                    placeholder="e.g. Vendor Delta"
                    value={newContribName}
                    onChange={(e) => setNewContribName(e.target.value)}
                  />
                </div>
                <div className="contrib-field">
                  <label>Description</label>
                  <textarea
                    rows={2}
                    placeholder="Source attribution notes…"
                    value={newContribDesc}
                    onChange={(e) => setNewContribDesc(e.target.value)}
                  />
                </div>
              </div>
              <div className="contrib-modal-foot">
                <button type="button" className="hud-btn ghost" onClick={() => setShowAddContrib(false)}>
                  Cancel
                </button>
                <button type="submit" className="auth-submit">
                  Register
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
