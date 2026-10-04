import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Loader2, CheckCircle2, XCircle, AlertTriangle,
  Ban, RefreshCw, UploadCloud
} from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { StatusBadge } from '../components/Badges';
import DataTable from '../components/DataTable';
import {
  clientValidateFile, uploadAndValidateDataset, listDatasetValidations,
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
 * Presents ONE single upload option: [ Upload Dataset ]
 * Automatically detects dataset structure and submits directly to the
 * backend Data Integrity pipeline.
 */
export default function DatasetValidation({ notify }) {
  const [kind, setKind] = useState('yolo');
  const [files, setFiles] = useState([]);
  const [precheck, setPrecheck] = useState([]);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState([]);
  const [contributors, setContributors] = useState([]);
  const [contributorId, setContributorId] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await listDatasetValidations());
    } catch {
      /* history is non-critical UI */
    }
  }, []);

  useEffect(() => {
    refreshHistory();
    listContributors()
      .then((list) => {
        setContributors(list);
        if (list && list.length > 0) {
          setContributorId(list[0].id);
        }
      })
      .catch(() => setContributors([]));
  }, [refreshHistory]);

  async function handleFilesSelected(pickedList) {
    const picked = Array.from(pickedList || []);
    if (!picked.length) return;

    if (!contributorId) {
      notify?.('Select the contributor / vendor who provided this dataset.', 'error');
      return;
    }

    setFiles(picked);
    setReport(null);

    // Auto-detect format: JSON annotation indicates COCO, otherwise YOLO
    const detectedKind = picked.some((f) => f.name.toLowerCase().endsWith('.json')) ? 'coco' : 'yolo';
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
    } catch (err) {
      notify?.(err.message || 'Dataset validation failed', 'error');
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
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

  const meta = report ? reportMeta(report.status) : null;
  const stats = report?.stats || {};

  const statRows = [
    ...(report?.datasetName ? [['Dataset', report.datasetName]] : []),
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
      {/* ---- Step 1: UNIFIED UPLOAD DATASET ---- */}
      <GlassCard className="dv-upload">
        <div className="card-header">
          <h3>01 · DATA VALIDATION</h3>
          <span className="text-muted" style={{ fontSize: 10 }}>DATA INTEGRITY PIPELINE</span>
          <span className="hdr-meta">{kind.toUpperCase()} PIPELINE</span>
        </div>

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

        {/* Single Primary Action: Upload Dataset */}
        <div
          className={`dv-upload-action-box ${dragOver ? 'drag-over' : ''} ${busy ? 'busy' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => !busy && inputRef.current?.click()}
        >
          <div className="dv-upload-icon-wrap">
            {busy ? <Loader2 size={24} className="spin" /> : <UploadCloud size={24} />}
          </div>

          <button
            type="button"
            className="auth-submit dv-single-upload-btn"
            disabled={busy || !contributorId}
            onClick={(e) => {
              e.stopPropagation();
              if (!busy && contributorId) inputRef.current?.click();
            }}
          >
            {busy ? (
              <><Loader2 size={14} className="spin" /> VALIDATING DATASET…</>
            ) : (
              <><UploadCloud size={14} /> Upload Dataset</>
            )}
          </button>

          <span className="dv-upload-hint">
            {busy
              ? 'Dataset submitted to the Data Integrity validation pipeline…'
              : 'Select dataset or drop folder/files to validate'}
          </span>
          <span className="dv-upload-meta mono">
            COCO / YOLO FORMATS · IMAGES & ANNOTATIONS · CHECKS DUPLICATE, OOD & LABEL-FLIPS
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
          <div className="dv-empty">SELECT CONTRIBUTOR, CLICK UPLOAD DATASET, AND VIEW REAL-TIME INTEGRITY VERDICTS</div>
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
