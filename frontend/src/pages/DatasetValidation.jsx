import { useCallback, useEffect, useRef, useState } from 'react';
import {
  FileJson, FileText, FileType2, Loader2, CheckCircle2, XCircle, AlertTriangle,
  Ban, RefreshCw, FileWarning, ShieldCheck, Copy, Package
} from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { StatusBadge } from '../components/Badges';
import DataTable from '../components/DataTable';
import {
  clientValidateFile, uploadAndValidateDataset, listDatasetValidations,
  ALLOWED_EXTENSIONS, KIND_RULES
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
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

/**
 * DatasetValidation — COCO/YOLO dataset integrity gate (upload → validate →
 * report). Client-side checks pre-filter obvious rejects; the bridge is the
 * authoritative server-side validator (task §11). Shows the machine-readable
 * report: errors vs warnings separated, dataset completeness stats, and the
 * history of validated files.
 */
export default function DatasetValidation({ notify }) {
  const [kind, setKind] = useState('yolo');
  const [files, setFiles] = useState([]);
  const [precheck, setPrecheck] = useState([]); // client-side gate results
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState([]);
  const [contributors, setContributors] = useState([]);
  const [contributorId, setContributorId] = useState('');
  const [folderMode, setFolderMode] = useState(false);
  const inputRef = useRef(null);
  const folderInputRef = useRef(null);

  const rules = KIND_RULES[kind];

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await listDatasetValidations());
    } catch {
      /* history is non-critical UI */
    }
  }, []);

  useEffect(() => {
    refreshHistory();
    listContributors().then(setContributors).catch(() => setContributors([]));
  }, [refreshHistory]);

  function pickFiles(fileList, fromFolder = false) {
    const picked = Array.from(fileList || []);
    setFiles(picked);
    setFolderMode(fromFolder);
    setReport(null);
    if (fromFolder) {
      setPrecheck(picked.length
        ? [{ name: `${picked.length} files from selected dataset folder`, size: picked.reduce((n, f) => n + f.size, 0), ok: true, reason: 'server-side folder validation' }]
        : []);
      return;
    }
    Promise.all(
      picked.map(async (f) => ({ name: f.name, size: f.size, ...(await clientValidateFile(f, kind)) }))
    ).then(setPrecheck);
  }

  function switchKind(nextKind) {
    setKind(nextKind);
    setFiles([]);
    setPrecheck([]);
    setFolderMode(false);
    setReport(null);
  }

  async function doValidate() {
    if (files.length === 0) return;
    if (!contributorId) {
      notify?.('Select the contributor who provided this dataset before validation.', 'error');
      return;
    }
    const blocked = folderMode ? [] : precheck.filter((p) => !p.ok);
    if (blocked.length > 0) {
      notify?.(`${blocked.length} file(s) failed client-side checks — remove them before validating.`, 'error');
      return;
    }
    setBusy(true);
    setReport(null);
    try {
      const { report: r } = await uploadAndValidateDataset(kind, files, contributorId);
      setReport(r);
      const meta = reportMeta(r.status);
      notify?.(
        `Dataset validation: ${meta.label} · ${r.files_processed} file(s) · ${r.errors || 0} error(s) · ${r.warnings || 0} warning(s)`,
        r.status === 'valid' || r.status === 'warning' ? 'success' : 'error'
      );
      refreshHistory();
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  const meta = report ? reportMeta(report.status) : null;
  const stats = report?.stats || {};
  const statRows = [
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
      {/* ---- Step 1: UPLOAD + CLIENT GATE ---- */}
      <GlassCard className="dv-upload">
        <div className="card-header">
          <h3>01 · UPLOAD DATASET FILES</h3>
          <span className="hdr-meta">{rules.label.toUpperCase()} · {rules.extensions.join(' · ')}</span>
        </div>

        <div className="dv-contributor-row">
          <label className="dv-field-label">PROVIDED BY *</label>
          <select className="dv-contributor-select" value={contributorId} onChange={(e) => setContributorId(e.target.value)} disabled={busy}>
            <option value="">SELECT CONTRIBUTOR / VENDOR</option>
            {contributors.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <span className="dv-field-help">Select the vendor/contributor that supplied this dataset.</span>
        </div>

        <div className="dv-kind-row">
          <button
            className={`dv-kind ${kind === 'yolo' ? 'active' : ''}`}
            onClick={() => switchKind('yolo')}
            disabled={busy}
          >
            <FileText size={15} /> YOLO
            <span>.txt annotations + .yaml/.yml config</span>
          </button>
          <button
            className={`dv-kind ${kind === 'coco' ? 'active' : ''}`}
            onClick={() => switchKind('coco')}
            disabled={busy}
          >
            <FileJson size={15} /> COCO
            <span>.json annotation export</span>
          </button>
        </div>

        <button className="dv-drop" disabled={busy} onClick={() => inputRef.current?.click()}>
          <Package size={20} />
          <strong>SELECT FILES</strong>
          <span>
            {kind === 'yolo'
              ? 'Annotation .txt files and dataset .yaml/.yml config'
              : 'COCO annotation .json (images / annotations / categories)'}
          </span>
          <span className="dv-allowed mono">ALLOWED: {ALLOWED_EXTENSIONS.join(' · ')} — MAX 20 MB / FILE</span>
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={rules.accept}
          multiple
          hidden
          onChange={(e) => pickFiles(e.target.files)}
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

        <button
          className="auth-submit dv-validate"
          disabled={busy || files.length === 0 || !contributorId || precheck.some((p) => !p.ok)}
          onClick={doValidate}
        >
          {busy
            ? <><Loader2 size={14} className="spin" /> VALIDATING…</>
            : <><ShieldCheck size={14} /> VALIDATE DATASET</>}
        </button>
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
          <div className="dv-empty">SELECT FILES AND RUN VALIDATION — THE BRIDGE PERFORMS THE AUTHORITATIVE CHECKS</div>
        )}
        {busy && (
          <div className="dv-progress mono">
            <span className="auth-boot-dot" /> RUNNING SCHEMA · ANNOTATION · CROSS-REFERENCE · COMPLETENESS CHECKS…
          </div>
        )}

        {report && !busy && (
          <div className="dv-report-body">
            <div className={`dv-verdict v-${meta.cls}`}>
              <span className="dv-verdict-label">STATUS</span>
              <span className="dv-verdict-val">{meta.label}</span>
              <span className="dv-verdict-format">{String(report.format || '').toUpperCase()}</span>
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
