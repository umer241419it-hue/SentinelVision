import { useCallback, useEffect, useState } from 'react';
import { ExternalLink, FileDown, Loader2, X } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { listReports, downloadGovernanceReport } from '../services/workflowApi';
import { BRIDGE_BASE_URL } from '../services/authApi';
import './AuditorPages.css';

export default function GovernanceReports({ notify }) {
  const [reports, setReports] = useState([]);
  const [periodDays, setPeriodDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reportUrl, setReportUrl] = useState(null);
  const [reportTitle, setReportTitle] = useState('Governance Report');
  const [selectedReport, setSelectedReport] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setReports(await listReports());
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function openReport(report) {
    try {
      const token = localStorage.getItem('sv-token');
      const id = encodeURIComponent(report.reportId || report._id || '');
      if (!id) throw new Error('Report identifier is missing');

      const res = await fetch(
        `${BRIDGE_BASE_URL}/api/auditor/reports/${id}/download?view=1`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) throw new Error(`Report open failed: ${res.status}`);

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setReportUrl((old) => {
        if (old) URL.revokeObjectURL(old);
        return url;
      });
      setReportTitle(report.reportId || 'Governance Report');
      setSelectedReport(report);
    } catch (err) {
      notify?.(err.message, 'error');
    }
  }

  function closeReport() {
    setReportUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return null;
    });
    setSelectedReport(null);
  }

  async function download() {
    setBusy(true);
    try {
      await downloadGovernanceReport(periodDays);
      notify?.(`Governance report (${periodDays}d) downloaded.`, 'success');
      await refresh();
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="anim-fade">
      <GlassCard className="rp-card">
        <div className="card-header">
          <h3>GOVERNANCE REPORTS</h3>
          <span className="hdr-meta">PDF · SYSTEM SUMMARY · QUARANTINE · LEDGER · AUDIT TRAIL</span>
        </div>
        <p>
          Generates a real governance report from live system data: totals of tests and findings,
          integrity check outcomes, quarantine decisions with reviewers, ledger transactions with
          evidence hashes, and the audit trail for the selected period. Values are sourced from the
          bridge stores — nothing is fabricated.
        </p>
        <div className="rp-actions">
          <label className="rp-period">
            <span className="qr-sub" style={{ marginBottom: 0 }}>PERIOD</span>
            <select
              className="qr-filter"
              value={periodDays}
              onChange={(e) => setPeriodDays(Number(e.target.value))}
            >
              {[1, 7, 30, 90, 365].map((d) => (
                <option key={d} value={d}>
                  {d === 365 ? 'LAST YEAR' : `LAST ${d} DAY${d > 1 ? 'S' : ''}`}
                </option>
              ))}
            </select>
          </label>
          <button className="qr-act ledger" onClick={download} disabled={busy}>
            {busy ? <Loader2 size={13} className="spin" /> : <FileDown size={13} />}
            DOWNLOAD GOVERNANCE REPORT
          </button>
        </div>
      </GlassCard>

      <GlassCard style={{ marginTop: 14 }}>
        <div className="card-header">
          <h3>PREVIOUSLY GENERATED</h3>
          <span className="hdr-meta">{reports.length} REPORTS</span>
        </div>
        <div className="aud-table-wrap" style={{ maxHeight: 320 }}>
          <table className="aud-table">
            <thead>
              <tr>
                <th>Report ID</th>
                <th>Generated</th>
                <th>Period</th>
                <th>Auditor</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.reportId || r._id}>
                  <td className="mono">{r.reportId || r._id}</td>
                  <td className="mono">{r.generatedAt ? new Date(r.generatedAt).toLocaleString() : '—'}</td>
                  <td>{r.periodDays ? `${r.periodDays} days` : '—'}</td>
                  <td>{r.auditorName || '—'}</td>
                  <td>
                    <button className="qr-act" onClick={() => openReport(r)}>
                      <ExternalLink size={13} />
                      OPEN
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && reports.length === 0 && (
                <tr><td colSpan={5} className="aw-empty">No governance reports have been generated.</td></tr>
              )}
              {loading && <tr><td colSpan={5} className="aw-empty">LOADING…</td></tr>}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {reportUrl && (
        <div
          className="report-viewer-overlay"
          role="dialog"
          aria-modal="true"
          onClick={(e) => { if (e.target === e.currentTarget) closeReport(); }}
        >
          <div className="report-viewer">
            <div className="report-viewer-header">
              <div className="report-viewer-header-info">
                <span className="report-viewer-title">{reportTitle}</span>
                {selectedReport?.generatedAt && (
                  <span className="report-viewer-meta">
                    Generated: {new Date(selectedReport.generatedAt).toLocaleString()}
                  </span>
                )}
                {selectedReport?.periodDays && (
                  <span className="report-viewer-meta">
                    Period: {selectedReport.periodDays}d
                  </span>
                )}
                {selectedReport?.disposition && (
                  <span className={`tb-pill ${selectedReport.disposition === 'ACCEPT' ? 'ok' : 'crit'}`}>
                    {selectedReport.disposition}
                  </span>
                )}
              </div>
              <button className="qr-act" onClick={closeReport} title="Close report">
                <X size={15} />
                CLOSE
              </button>
            </div>
            <iframe
              title={reportTitle}
              src={reportUrl}
              className="report-viewer-frame"
            />
          </div>
        </div>
      )}
    </div>
  );
}
