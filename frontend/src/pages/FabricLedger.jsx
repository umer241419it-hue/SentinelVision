import { useEffect, useState } from 'react';
import { Link2, Boxes, FileLock2, CircleCheck, Layers } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { LedgerVerifiedBadge, StatusBadge } from '../components/Badges';
import { getLedgerTransactions } from '../services/api';
import './FabricLedger.css';

function fmtTime(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
}

export default function FabricLedger() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getLedgerTransactions()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return (
      <div className="page-loading">
        <div className="spinner" /> Loading ledger…
      </div>
    );
  if (error)
    return (
      <div className="page-error">
        <FileLock2 size={18} /> {error}
      </div>
    );

  const { info, transactions } = data;

  const netStats = [
    { icon: Layers, label: 'Channel', value: info.channel },
    { icon: Boxes, label: 'Chaincode', value: info.chaincode },
    { icon: Link2, label: 'Latest Block', value: info.latestBlock && info.latestBlock !== '—' ? `#${info.latestBlock}` : '—' },
    { icon: CircleCheck, label: 'Committed Findings', value: info.totalFindings }
  ];

  const isConnected = info.networkStatus === 'CONNECTED';

  return (
    <div className="anim-fade">
      {/* Network status header */}
      <GlassCard className="fl-header" glow="violet">
        <div className="fl-header-left">
          <div className="fl-net-badge">
            <Link2 size={20} strokeWidth={1.9} />
          </div>
          <div>
            <h2 className="fl-title">Immutable Audit Ledger</h2>
            <p className="fl-sub">
              Every security finding is committed to Hyperledger Fabric as a tamper-proof
              transaction — {info.organization} · {info.node}
            </p>
          </div>
        </div>
        <div className="fl-header-right">
          <span className="tb-pill fl-status-pill">
            <span className={`status-dot ${isConnected ? 'ok' : 'pending'}`} />
            Fabric {info.networkStatus}
          </span>
          <LedgerVerifiedBadge />
        </div>
      </GlassCard>

      {/* Network stats */}
      <div className="fl-stats-row">
        {netStats.map(({ icon: Icon, label, value }) => (
          <GlassCard key={label} className="fl-stat-card">
            <div className="fl-stat-icon">
              <Icon size={16} strokeWidth={1.9} />
            </div>
            <div>
              <div className="fl-stat-value mono">{value}</div>
              <div className="fl-stat-label">{label}</div>
            </div>
          </GlassCard>
        ))}
      </div>

      {/* Transaction timeline */}
      <GlassCard>
        <div className="card-header">
          <h3>
            <Layers size={15} className="hdr-icon" /> Transaction Timeline
          </h3>
          <span className="text-muted" style={{ fontSize: 11.5 }}>
            newest first · {transactions.length} transactions
          </span>
        </div>

        {transactions.length === 0 ? (
          <div style={{ padding: '36px 16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
            {info.networkStatus === 'OFFLINE'
              ? 'No on-chain ledger transactions available. Hyperledger Fabric network is currently offline.'
              : 'No ledger transactions available.'}
          </div>
        ) : (
          <div className="tx-timeline">
            {transactions.map((tx) => (
              <div key={tx.txId} className="tx-row">
                <div className="tx-rail">
                  <div className="tx-node">
                    <CircleCheck size={13} />
                  </div>
                  <div className="tx-line" />
                </div>
                <div className="tx-card">
                  <div className="tx-card-head">
                    <span className="mono tx-id" title={tx.txId}>
                      TX {tx.txId.slice(0, 18)}…
                    </span>
                    <span className="tx-block mono">block #{tx.block}</span>
                    <StatusBadge status={tx.status} />
                    <span className="tx-time">{fmtTime(tx.timestamp)}</span>
                  </div>
                  <div className="tx-card-body">
                    <div className="tx-field">
                      <span className="tx-k">Finding</span>
                      <span className="tx-v mono">{tx.findingId}</span>
                    </div>
                    <div className="tx-field">
                      <span className="tx-k">Asset ID</span>
                      <span className="tx-v mono">{tx.assetId}</span>
                    </div>
                    <div className="tx-field">
                      <span className="tx-k">Module</span>
                      <span className="tx-v">{tx.moduleName}</span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
