import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, X, Link2, ShieldCheck, Database, Layers, Hash, Clock, User, AlertCircle } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { StatusBadge } from '../components/Badges';
import { listLedgerTransactions } from '../services/workflowApi';
import './AuditorPages.css';

/**
 * LedgerTransactions — auditor view of Fabric ledger commitments.
 * Displays authoritative transaction journal entries with interactive detail inspection.
 */
export default function LedgerTransactions({ notify }) {
  const [txs, setTxs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTx, setSelectedTx] = useState(null);

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
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <span className="hdr-meta">{txs.length} TRANSACTIONS</span>
            <button className="hud-btn icon-only" onClick={refresh} title="Refresh">
              <RefreshCw size={13} />
            </button>
          </div>
        </div>
        <div className="aud-table-wrap">
          <table className="aud-table">
            <thead>
              <tr>
                <th>Transaction ID</th>
                <th>Finding / Test</th>
                <th>Asset / Module</th>
                <th>Evidence Hash</th>
                <th>Auditor</th>
                <th>Timestamp</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {txs.map((t) => (
                <tr
                  key={t.journalId || t.txId || t._id}
                  onClick={() => setSelectedTx(t)}
                  style={{ cursor: 'pointer' }}
                  title="Click to view transaction details"
                >
                  <td className="mono" title={t.txId || 'Pending commit'}>
                    {t.txId ? `${String(t.txId).slice(0, 18)}…` : <span className="text-muted">Not available</span>}
                  </td>
                  <td className="mono">{t.testId || t.findingId || t.quarantineId || '—'}</td>
                  <td>{t.assetId || t.assetID || t.moduleName || '—'}</td>
                  <td className="mono" title={t.evidenceHash || ''}>
                    {t.evidenceHash ? `#${String(t.evidenceHash).slice(0, 16)}…` : <span className="text-muted">Not available</span>}
                  </td>
                  <td>{t.auditorName || t.actor || '—'}</td>
                  <td className="mono">
                    {t.timestamp || t.attemptedAt || t.createdAt
                      ? new Date(t.timestamp || t.attemptedAt || t.createdAt).toLocaleString()
                      : '—'}
                  </td>
                  <td><StatusBadge status={t.status || 'RECORDED'} /></td>
                </tr>
              ))}
              {!loading && txs.length === 0 && (
                <tr><td colSpan={7} className="aw-empty">No ledger transactions available.</td></tr>
              )}
              {loading && <tr><td colSpan={7} className="aw-empty">LOADING…</td></tr>}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {/* Transaction Detail Modal */}
      {selectedTx && (
        <div
          className="report-viewer-overlay"
          role="dialog"
          aria-modal="true"
          onClick={(e) => { if (e.target === e.currentTarget) setSelectedTx(null); }}
        >
          <div className="report-viewer" style={{ maxWidth: 800, height: 'auto', maxHeight: '85vh' }}>
            <div className="report-viewer-header">
              <div className="report-viewer-header-info">
                <Link2 size={16} className="hdr-icon" />
                <span className="report-viewer-title">
                  {selectedTx.txId ? `TX: ${selectedTx.txId}` : 'Transaction Detail'}
                </span>
                <StatusBadge status={selectedTx.status || 'RECORDED'} />
              </div>
              <button className="qr-act" onClick={() => setSelectedTx(null)} title="Close">
                <X size={15} /> CLOSE
              </button>
            </div>
            <div style={{ padding: 24, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
                <div className="tx-field">
                  <span className="tx-k" style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Transaction ID</span>
                  <span className="mono" style={{ fontSize: 12, wordBreak: 'break-all', color: 'var(--accent-cyan)' }}>
                    {selectedTx.txId || 'Not available (offline/pending commit)'}
                  </span>
                </div>
                <div className="tx-field">
                  <span className="tx-k" style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Finding / Test ID</span>
                  <span className="mono" style={{ fontSize: 12 }}>
                    {selectedTx.testId || selectedTx.findingId || selectedTx.quarantineId || 'Not available'}
                  </span>
                </div>
                <div className="tx-field">
                  <span className="tx-k" style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Asset / Target</span>
                  <span className="mono" style={{ fontSize: 12 }}>
                    {selectedTx.assetId || selectedTx.assetID || selectedTx.ledgerKey || 'Not available'}
                  </span>
                </div>
                <div className="tx-field">
                  <span className="tx-k" style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Module</span>
                  <span style={{ fontSize: 12 }}>
                    {selectedTx.moduleName || 'Governance'}
                  </span>
                </div>
                <div className="tx-field">
                  <span className="tx-k" style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Contributor / Vendor</span>
                  <span style={{ fontSize: 12 }}>
                    {selectedTx.contributorName || selectedTx.contributorId || 'Not available'}
                  </span>
                </div>
                <div className="tx-field">
                  <span className="tx-k" style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Auditor / Operator</span>
                  <span style={{ fontSize: 12 }}>
                    {selectedTx.auditorName || selectedTx.actor || 'Not available'}
                  </span>
                </div>
                <div className="tx-field">
                  <span className="tx-k" style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Block Number</span>
                  <span className="mono" style={{ fontSize: 12 }}>
                    {selectedTx.blockNumber || selectedTx.block || 'Not available'}
                  </span>
                </div>
                <div className="tx-field">
                  <span className="tx-k" style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Validation Code</span>
                  <span className="mono" style={{ fontSize: 12 }}>
                    {selectedTx.validationCode || 'Not available'}
                  </span>
                </div>
                <div className="tx-field">
                  <span className="tx-k" style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Channel / Chaincode</span>
                  <span className="mono" style={{ fontSize: 12 }}>
                    {selectedTx.channel || 'mychannel'} / {selectedTx.chaincode || 'basic'}
                  </span>
                </div>
                <div className="tx-field">
                  <span className="tx-k" style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Timestamp</span>
                  <span className="mono" style={{ fontSize: 12 }}>
                    {selectedTx.timestamp || selectedTx.attemptedAt || selectedTx.createdAt
                      ? new Date(selectedTx.timestamp || selectedTx.attemptedAt || selectedTx.createdAt).toLocaleString()
                      : 'Not available'}
                  </span>
                </div>
              </div>

              <div>
                <span style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
                  Evidence Hash (SHA-256)
                </span>
                <div className="mono" style={{ fontSize: 11, background: 'var(--surface-0)', padding: '8px 12px', borderRadius: 4, border: '1px solid var(--border-soft)', wordBreak: 'break-all' }}>
                  {selectedTx.evidenceHash ? `#${selectedTx.evidenceHash}` : 'Not available'}
                </div>
              </div>

              {selectedTx.reason && (
                <div>
                  <span style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: 4 }}>
                    Reason / Finding Statement
                  </span>
                  <p style={{ margin: 0, fontSize: 12, color: 'var(--text-secondary)', background: 'var(--surface-0)', padding: '10px 12px', borderRadius: 4, border: '1px solid var(--border-soft)' }}>
                    {selectedTx.reason}
                  </p>
                </div>
              )}

              {selectedTx.error && (
                <div style={{ background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.25)', borderRadius: 4, padding: '10px 14px', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <AlertCircle size={15} color="#f87171" style={{ flexShrink: 0, marginTop: 2 }} />
                  <div style={{ fontSize: 11.5, color: '#f87171' }}>
                    <strong>Network Notice:</strong> {selectedTx.error}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
