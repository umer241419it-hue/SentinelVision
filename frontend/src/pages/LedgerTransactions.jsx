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
  const [activeTab, setActiveTab] = useState('chain');
  const [txs, setTxs] = useState([]);
  const [journal, setJournal] = useState([]);
  const [info, setInfo] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedTx, setSelectedTx] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listLedgerTransactions();
      const transactions = Array.isArray(res) ? res : (res.transactions || []);
      const localJournal = res.journal || [];
      setTxs(transactions);
      setJournal(localJournal);
      setInfo(res.info || {});
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const isOffline = info.networkStatus === 'OFFLINE' || info.connected === false;

  return (
    <div className="anim-fade">
      <GlassCard>
        <div className="card-header" style={{ flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <h3>FABRIC LEDGER & AUDIT JOURNAL</h3>
            <span className={`tb-pill ${isOffline ? 'pending' : 'ok'}`} style={{ fontSize: 10 }}>
              <span className={`status-dot ${isOffline ? 'pending' : 'ok'}`} />
              Fabric {info.networkStatus || 'OFFLINE'}
            </span>
          </div>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 4, background: 'var(--surface-0)', padding: '3px', borderRadius: 6, border: '1px solid var(--border-medium)' }}>
              <button
                className={`hud-btn small ${activeTab === 'chain' ? 'primary' : ''}`}
                onClick={() => setActiveTab('chain')}
                style={{ fontSize: 11, padding: '3px 10px', height: 'auto', border: 'none' }}
              >
                On-Chain Ledger ({txs.length})
              </button>
              <button
                className={`hud-btn small ${activeTab === 'journal' ? 'primary' : ''}`}
                onClick={() => setActiveTab('journal')}
                style={{ fontSize: 11, padding: '3px 10px', height: 'auto', border: 'none' }}
              >
                Local Submission Journal ({journal.length})
              </button>
            </div>
            <button className="hud-btn icon-only" onClick={refresh} title="Refresh">
              <RefreshCw size={13} />
            </button>
          </div>
        </div>

        {activeTab === 'chain' ? (
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
                    key={t.txId || t.journalId || t._id}
                    onClick={() => setSelectedTx({ ...t, _category: 'On-Chain Fabric Transaction' })}
                    style={{ cursor: 'pointer' }}
                    title="Click to view transaction details"
                  >
                    <td className="mono" title={t.txId}>
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
                    <td><StatusBadge status={t.status || 'COMMITTED'} /></td>
                  </tr>
                ))}
                {!loading && txs.length === 0 && (
                  <tr>
                    <td colSpan={7} className="aw-empty">
                      {isOffline
                        ? 'No on-chain ledger transactions available. Hyperledger Fabric network is offline.'
                        : 'No on-chain ledger transactions available.'}
                    </td>
                  </tr>
                )}
                {loading && <tr><td colSpan={7} className="aw-empty">LOADING…</td></tr>}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="aud-table-wrap">
            <table className="aud-table">
              <thead>
                <tr>
                  <th>Journal ID</th>
                  <th>Target Asset</th>
                  <th>Module</th>
                  <th>Evidence Hash</th>
                  <th>Dispatch Status</th>
                  <th>Attempted At</th>
                  <th>Error / Outcome</th>
                </tr>
              </thead>
              <tbody>
                {journal.map((j) => (
                  <tr
                    key={j.journalId}
                    onClick={() => setSelectedTx({ ...j, _category: 'Local Submission Journal Entry' })}
                    style={{ cursor: 'pointer' }}
                    title="Click to view journal record"
                  >
                    <td className="mono" style={{ color: 'var(--accent-cyan)' }}>{j.journalId}</td>
                    <td className="mono">{j.ledgerKey || j.assetId || '—'}</td>
                    <td>{j.moduleName || 'Governance'}</td>
                    <td className="mono" title={j.evidenceHash || ''}>
                      {j.evidenceHash ? `#${String(j.evidenceHash).slice(0, 16)}…` : <span className="text-muted">Not available</span>}
                    </td>
                    <td><StatusBadge status={j.status} /></td>
                    <td className="mono">
                      {j.attemptedAt ? new Date(j.attemptedAt).toLocaleString() : '—'}
                    </td>
                    <td style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={j.error || 'Committed on-chain'}>
                      {j.error ? <span style={{ color: '#f87171' }}>{j.error}</span> : <span style={{ color: '#34d399' }}>Recorded</span>}
                    </td>
                  </tr>
                ))}
                {!loading && journal.length === 0 && (
                  <tr><td colSpan={7} className="aw-empty">No local journal entries recorded.</td></tr>
                )}
                {loading && <tr><td colSpan={7} className="aw-empty">LOADING…</td></tr>}
              </tbody>
            </table>
          </div>
        )}
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
                  {selectedTx._category || (selectedTx.txId ? `TX: ${selectedTx.txId}` : 'Record Detail')}
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
                  <span className="tx-k" style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Record Type</span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent-cyan)' }}>
                    {selectedTx._category || (selectedTx.txId ? 'On-Chain Fabric Transaction' : 'Local Submission Journal Entry')}
                  </span>
                </div>
                <div className="tx-field">
                  <span className="tx-k" style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Transaction ID</span>
                  <span className="mono" style={{ fontSize: 12, wordBreak: 'break-all', color: selectedTx.txId ? 'var(--accent-cyan)' : 'var(--text-muted)' }}>
                    {selectedTx.txId || 'Not available (pre-chain / Fabric offline)'}
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
