import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckCircle2, XCircle, Loader2, RefreshCw, ShieldCheck,
  ScanLine, UploadCloud, Cpu, FolderOpen, FileCode, AlertTriangle
} from 'lucide-react';
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

/** Recursively scan dropped folder entries */
async function scanFiles(items) {
  const files = [];
  async function readEntry(entry, currentPath = '') {
    if (entry.isFile) {
      const file = await new Promise((resolve, reject) => entry.file(resolve, reject));
      const relPath = currentPath ? `${currentPath}/${file.name}` : file.name;
      Object.defineProperty(file, 'webkitRelativePath', {
        value: relPath,
        writable: true,
        configurable: true
      });
      files.push(file);
    } else if (entry.isDirectory) {
      const dirReader = entry.createReader();
      const readAllEntries = async () => {
        const batch = await new Promise((resolve, reject) => dirReader.readEntries(resolve, reject));
        if (batch.length > 0) {
          for (const child of batch) {
            await readEntry(child, currentPath ? `${currentPath}/${entry.name}` : entry.name);
          }
          await readAllEntries();
        }
      };
      await readAllEntries();
    }
  }

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.webkitGetAsEntry) {
      const entry = item.webkitGetAsEntry();
      if (entry) await readEntry(entry);
    } else if (item.kind === 'file') {
      const f = item.getAsFile();
      if (f) files.push(f);
    }
  }
  return files;
}

