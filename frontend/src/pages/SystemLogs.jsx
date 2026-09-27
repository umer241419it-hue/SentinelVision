import { useCallback, useEffect, useState } from 'react';
import { Download, RefreshCw, FileText } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { listAuditLogs } from '../services/workflowApi';
import './AuditorPages.css';

/**
 * SystemLogs — auditor-only audit trail (task spec §25).
 * Timestamp / actor / role / action / resource / result / device metadata.
 */
export default function SystemLogs({ notify }) {
  const [logs, setLogs] = useState([]);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setLogs(await listAuditLogs());
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const shown = filter
    ? logs.filter((l) =>
        [l.action, l.actorName, l.actorRole, l.resourceType, l.result]
          .filter(Boolean)
          .some((v) => String(v).toLowerCase().includes(filter.toLowerCase()))
      )
    : logs;

  return (
    <div className="anim-fade">
      <GlassCard>
        <div className="card-header">
          <h3>SYSTEM LOGS · AUDIT TRAIL</h3>
          <div className="aud-toolbar">
            <input
              className="qr-filter"
              style={{ height: 28, padding: '0 10px', width: 220 }}
              placeholder="FILTER ACTIONS / USERS…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <button className="hud-btn icon-only" onClick={refresh} title="Refresh">
              <RefreshCw size={13} />
            </button>
            <span className="hdr-meta">{shown.length} ENTRIES</span>
          </div>
        </div>
        <div className="aud-table-wrap">
          <table className="aud-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Actor</th>
                <th>Role</th>
                <th>Action</th>
                <th>Resource</th>
                <th>Result</th>
                <th>IP / Device</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((l) => (
                <tr key={l._id || `${l.timestamp}-${l.action}-${l.resourceId}`}>
                  <td className="mono">{l.timestamp ? new Date(l.timestamp).toLocaleString() : '—'}</td>
                  <td>{l.actorName || 'SYSTEM'}</td>
                  <td className="mono">{l.actorRole || '—'}</td>
                  <td className="mono">{l.action}</td>
                  <td className="mono">
                    {l.resourceType}
                    {l.resourceId ? ` · ${String(l.resourceId).slice(0, 18)}` : ''}
                  </td>
                  <td>
                    <span className={`qr-act ${l.result === 'FAILURE' ? 'crit' : 'ok'}`} style={{ padding: '2px 8px', pointerEvents: 'none' }}>
                      {l.result || 'SUCCESS'}
                    </span>
                  </td>
                  <td className="mono" title={l.userAgent}>{l.ip || '—'}</td>
                </tr>
              ))}
              {!loading && shown.length === 0 && (
                <tr><td colSpan={7} className="aw-empty">NO LOG ENTRIES</td></tr>
              )}
              {loading && <tr><td colSpan={7} className="aw-empty">LOADING…</td></tr>}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );
}
