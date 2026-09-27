import './Badges.css';

/** Severity badge: CRITICAL / HIGH / MEDIUM / LOW (muted, enterprise tones). */
export function SeverityBadge({ severity }) {
  return <span className={`sev-badge sev-${String(severity).toLowerCase()}`}>{severity}</span>;
}

/** Status badge for dispositions: QUARANTINE / REVIEW / ACCEPT. */
export function DispositionBadge({ disposition }) {
  return <span className={`disp-badge disp-${String(disposition).toLowerCase()}`}>{disposition}</span>;
}

/** Generic status badge: PASS / WARNING / ERROR / OK / ALERT / COMMITTED / PENDING... */
export function StatusBadge({ status }) {
  const key = String(status).toLowerCase();
  return <span className={`status-badge st-${key}`}>{status}</span>;
}

/** Ledger verification pill with check icon. */
export function LedgerVerifiedBadge() {
  return <span className="ledger-badge">✓ Verified on Hyperledger Fabric</span>;
}
