import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Loader2, CheckCircle2, XCircle, AlertTriangle,
  Ban, RefreshCw, UploadCloud, DatabaseZap, ShieldCheck,
  FolderOpen, FileCode
} from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { StatusBadge } from '../components/Badges';
import DataTable from '../components/DataTable';
import {
  clientValidateFile, uploadAndValidateDataset, listDatasets, listDatasetValidations,
  BLOCKED_EXTENSIONS
} from '../services/datasetValidationApi';
import { listContributors } from '../services/workflowApi';
import './DatasetValidation.css';

const REPORT_STATUS_META = {
  valid: { label: 'VALID', cls: 'pass' },
  warning: { label: 'WARNING', cls: 'warning' },
  invalid: { label: 'FAILED', cls: 'fail' },
  rejected: { label: 'REJECTED', cls: 'rejected' }
};

function reportMeta(status) {
  return REPORT_STATUS_META[status] || { label: String(status || '—').toUpperCase(), cls: 'pass' };
}

function fmtBytes(n) {
  if (n == null) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function fmtTime(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
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

/**
 * DatasetValidation — Unified Data Integrity gate.
 * Provides TWO dataset input methods:
 * 1. Use Registered Dataset (Select an existing dataset from the repository)
 * 2. Upload Dataset (Upload a new dataset via single unified control)
 */
export default function DatasetValidation({ notify }) {
  const [sourceMode, setSourceMode] = useState('registered'); // 'registered' | 'upload'
  const [availableDatasets, setAvailableDatasets] = useState([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState('');
  const [contributors, setContributors] = useState([]);
  const [contributorId, setContributorId] = useState('');
  const [kind, setKind] = useState('yolo');
  const [files, setFiles] = useState([]);
  const [precheck, setPrecheck] = useState([]);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const inputRef = useRef(null);
  const folderInputRef = useRef(null);
  const pickerRef = useRef(null);

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await listDatasetValidations());
    } catch {
      /* history is non-critical UI */
    }
  }, []);

  const loadRegisteredDatasets = useCallback(async () => {
    try {
      const list = await listDatasets('all');
      setAvailableDatasets(list);
    } catch {
      setAvailableDatasets([]);
    }
  }, []);

  useEffect(() => {
    refreshHistory();
    loadRegisteredDatasets();
    listContributors()
      .then((list) => {
        setContributors(list);
        if (list && list.length > 0 && !contributorId) {
          setContributorId(list[0].id);
        }
      })
      .catch(() => setContributors([]));
  }, [refreshHistory, loadRegisteredDatasets, contributorId]);

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

  function selectRegisteredDataset(id) {
    setSelectedDatasetId(id);
    const d = availableDatasets.find((item) => (item.id || item.uploadId) === id);
    if (d) {
      if (d.contributorId && d.contributorId !== 'unassigned') {
        setContributorId(d.contributorId);
      }
      if (d.format && ['yolo', 'coco'].includes(d.format.toLowerCase())) {
        setKind(d.format.toLowerCase());
      }
    }
  }

  async function validateRegisteredDataset() {
    if (!selectedDatasetId) {
      notify?.('Select a registered dataset to validate.', 'error');
      return;
    }
    const ds = availableDatasets.find((item) => (item.id || item.uploadId) === selectedDatasetId);
    if (ds?.available === false) {
      notify?.('This dataset is unavailable because its files are missing from local storage.', 'error');
      return;
    }
    const targetContributor = ds?.contributorId || contributorId;
    if (!targetContributor) {
      notify?.('Select the contributor associated with this dataset.', 'error');
      return;
    }

    setBusy(true);
    setReport(null);
    try {
      const targetKind = ds?.format && ['yolo', 'coco'].includes(ds.format.toLowerCase())
        ? ds.format.toLowerCase()
        : kind;
      const { report: r } = await uploadAndValidateDataset(targetKind, [], targetContributor, selectedDatasetId);
      setReport(r);
      const meta = reportMeta(r.status);
      notify?.(
        `Dataset validation: ${meta.label} · ${r.files_processed || 0} file(s) · ${r.errors || 0} error(s) · ${r.warnings || 0} warning(s)`,
        r.status === 'valid' || r.status === 'warning' ? 'success' : 'error'
      );
      refreshHistory();
    } catch (err) {
      notify?.(err.message || 'Validation request failed', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function handleFilesSelected(pickedList) {
    const picked = Array.from(pickedList || []);
    if (!picked.length) return;

    if (!contributorId || contributorId === 'all') {
      notify?.('Select a specific contributor / vendor before uploading the dataset.', 'error');
      return;
    }

    setFiles(picked);
    setReport(null);
    setPickerOpen(false);

    // Auto-detect format from files: if .json is present without .txt -> coco, else if .txt/.yaml -> yolo
    const hasJson = picked.some(f => f.name.toLowerCase().endsWith('.json') || (f.webkitRelativePath && f.webkitRelativePath.toLowerCase().endsWith('.json')));
    const hasYolo = picked.some(f => f.name.toLowerCase().endsWith('.txt') || f.name.toLowerCase().endsWith('.yaml') || f.name.toLowerCase().endsWith('.yml'));
    const detectedKind = (hasJson && !hasYolo) ? 'coco' : (hasYolo && !hasJson ? 'yolo' : (hasJson ? 'coco' : 'yolo'));
    setKind(detectedKind);

    // Client-side precheck: block hazardous binaries
    const checks = await Promise.all(
      picked.map(async (f) => ({
        name: f.name,
        size: f.size,
        ...(await clientValidateFile(f, detectedKind))
      }))
    );
    setPrecheck(checks);

    const blocked = checks.filter((c) => !c.ok && c.reason && BLOCKED_EXTENSIONS.some((ext) => c.reason.includes(ext)));
    if (blocked.length > 0) {
      notify?.(`${blocked.length} file(s) failed client-side security checks.`, 'error');
      return;
    }

    setBusy(true);
    try {
      const { report: r } = await uploadAndValidateDataset(detectedKind, picked, contributorId);
      setReport(r);
      const meta = reportMeta(r.status);
      notify?.(
        `Dataset validation: ${meta.label} · ${r.files_processed || picked.length} file(s) · ${r.errors || 0} error(s) · ${r.warnings || 0} warning(s)`,
        r.status === 'valid' || r.status === 'warning' ? 'success' : 'error'
      );
      refreshHistory();
      loadRegisteredDatasets();
    } catch (err) {
      notify?.(err.message || 'Dataset validation failed', 'error');
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
      if (folderInputRef.current) folderInputRef.current.value = '';
    }
  }

  function handleDragOver(e) {
    e.preventDefault();
    if (!busy) setDragOver(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    setDragOver(false);
  }

  async function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    if (busy) return;

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

  const filteredDatasets = useMemo(() => {
    if (!contributorId || contributorId === 'all') return availableDatasets;
    return availableDatasets.filter((d) => !d.contributorId || d.contributorId === contributorId);
  }, [availableDatasets, contributorId]);

  const selectedDataset = useMemo(() => {
    return availableDatasets.find((d) => (d.id || d.uploadId) === selectedDatasetId);
  }, [availableDatasets, selectedDatasetId]);

  const meta = report ? reportMeta(report.status) : null;
  const stats = report?.stats || {};

  const statRows = [
    ...(report?.datasetName || selectedDataset?.name ? [['Dataset', report?.datasetName || selectedDataset?.name]] : []),
    ['Images', stats.images],
    ['Annotation files', stats.annotation_files],
    ['Annotations', stats.annotations],
    ['Classes', stats.classes],
    ['Images without annotations', stats.images_without_annotations],
    ['Annotations without images', stats.annotations_without_images],
    ['Empty annotation files', stats.empty_annotation_files],
    ['Invalid files', stats.invalid_files],
    ['Duplicate files', stats.duplicate_files],
    ['Unknown class IDs', stats.unknown_class_ids],
    ['Out-of-bounds boxes', stats.out_of_bounds_boxes]
  ].filter(([, v]) => v != null);

  return (
    <div className="anim-fade dv-grid">
      {/* ---- Step 1: DATA VALIDATION GATE ---- */}
      <GlassCard className="dv-upload">
        <div className="card-header">
          <h3>01 · DATA VALIDATION</h3>
          <span className="text-muted" style={{ fontSize: 10 }}>DATA INTEGRITY PIPELINE</span>
        </div>

        {/* 2 Dataset Input Methods */}
        <div className="dv-source-choice-container">
          <button
            type="button"
            className={`dv-source-choice ${sourceMode === 'registered' ? 'active' : ''}`}
            onClick={() => {
              setSourceMode('registered');
              setFiles([]);
              setPrecheck([]);
              setReport(null);
            }}
            disabled={busy}
          >
            <div className="dv-source-header">
              <DatabaseZap size={16} />
              <span className="dv-source-title">Use Registered Dataset</span>
            </div>
            <span className="dv-source-sub">Select an existing dataset from the repository</span>
          </button>

          <div className="dv-source-choice-divider">
            <span>OR</span>
          </div>

          <button
            type="button"
            className={`dv-source-choice ${sourceMode === 'upload' ? 'active' : ''}`}
            onClick={() => {
              setSourceMode('upload');
              setSelectedDatasetId('');
              setReport(null);
            }}
            disabled={busy}
          >
            <div className="dv-source-header">
              <UploadCloud size={16} />
              <span className="dv-source-title">Upload Dataset</span>
            </div>
            <span className="dv-source-sub">Upload a new dataset from your local machine</span>
          </button>
        </div>

        {sourceMode === 'registered' ? (
          <div className="dv-pane dv-registered-pane">
            <div className="dv-contributor-row">
              <label className="dv-field-label">CONTRIBUTOR / VENDOR</label>
              <select
                className="dv-contributor-select"
                value={contributorId}
                onChange={(e) => {
                  setContributorId(e.target.value);
                  setSelectedDatasetId('');
                }}
                disabled={busy}
              >
                <option value="">ALL CONTRIBUTORS / VENDORS</option>
                {contributors.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>

            <div className="dv-contributor-row">
              <label className="dv-field-label">REGISTERED DATASET *</label>
              <select
                className="dv-contributor-select"
                value={selectedDatasetId}
                onChange={(e) => selectRegisteredDataset(e.target.value)}
                disabled={busy}
              >
                <option value="">SELECT REGISTERED DATASET</option>
                {filteredDatasets.map((d) => (
                  <option key={d.id || d.uploadId} value={d.id || d.uploadId}>
                    {d.name || d.id} ({d.contributorName || 'Unassigned'})
                  </option>
                ))}
              </select>
              <span className="dv-field-help">
                {filteredDatasets.length
                  ? `${filteredDatasets.length} registered dataset(s) available in local registry.`
                  : 'No registered datasets found for this filter.'}
              </span>
            </div>

            {selectedDataset && (
              <div className="dv-asset-details">
                <div><span>DATASET</span><b>{selectedDataset.name || selectedDataset.id}</b></div>
                <div><span>PROVIDER</span><b>{selectedDataset.contributorName}</b></div>
                <div><span>FORMAT</span><b>{selectedDataset.format || 'Unknown'}{selectedDataset.isFolder ? ' (Folder)' : ''}</b></div>
                <div><span>SHA-256</span><b className="mono">{selectedDataset.sha256?.slice(0, 16)}…</b></div>
                <div>
                  <span>STATUS</span>
                  <b style={{ color: selectedDataset.available !== false ? 'var(--accent-green, #10b981)' : 'var(--accent-red, #ef4444)' }}>
                    {selectedDataset.available !== false ? 'AVAILABLE LOCALLY' : 'UNAVAILABLE'}
                  </b>
                </div>
                {selectedDataset.available === false && (
                  <div className="dv-asset-warning">
                    <AlertTriangle size={13} /> {selectedDataset.unavailableReason || 'Asset files are missing from local storage.'}
                  </div>
                )}
              </div>
            )}

            <button
              type="button"
              className="auth-submit dv-action-submit"
              disabled={busy || !selectedDatasetId || selectedDataset?.available === false}
              onClick={validateRegisteredDataset}
            >
              {busy ? (
                <><Loader2 size={14} className="spin" /> VALIDATING REGISTERED DATASET…</>
              ) : selectedDataset?.available === false ? (
                <><AlertTriangle size={14} /> DATASET MISSING LOCALLY</>
              ) : (
                <><ShieldCheck size={14} /> VALIDATE REGISTERED DATASET</>
              )}
            </button>
          </div>
        ) : (
          <div className="dv-pane dv-upload-pane">
            <div className="dv-contributor-row">
              <label className="dv-field-label">PROVIDED BY *</label>
              <select
                className="dv-contributor-select"
                value={contributorId}
                onChange={(e) => setContributorId(e.target.value)}
                disabled={busy}
              >
                <option value="">SELECT CONTRIBUTOR / VENDOR</option>
                {contributors.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              <span className="dv-field-help">Select the contributor / vendor who provided this dataset.</span>
            </div>

            <div
              className={`dv-upload-action-box ${dragOver ? 'drag-over' : ''} ${busy ? 'busy' : ''}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => {
                if (!busy && contributorId) {
                  setPickerOpen((v) => !v);
                }
              }}
            >
              <div className="dv-upload-icon-wrap">
                {busy ? <Loader2 size={24} className="spin" /> : <UploadCloud size={24} />}
              </div>

              <div className="dv-upload-btn-wrap" ref={pickerRef} onClick={(e) => e.stopPropagation()}>
                <button
                  type="button"
                  className="auth-submit dv-single-upload-btn"
                  disabled={busy || !contributorId}
                  onClick={() => setPickerOpen((v) => !v)}
                >
                  {busy ? (
                    <><Loader2 size={14} className="spin" /> VALIDATING DATASET…</>
                  ) : (
                    <><UploadCloud size={14} /> Upload Dataset</>
                  )}
                </button>

                {pickerOpen && !busy && (
                  <div className="dv-picker-popover anim-scale-up">
                    <div className="dv-picker-popover-title">SELECT DATASET SOURCE</div>
                    <button
                      type="button"
                      className="dv-picker-option"
                      onClick={() => {
                        setPickerOpen(false);
                        folderInputRef.current?.click();
                      }}
                    >
                      <FolderOpen size={16} className="dv-picker-icon" />
                      <div className="dv-picker-text">
                        <strong>Complete Dataset Folder</strong>
                        <span>Upload directory with images & annotations</span>
                      </div>
                    </button>
                    <button
                      type="button"
                      className="dv-picker-option"
                      onClick={() => {
                        setPickerOpen(false);
                        inputRef.current?.click();
                      }}
                    >
                      <FileCode size={16} className="dv-picker-icon" />
                      <div className="dv-picker-text">
                        <strong>Dataset File(s)</strong>
                        <span>Select annotation or image files</span>
                      </div>
                    </button>
                  </div>
                )}
              </div>

              <span className="dv-upload-hint">
                {busy
                  ? 'Dataset submitted to the Data Integrity validation pipeline…'
                  : 'Select dataset file or complete dataset folder, or drop here'}
              </span>
              <span className="dv-upload-meta mono">
                COCO / YOLO FORMATS · IMAGES & ANNOTATIONS · FOLDER STRUCTURE PRESERVED
              </span>
            </div>

            <input
              ref={inputRef}
              type="file"
              multiple
              accept=".json,.txt,.yaml,.yml,.jpg,.jpeg,.png,.webp,.bmp"
              hidden
              onChange={(e) => handleFilesSelected(e.target.files)}
            />
            <input
              ref={folderInputRef}
              type="file"
              multiple
              hidden
              webkitdirectory=""
              directory=""
              onChange={(e) => handleFilesSelected(e.target.files)}
            />

            {precheck.length > 0 && (
              <div className="dv-precheck">
                {precheck.map((p) => (
                  <div key={p.name} className={`dv-pre-row ${p.ok ? 'ok' : 'bad'}`}>
                    {p.ok ? <CheckCircle2 size={12} /> : <Ban size={12} />}
                    <span className="dv-pre-name" title={p.name}>{p.name}</span>
                    <span className="dv-pre-size mono">{fmtBytes(p.size)}</span>
                    <span className="dv-pre-msg">{p.ok ? 'ready' : p.reason}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </GlassCard>

      {/* ---- Step 2: INTEGRITY REPORT ---- */}
      <GlassCard className="dv-report">
        <div className="card-header">
          <h3>02 · INTEGRITY REPORT</h3>
          {report && (
            <StatusBadge
              status={report.status === 'warning' ? 'WARNING' : report.status === 'valid' ? 'PASS' : report.status === 'invalid' ? 'FAILED' : 'REJECTED'}
            />
          )}
        </div>

        {!report && !busy && (
          <div className="dv-empty">SELECT A REGISTERED DATASET OR UPLOAD A NEW ONE TO RUN VALIDATION</div>
        )}
        {busy && (
          <div className="dv-progress mono">
            <span className="auth-boot-dot" /> RUNNING SCHEMA · ANNOTATION · DUPLICATE · OOD · LABEL-FLIP CHECKS…
          </div>
        )}

        {report && !busy && (
          <div className="dv-report-body">
            <div className={`dv-verdict v-${meta.cls}`}>
              <span className="dv-verdict-label">STATUS</span>
              <span className="dv-verdict-val">{meta.label}</span>
              <span className="dv-verdict-format">{String(report.format || '').toUpperCase()}</span>
              {(report.datasetName || report.datasetId) && (
                <span className="dv-verdict-model mono" title={report.datasetId || ''}>
                  DATASET: {report.datasetName || report.datasetId}
                </span>
              )}
              <span className="dv-verdict-counts">
                {report.files_processed} file(s) · {report.errors || 0} error(s) · {report.warnings || 0} warning(s)
              </span>
            </div>

            {report.status === 'rejected' && (
              <div className="dv-callout dv-callout-reject">
                <Ban size={14} />
                <div>
                  <b>{report.error || 'Unsupported file format'}</b>
                  <div className="dv-callout-sub">{report.details || 'The upload was rejected before processing.'}</div>
                  {report.rejected_files?.length > 0 && (
                    <div className="dv-callout-sub mono">REJECTED: {report.rejected_files.join(', ')}</div>
                  )}
                  <div className="dv-callout-sub mono">ALLOWED: {(report.allowed_formats || []).join(' · ')}</div>
                </div>
              </div>
            )}

            {statRows.length > 0 && (report.status !== 'rejected') && (
              <div className="dv-stats">
                {statRows.map(([k, v]) => (
                  <div key={k} className="dv-stat">
                    <span className="dv-stat-k">{k}</span>
                    <span className="dv-stat-v mono">{v}</span>
                  </div>
                ))}
              </div>
            )}

            {(report.error_details?.length > 0) && (
              <div className="dv-issues">
                <div className="dv-issues-title"><XCircle size={12} /> ERRORS ({report.error_details.length})</div>
                {report.error_details.map((e, i) => (
                  <div key={i} className="dv-issue dv-issue-err">
                    <span className="dv-issue-type mono">{e.type}</span>
                    <span className="dv-issue-file mono">{e.file}</span>
                    <span className="dv-issue-msg">{e.message}</span>
                  </div>
                ))}
              </div>
            )}

            {(report.warning_details?.length > 0) && (
              <div className="dv-issues">
                <div className="dv-issues-title warn"><AlertTriangle size={12} /> WARNINGS ({report.warning_details.length})</div>
                {report.warning_details.map((w, i) => (
                  <div key={i} className="dv-issue dv-issue-warn">
                    <span className="dv-issue-type mono">{w.type}</span>
                    <span className="dv-issue-file mono">{w.file}</span>
                    <span className="dv-issue-msg">{w.message}</span>
                  </div>
                ))}
              </div>
            )}

            {report.engine && (
              <div className={`dv-callout ${report.engine.status === 'COMPLETED' ? 'dv-callout-ok' : 'dv-callout-reject'}`}>
                {report.engine.status === 'COMPLETED' ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                <div>
                  <b>DATA INTEGRITY ASSURANCE: {report.engine.status}</b>
                  <div className="dv-callout-sub mono">
                    {report.engine.imagesPresentedToEngine || 0} annotated image(s) evaluated by the local assurance profile
                  </div>
                  {report.engine.output && (
                    <div className="dv-callout-sub mono">
                      VERDICT: {report.engine.output.verdict || '—'} · FLAGS: {report.engine.output.images_flagged ?? '—'} · CHECKS: {(report.engine.output.checks_run || []).join(', ') || 'duplicate, ood, label_flip'}
                      {report.engine.output.dataset_name && ` · DATASET: ${report.engine.output.dataset_name}`}
                    </div>
                  )}
                  {report.engine.stderr && report.engine.status !== 'COMPLETED' && (
                    <pre className="dv-engine-log">{report.engine.stderr.slice(-3000)}</pre>
                  )}
                </div>
              </div>
            )}

            {report.status === 'valid' && (
              <div className="dv-callout dv-callout-ok">
                <CheckCircle2 size={14} />
                <span>All structural, annotation and cross-reference checks passed. The dataset is cleared for downstream model testing.</span>
              </div>
            )}
          </div>
        )}
      </GlassCard>

      {/* ---- Step 3: VALIDATED FILES HISTORY ---- */}
      <GlassCard className="dv-history">
        <div className="card-header">
          <h3>03 · VALIDATED FILES</h3>
          <button className="hud-btn icon-only" onClick={refreshHistory} title="Refresh">
            <RefreshCw size={13} />
          </button>
        </div>
        <DataTable
          columns={[
            { key: 'validationId', label: 'ID', render: (r) => <span className="mono dv-hid">{r.validationId}</span> },
            { key: 'format', label: 'Format', render: (r) => <span className="mono">{r.format}</span> },
            { key: 'filename', label: 'File' },
            { key: 'contributorName', label: 'Contributor', render: (r) => <span className="dv-contributor-badge">{r.contributorName || 'Unassigned'}</span> },
            { key: 'datasetName', label: 'Dataset', render: (r) => <span className="mono">{r.datasetName || r.datasetId || '—'}</span> },
            { key: 'sizeBytes', label: 'Size', render: (r) => fmtBytes(r.sizeBytes) },
            { key: 'sha256', label: 'SHA-256', render: (r) => <span className="hash-chip" title={r.sha256}>{r.sha256?.slice(0, 12)}…</span> },
            { key: 'status', label: 'Verdict', render: (r) => <StatusBadge status={r.status === 'valid' ? 'PASS' : r.status === 'warning' ? 'WARNING' : 'FAIL'} /> },
            { key: 'timestamp', label: 'Time', render: (r) => fmtTime(r.timestamp) }
          ]}
          rows={history}
          emptyMessage="NO VALIDATED DATASET FILES YET"
        />
      </GlassCard>
    </div>
  );
}
