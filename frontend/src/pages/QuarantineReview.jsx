import { useCallback, useEffect, useState } from 'react';
import {
  RefreshCw, ShieldCheck, ShieldX, Clock, Send, Unlock, Loader2
} from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { StatusBadge, SeverityBadge } from '../components/Badges';
import {
  listQuarantine, getQuarantineDetail, decideQuarantine, releaseQuarantine, commitQuarantineToLedger
} from '../services/workflowApi';
import './AuditorPages.css';

const DECISIONS = [
  { key: 'APPROVE', icon: ShieldCheck, cls: 'ok' },
  { key: 'REJECT', icon: ShieldX, cls: 'crit' },
  { key: 'KEEP_QUARANTINED', icon: Clock, cls: 'warn' },
  { key: 'REQUEST_RETEST', icon: Send, cls: 'info' }
];

/**
 * QuarantineReview — auditor governance console for quarantined tests.
 * Full record inspection → APPROVE / REJECT / KEEP / RE-TEST → release / ledger commit.
 */
export default function QuarantineReview({ notify }) {
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState('');
  const [selected, setSelected] = useState(null); // full detail
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (s = status) => {
    setLoading(true);
    try {
      setRows(await listQuarantine(s || null));
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setLoading(false);
    }
  }, [status, notify]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function openDetail(id) {
    try {
      setSelected(await getQuarantineDetail(id));
    } catch (err) {
      notify?.(err.message, 'error');
    }
  }

  async function act(fn, okMsg) {
    if (!selected) return;
    setBusy(true);
    try {
      await fn();
      notify?.(okMsg, 'success');
      await refresh();
      await openDetail(selected.quarantine.quarantineId);
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  const q = selected?.quarantine;
  const t = selected?.test;

  return (
    <div className="anim-fade qr-grid">
      {/* ---- Record list ---- */}
      <GlassCard className="qr-list">
        <div className="card-header">
          <h3>QUARANTINE REVIEW QUEUE</h3>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <select
              className="qr-filter mono"
              value={status}
              onChange={(e) => { setStatus(e.target.value); refresh(e.target.value); }}
            >
              <option value="">ALL STATUSES</option>
              {['QUARANTINED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'RELEASED', 'COMMITTED'].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <button className="hud-btn icon-only" onClick={() => refresh()} title="Refresh">
              <RefreshCw size={13} />
            </button>
          </div>
        </div>
        <div className="qr-rows">
          {rows.map((r) => (
            <button
              key={r.quarantineId}
              className={`qr-row ${q?.quarantineId === r.quarantineId ? 'active' : ''}`}
              onClick={() => openDetail(r.quarantineId)}
            >
              <span className="mono qr-id">{r.quarantineId}</span>
              <span className="qr-test mono">{r.testId}</span>
              <span className="qr-user">{r.userName || r.userId}</span>
              <StatusBadge status={r.status} />
            </button>
          ))}
          {!loading && rows.length === 0 && (
            <div className="aw-empty">NO QUARANTINE RECORDS{status ? ` WITH STATUS ${status}` : ''}</div>
          )}
          {loading && <div className="aw-empty">LOADING…</div>}
        </div>
      </GlassCard>

      {/* ---- Detail / decision console ---- */}
      <GlassCard className="qr-detail">
        {!selected && <div className="aw-empty qr-placeholder">SELECT A RECORD TO REVIEW</div>}
        {selected && q && (
          <>
            <div className="card-header">
              <h3>RECORD {q.quarantineId}</h3>
              <StatusBadge status={q.status} />
            </div>

            {/* Metadata */}
            <div className="qr-meta">
              <div><span>TEST</span><b className="mono">{q.testId}</b></div>
              <div><span>ANALYST</span><b>{q.userName || q.userId}</b></div>
              <div><span>DATASET</span><b className="mono">{q.datasetName || q.datasetId || '—'}</b></div>
              <div><span>MODEL</span><b className="mono">{q.modelName || q.modelId || '—'}</b></div>
              <div><span>SEVERITY</span><b>{q.severity || '—'}</b></div>
              <div><span>CONFIDENCE</span><b>{q.confidence ?? '—'}</b></div>
              <div><span>EVIDENCE HASH</span><b className="mono">{q.evidenceHash ? `#${String(q.evidenceHash).slice(0, 16)}…` : '—'}</b></div>
              <div><span>CREATED</span><b>{q.createdAt ? new Date(q.createdAt).toLocaleString() : '—'}</b></div>
            </div>

            {q.reason && (
              <div className="qr-reason">
                <span>REPORTED REASON</span>
                <p>{q.reason}</p>
              </div>
            )}

            {/* Algorithm results from the underlying test (unchanged outputs) */}
            {t?.checks && (
              <div className="qr-checks">
                <span className="qr-sub">UNDERLYING TEST RESULTS · EXISTING MODULE OUTPUTS</span>
                {Object.entries(t.checks).map(([k, v]) => (
                  <div key={k} className={`aw-check st-${(v.status || '').toLowerCase()}`}>
                    <span className="aw-check-name">{k.replaceAll('_', ' ')}</span>
                    <span className="aw-check-status">{v.status}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Timeline */}
            {(q.timeline || []).length > 0 && (
              <div className="qr-timeline">
                <span className="qr-sub">TIMELINE</span>
                {(q.timeline || []).map((ev, i) => (
                  <div key={i} className="qr-tl-row">
                    <span className="mono qr-tl-time">{new Date(ev.at).toLocaleTimeString()}</span>
                    <span className="qr-tl-what">{ev.action}{ev.actor ? ` · ${ev.actor}` : ''}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Actions */}
            <div className="qr-actions">
              {DECISIONS.map(({ key, icon: Icon, cls }) => (
                <button
                  key={key}
                  className={`qr-act ${cls}`}
                  disabled={busy}
                  onClick={() => act(() => decideQuarantine(q.quarantineId, key), `Decision ${key} recorded.`)}
                >
                  <Icon size={13} /> {key.replaceAll('_', ' ')}
                </button>
              ))}
              {q.status === 'APPROVED' && (
                <button
                  className="qr-act info"
                  disabled={busy}
                  onClick={() => act(() => releaseQuarantine(q.quarantineId), 'Record released.')}
                >
                  <Unlock size={13} /> RELEASE
                </button>
              )}
              {q.status === 'APPROVED' && (
                <button
                  className="qr-act ledger"
                  disabled={busy}
                  onClick={() => act(() => commitQuarantineToLedger(q.quarantineId), 'Committed to Hyperledger Fabric.')}
                >
                  <Loader2 size={13} className={busy ? 'spin' : ''} /> COMMIT TO LEDGER
                </button>
              )}
            </div>
          </>
        )}
      </GlassCard>
    </div>
  );
}
