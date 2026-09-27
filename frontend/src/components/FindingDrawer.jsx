import { useEffect } from 'react';
import {
  X, Radar, FileJson, Hash, Link2, CheckCircle2, ShieldCheck, Copy, Check
} from 'lucide-react';
import { useState } from 'react';
import { SeverityBadge, DispositionBadge } from './Badges';
import './FindingDrawer.css';

function fmtTime(iso) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function CopyChip({ value }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="hash-chip copy-chip"
      title="Copy to clipboard"
      onClick={() => {
        navigator.clipboard?.writeText(value);
        setCopied(true);
        setTimeout(() => setCopied(false), 1400);
      }}
    >
      {copied ? <Check size={11} color="#34d399" /> : <Copy size={11} />}
      <span>{value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-8)}` : value}</span>
    </button>
  );
}

/**
 * VerificationChain — Detection → Evidence Generated → Hash Created →
 * Fabric Transaction → Ledger Confirmed, each stage with icon/status/time.
 */
function VerificationChain({ finding }) {
  const committed = finding.ledgerStatus === 'COMMITTED';
  const stages = [
    { icon: Radar, label: 'Detection', time: fmtTime(finding.timestamp), status: 'COMPLETE', detail: finding.moduleName },
    {
      icon: FileJson,
      label: 'Evidence Generated',
      time: fmtTime(finding.timestamp),
      status: 'COMPLETE',
      detail: finding.schema || 'evidence record (JSON, schema-tagged)'
    },
    { icon: Hash, label: 'Hash Created', time: fmtTime(finding.timestamp), status: 'COMPLETE', detail: 'SHA-256' },
    {
      icon: Link2,
      label: 'Fabric Transaction',
      time: committed ? fmtTime(finding.timestamp) : '—',
      status: committed ? 'COMPLETE' : 'PENDING',
      detail: committed ? finding.txId : 'awaiting commit'
    },
    {
      icon: ShieldCheck,
      label: 'Ledger Confirmed',
      time: committed ? fmtTime(finding.timestamp) : '—',
      status: committed ? 'COMPLETE' : 'PENDING',
      detail: committed ? 'immutable record on mychannel' : 'not yet committed'
    }
  ];

  return (
    <div className="vchain">
      {stages.map((s, i) => {
        const Icon = s.icon;
        const done = s.status === 'COMPLETE';
        return (
          <div key={s.label} className="vchain-stage-wrap">
            <div className={`vchain-stage ${done ? 'done' : 'pending'}`}>
              <div className="vchain-node">
                <Icon size={15} strokeWidth={1.9} />
              </div>
              <div className="vchain-info">
                <div className="vchain-label">{s.label}</div>
                <div className="vchain-detail mono">{s.detail}</div>
                <div className="vchain-time">{s.time}</div>
              </div>
              <span className={`vchain-status ${done ? 'done' : 'pending'}`}>
                {done ? <CheckCircle2 size={12} /> : null}
                {s.status}
              </span>
            </div>
            {i < stages.length - 1 && <div className={`vchain-line ${done ? 'done' : ''}`} />}
          </div>
        );
      })}
    </div>
  );
}

/**
 * FindingDrawer — detailed side drawer for a single finding.
 */
export default function FindingDrawer({ finding, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!finding) return null;

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="finding-drawer">
        <header className="drawer-head">
          <div>
            <div className="drawer-kicker">Finding Detail</div>
            <h2 className="mono">{finding.id}</h2>
          </div>
          <button className="hud-btn icon-only ghost" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </header>

        <div className="drawer-body">
          <section className="drawer-section">
            <div className="drawer-grid">
              <div>
                <div className="drawer-field-label">Module</div>
                <div className="drawer-field-value">{finding.moduleName}</div>
              </div>
              <div>
                <div className="drawer-field-label">Severity</div>
                <SeverityBadge severity={finding.severity} />
              </div>
              <div>
                <div className="drawer-field-label">Disposition</div>
                <DispositionBadge disposition={finding.disposition} />
              </div>
              <div>
                <div className="drawer-field-label">Confidence</div>
                <div className="drawer-field-value">{(finding.confidence * 100).toFixed(0)}%</div>
              </div>
              <div>
                <div className="drawer-field-label">Timestamp</div>
                <div className="drawer-field-value">{fmtTime(finding.timestamp)}</div>
              </div>
              <div>
                <div className="drawer-field-label">Ledger</div>
                <div className="drawer-field-value">{finding.ledgerStatus}</div>
              </div>
            </div>
          </section>

          <section className="drawer-section">
            <div className="drawer-field-label">Reason</div>
            <p className="drawer-reason">{finding.reason}</p>
          </section>

          <section className="drawer-section">
            <div className="drawer-field-label">Asset ID</div>
            <CopyChip value={finding.assetID} />
          </section>

          <section className="drawer-section">
            <div className="drawer-field-label">Evidence Hash (SHA-256)</div>
            <CopyChip value={finding.evidenceHash} />
            <p className="drawer-hint">
              Evidence records are content-addressed by this digest — any modification of the
              evidence invalidates the hash and breaks verification.
            </p>
          </section>

          <section className="drawer-section">
            <div className="drawer-field-label">Verification Chain</div>
            <VerificationChain finding={finding} />
          </section>
        </div>
      </aside>
    </>
  );
}
