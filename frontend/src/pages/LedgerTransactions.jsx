import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { StatusBadge } from '../components/Badges';
import { listLedgerTransactions } from '../services/workflowApi';
import './AuditorPages.css';

/**
 * LedgerTransactions — auditor view of Fabric ledger commitments (task spec §23).
 * Transaction IDs, finding IDs, evidence hashes, commit status.
 */
export default function LedgerTransactions({ notify }) {
  const [txs, setTxs] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setTxs(await listLedgerTransactions());
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="anim-fade">
      <GlassCard>
        <div className="card-header">
          <h3>FABRIC LEDGER · COMMITTED FINDINGS</h3>
          <button className="hud-btn icon-only" onClick={refresh} title="Refresh">
            <RefreshCw size={13} />
          </button>
        </div>
        <div className="aud-table-wrap">
          <table className="aud-table">
            <thead>
              <tr>
                <th>Transaction ID</th>
                <th>Finding / Test</th>
                <th>Evidence Hash</th>
                <th>Auditor</th>
                <th>Timestamp</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {txs.map((t) => (
                <tr key={t.txId || t._id}>
                  <td className="mono" title={t.txId}>{t.txId ? `${String(t.txId).slice(0, 18)}…` : '—'}</td>
                  <td className="mono">{t.testId || t.findingId || t.quarantineId || '—'}</td>
                  <td className="mono" title={t.evidenceHash}>{t.evidenceHash ? `#${String(t.evidenceHash).slice(0, 16)}…` : '—'}</td>
                  <td>{t.auditorName || '—'}</td>
                  <td className="mono">{t.timestamp || t.createdAt ? new Date(t.timestamp || t.createdAt).toLocaleString() : '—'}</td>
                  <td><StatusBadge status={t.status || 'COMMITTED'} /></td>
                </tr>
              ))}
              {!loading && txs.length === 0 && (
                <tr><td colSpan={6} className="aw-empty">NO LEDGER TRANSACTIONS — COMMIT APPROVED RECORDS FROM QUARANTINE REVIEW</td></tr>
              )}
              {loading && <tr><td colSpan={6} className="aw-empty">LOADING…</td></tr>}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );
}