export default function ModelValidation({ notify }) {
  const [sourceMode, setSourceMode] = useState('registered'); // 'registered' | 'upload'
  const [contributors, setContributors] = useState([]);
  const [models, setModels] = useState([]);
  const [history, setHistory] = useState([]);
  const [contributorId, setContributorId] = useState('');
  const [modelId, setModelId] = useState('');
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);
  const pickerRef = useRef(null);

  async function load() {
    try {
      const [cs, hs] = await Promise.all([listContributors(), listModelValidations()]);
      setContributors(cs);
      setHistory(hs);
      if (cs && cs.length > 0 && !contributorId) {
        setContributorId(cs[0].id);
      }
    } catch (err) {
      notify?.(err.message, 'error');
    }
  }

  async function refreshModels(targetContributor) {
    try {
      const q = targetContributor && targetContributor !== 'all' ? targetContributor : 'all';
      const fetched = await listModels(q);
      setModels(fetched);
    } catch (err) {
      setModels([]);
      notify?.(err.message, 'error');
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    setModelId('');
    refreshModels(contributorId);
  }, [contributorId]);

  // Ensure Chromium / Electron folder picker attributes are reliably applied
  useEffect(() => {
    if (folderInputRef.current) {
      folderInputRef.current.webkitdirectory = true;
      folderInputRef.current.directory = true;
      folderInputRef.current.setAttribute('webkitdirectory', '');
      folderInputRef.current.setAttribute('directory', '');
    }
  }, []);

  // Dismiss picker popover on outside click
  useEffect(() => {
    function handleDocClick(e) {
      if (pickerRef.current && !pickerRef.current.contains(e.target)) {
        setPickerOpen(false);
      }
    }
    if (pickerOpen) {
      document.addEventListener('click', handleDocClick);
      return () => document.removeEventListener('click', handleDocClick);
    }
  }, [pickerOpen]);

  const selectedModel = useMemo(() => models.find((m) => m.id === modelId), [models, modelId]);

  async function handleFilesSelected(pickedList) {
    const picked = Array.from(pickedList || []);
    if (!picked.length) return;
    if (!contributorId || contributorId === 'all') {
      notify?.('Select a specific contributor / vendor before uploading the model.', 'error');
      return;
    }
    setUploading(true);
    setReport(null);
    setPickerOpen(false);

    try {
      const isFolder = picked.length > 1 || Boolean(picked[0]?.webkitRelativePath && picked[0].webkitRelativePath.includes('/'));
      const displayName = isFolder
        ? (picked[0].webkitRelativePath ? picked[0].webkitRelativePath.split('/')[0] : 'Model Folder')
        : picked[0].name;

      const result = await uploadMultipleAssets('model', picked, contributorId);
      const first = result?.results?.[0];
      if (!first || !['SUCCESS', 'EXISTS'].includes(first.status)) {
        throw new Error(first?.error || result?.error || 'Model upload failed');
      }

      notify?.(`Model "${displayName}" uploaded successfully. Validating model artifact…`, 'success');

      // Refresh dynamic registered models
      await refreshModels(contributorId);
      setModelId(first.uploadId);

      // Execute artifact validation
      const r = await validateModel(first.uploadId);
      setReport(r);
      await load();
      notify?.(`Model validation: ${r.status}`, r.status === 'VALID' ? 'success' : 'error');
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
      if (folderInputRef.current) folderInputRef.current.value = '';
    }
  }

  async function runValidation() {
    if (!modelId) {
      notify?.('Select a registered model before validation.', 'error');
      return;
    }
    if (selectedModel?.available === false) {
      notify?.('This model is unavailable because its file is missing from local storage.', 'error');
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

  function handleDragOver(e) {
    e.preventDefault();
    if (!busy && !uploading) setDragOver(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    setDragOver(false);
  }

  async function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    if (busy || uploading) return;

    const items = e.dataTransfer.items;
    if (items && items.length > 0) {
      try {
        const scanned = await scanFiles(items);
        if (scanned.length > 0) {
          handleFilesSelected(scanned);
          return;
        }
      } catch (err) {
        console.warn('Folder drag scan fallback:', err);
      }
    }
    const droppedFiles = Array.from(e.dataTransfer.files || []);
    if (droppedFiles.length > 0) {
      handleFilesSelected(droppedFiles);
    }
  }

  return (
    <div className="anim-fade mv-grid">
      <GlassCard className="mv-select">
        <div className="card-header">
          <h3>01 · MODEL VALIDATION</h3>
          <span className="text-muted" style={{ fontSize: 10 }}>ARTIFACT INTEGRITY GATE</span>
          <button className="hud-btn icon-only" onClick={load} title="Refresh"><RefreshCw size={13} /></button>
        </div>

        {/* 2 Model Input Methods */}
        <div className="mv-source-choice-container">
          <button
            type="button"
            className={`mv-source-choice ${sourceMode === 'registered' ? 'active' : ''}`}
            onClick={() => {
              setSourceMode('registered');
              setReport(null);
              setPickerOpen(false);
            }}
            disabled={busy || uploading}
          >
            <div className="mv-source-header">
              <Cpu size={16} />
              <span className="mv-source-title">Use Registered Model</span>
            </div>
            <span className="mv-source-sub">Select an existing model from the repository</span>
          </button>

          <div className="mv-source-choice-divider">
            <span>OR</span>
          </div>

          <button
            type="button"
            className={`mv-source-choice ${sourceMode === 'upload' ? 'active' : ''}`}
            onClick={() => {
              setSourceMode('upload');
              setModelId('');
              setReport(null);
              setPickerOpen(false);
            }}
            disabled={busy || uploading}
          >
            <div className="mv-source-header">
              <UploadCloud size={16} />
              <span className="mv-source-title">Upload Model</span>
            </div>
            <span className="mv-source-sub">Select model file or complete model folder</span>
          </button>
        </div>

        {sourceMode === 'registered' ? (
          <div className="mv-pane mv-registered-pane">
            <label className="mv-label">CONTRIBUTOR / VENDOR</label>
            <select
              className="mv-selectbox"
              value={contributorId}
              onChange={(e) => {
                setContributorId(e.target.value);
                setModelId('');
              }}
              disabled={busy || uploading}
            >
              <option value="">ALL CONTRIBUTORS / VENDORS</option>
              {contributors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <div className="mv-help">Filter registered models by contributing vendor.</div>

            <label className="mv-label">REGISTERED MODEL *</label>
            <select
              className="mv-selectbox"
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              disabled={busy || uploading}
            >
              <option value="">SELECT REGISTERED MODEL</option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.contributorName || 'Unassigned'}){m.available === false ? ' [UNAVAILABLE]' : ''}
                </option>
              ))}
            </select>

            {selectedModel && (
              <div className="mv-asset">
                <div><span>MODEL</span><b>{selectedModel.name}</b></div>
                <div><span>PROVIDER</span><b>{selectedModel.contributorName}</b></div>
                <div><span>FORMAT</span><b>{selectedModel.framework || 'Unknown'}{selectedModel.isFolder ? ' (Folder)' : ''}</b></div>
                <div><span>SIZE</span><b>{fmtBytes(selectedModel.size)}</b></div>
                <div><span>SHA-256</span><b className="mono">{selectedModel.sha256?.slice(0, 16)}…</b></div>
                <div>
                  <span>STATUS</span>
                  <b style={{ color: selectedModel.available !== false ? 'var(--accent-green, #10b981)' : 'var(--accent-red, #ef4444)' }}>
                    {selectedModel.available !== false ? 'AVAILABLE LOCALLY' : 'UNAVAILABLE'}
                  </b>
                </div>
                {selectedModel.available === false && (
                  <div className="mv-asset-warning">
                    <AlertTriangle size={13} /> {selectedModel.unavailableReason || 'Asset file is not present locally in SentinelVision repository.'}
                  </div>
                )}
              </div>
            )}

            <button
              type="button"
              className="auth-submit mv-action"
              disabled={busy || uploading || !modelId || selectedModel?.available === false}
              onClick={runValidation}
            >
              {busy ? (
                <><Loader2 size={14} className="spin" /> VALIDATING REGISTERED MODEL…</>
              ) : selectedModel?.available === false ? (
                <><AlertTriangle size={14} /> MODEL MISSING LOCALLY</>
              ) : (
                <><ShieldCheck size={14} /> VALIDATE REGISTERED MODEL</>
              )}
            </button>
          </div>
        ) : (
          <div className="mv-pane mv-upload-pane">
            <label className="mv-label">CONTRIBUTOR / VENDOR *</label>
            <select
              className="mv-selectbox"
              value={contributorId}
              onChange={(e) => setContributorId(e.target.value)}
              disabled={busy || uploading}
            >
              <option value="">SELECT CONTRIBUTOR / VENDOR</option>
              {contributors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <div className="mv-help">Select the contributor / vendor who supplied this model.</div>

            <div
              className={`mv-upload-action-box ${dragOver ? 'drag-over' : ''} ${uploading || busy ? 'busy' : ''}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => {
                if (!busy && !uploading && contributorId) {
                  setPickerOpen((v) => !v);
                }
              }}
            >
              <div className="mv-upload-icon-wrap">
                {uploading || busy ? <Loader2 size={24} className="spin" /> : <UploadCloud size={24} />}
              </div>

              <div className="mv-upload-btn-wrap" ref={pickerRef} onClick={(e) => e.stopPropagation()}>
                <button
                  type="button"
                  className="auth-submit mv-single-upload-btn"
                  disabled={busy || uploading || !contributorId}
                  onClick={() => setPickerOpen((v) => !v)}
                >
                  {uploading ? (
                    <><Loader2 size={14} className="spin" /> UPLOADING & VALIDATING…</>
                  ) : (
                    <><UploadCloud size={14} /> Upload Model</>
                  )}
                </button>

                {pickerOpen && !busy && !uploading && (
                  <div className="mv-picker-popover anim-scale-up">
                    <div className="mv-picker-popover-title">SELECT MODEL SOURCE</div>
                    <button
                      type="button"
                      className="mv-picker-option"
                      onClick={() => {
                        setPickerOpen(false);
                        folderInputRef.current?.click();
                      }}
                    >
                      <FolderOpen size={16} className="mv-picker-icon" />
                      <div className="mv-picker-text">
                        <strong>Complete Model Folder</strong>
                        <span>Upload folder containing model weights, config & metadata</span>
                      </div>
                    </button>
                    <button
                      type="button"
                      className="mv-picker-option"
                      onClick={() => {
                        setPickerOpen(false);
                        fileInputRef.current?.click();
                      }}
                    >
                      <FileCode size={16} className="mv-picker-icon" />
                      <div className="mv-picker-text">
                        <strong>Individual Model File</strong>
                        <span>Select .pt, .pth, .onnx, .bin, .h5, .keras, or .tflite</span>
                      </div>
                    </button>
                  </div>
                )}
              </div>

              <span className="mv-upload-hint">
                {uploading
                  ? 'Uploading model and running artifact validation…'
                  : 'Select model file or complete model folder, or drop here'}
              </span>
              <span className="mv-upload-meta mono">
                SUPPORTS .PT, .PTH, .ONNX, .BIN, .H5, .KERAS, .TFLITE, .CKPT OR COMPLETE FOLDERS
              </span>
            </div>

            {/* Hidden native inputs: folder and file */}
            <input
              ref={fileInputRef}
              type="file"
              hidden
              accept=".pt,.pth,.onnx,.bin,.h5,.keras,.tflite,.ckpt,.tar,.gz"
              onChange={(e) => handleFilesSelected(e.target.files)}
            />
            <input
              ref={folderInputRef}
              type="file"
              hidden
              multiple
              webkitdirectory=""
              directory=""
              onChange={(e) => handleFilesSelected(e.target.files)}
            />
          </div>
        )}
      </GlassCard>

      <GlassCard className="mv-report">
        <div className="card-header">
          <h3>02 · MODEL VALIDATION RESULT</h3>
          {report && <StatusBadge status={report.status === 'VALID' ? 'PASS' : 'FAIL'} />}
        </div>
        {!report && !busy && !uploading && (
          <div className="mv-empty">SELECT A REGISTERED MODEL OR UPLOAD A MODEL FILE / FOLDER TO RUN VALIDATION</div>
        )}
        {(busy || uploading) && (
          <div className="mv-progress">
            <Loader2 size={15} className="spin" /> {uploading ? 'UPLOADING MODEL TO REPOSITORY…' : 'CHECKING MODEL REGISTRY AND FILE INTEGRITY…'}
          </div>
        )}
        {report && !busy && !uploading && (
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
                <div className="mv-engine-title"><ScanLine size={13} /> ARTIFACT ASSURANCE: {report.engine.status}</div>
                <div className="mono mv-engine-meta">ENGINE: {report.engine.engine || 'SentinelVision Artifact Integrity Validator'} · MODEL ID: {report.engine.modelId}</div>
                {report.engine.output && <div className="mono mv-engine-meta">VERDICT: {report.engine.output.verdict || '—'} · FINDINGS: {(report.engine.output.findings || []).length}</div>}
                {report.engine.stderr && report.engine.status !== 'COMPLETED' && <pre className="mv-engine-log">{report.engine.stderr.slice(-3000)}</pre>}
              </div>
            )}
          </div>
        )}
      </GlassCard>

      <GlassCard className="mv-history">
        <div className="card-header">
          <h3>03 · VALIDATION HISTORY</h3>
          <span className="text-muted" style={{ fontSize: 10 }}>FILE / FORMAT / HASH / ATTRIBUTION</span>
        </div>
        <DataTable
          columns={[
            { key: 'modelName', label: 'Model' },
            { key: 'contributorName', label: 'Contributor' },
            { key: 'framework', label: 'Framework' },
            { key: 'status', label: 'Artifact Check', render: (r) => <StatusBadge status={r.status === 'VALID' ? 'PASS' : 'FAIL'} /> },
            { key: 'computedSha256', label: 'SHA-256', render: (r) => <span className="mono">{r.computedSha256?.slice(0, 12)}…</span> },
            { key: 'validatedAt', label: 'Time', render: (r) => fmtTime(r.validatedAt) }
          ]}
          rows={history}
          emptyMessage="NO MODEL VALIDATIONS YET"
        />
        <div className="mv-help" style={{ marginTop: 10 }}>Model Validation verifies the supplied artifact. Backdoor and behavioural analysis is shown separately under Model Integrity.</div>
      </GlassCard>
    </div>
  );
}
