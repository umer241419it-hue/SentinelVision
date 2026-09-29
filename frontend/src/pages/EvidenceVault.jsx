import { useEffect, useState } from 'react';
import { Vault, ShieldCheck, Fingerprint, Lock, Search } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { StatusBadge } from '../components/Badges';
import { getEvidence, verifyEvidence } from '../services/api';
import './EvidenceVault.css';

function fmtTime(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
}

export default function EvidenceVault({ notify }) {
  const [evidence, setEvidence] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [verifying, setVerifying] = useState({});
  const [verified, setVerified] = useState({});

  useEffect(() => {
    getEvidence().then((e) => {
      setEvidence(e);
      setLoading(false);
    });
  }, []);

  const verify = async (ev) => {
    setVerifying((v) => ({ ...v, [ev.evidenceId]: true }));
    try {
      const result = await verifyEvidence(ev.evidenceId);
      setVerified((s) => ({ ...s, [ev.evidenceId]: Boolean(result.verified) }));
      notify?.(
        result.verified
          ? `Evidence ${ev.evidenceId.slice(0, 10)}… SHA-256 verified — record intact`
          : `Evidence ${ev.evidenceId.slice(0, 10)}… FAILED SHA-256 verification — possible tampering`,
        result.verified ? 'success' : 'error'
      );
    } catch (err) {
      notify?.(`Evidence verification failed: ${err.message}`, 'error');
    } finally {
      setVerifying((v) => ({ ...v, [ev.evidenceId]: false }));
    }
  };

  const q = query.trim().toLowerCase();
  const filtered = evidence.filter(
    (e) =>
      !q ||
      e.evidenceId.includes(q) ||
      e.sourceModule.toLowerCase().includes(q) ||
      e.relatedFinding.toLowerCase().includes(q) ||
      e.schema.toLowerCase().includes(q)
  );

  const verifiedCount = evidence.filter((e) => e.verificationStatus === 'VERIFIED' || verified[e.evidenceId]).length;

  return (
    <div className="anim-fade">
      {/* Trust banner */}
      <GlassCard className="ev-banner" glow="cyan">
        <div className="ev-banner-icon">
          <Lock size={22} strokeWidth={1.8} />
        </div>
        <div className="ev-banner-text">
          <h2>Tamper-Evident Evidence Store</h2>
          <p>
            Every finding ships with a JSON evidence record sealed by its SHA-256 digest. Evidence
            hashes are committed to the Hyperledger Fabric ledger — any later modification of an
            evidence file invalidates its digest and is immediately detectable.
          </p>
        </div>
        <div className="ev-banner-stats">
          <div className="ev-stat">
            <span className="ev-stat-num">{evidence.length}</span>
            <span className="ev-stat-label">Records</span>
          </div>
          <div className="ev-stat">
            <span className="ev-stat-num ok">{verifiedCount}</span>
            <span className="ev-stat-label">Verified</span>
          </div>
          <div className="ev-stat">
            <span className="ev-stat-num">SHA-256</span>
            <span className="ev-stat-label">Digest</span>
          </div>
        </div>
      </GlassCard>

      <GlassCard>
        <div className="card-header">
          <h3>
            <Vault size={15} className="hdr-icon" /> Evidence Records
          </h3>
          <div className="ev-search">
            <Search size={13} />
            <input
              placeholder="Search by hash, module, finding…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        </div>

        {loading ? (
          <div className="dt-loading">
            <div className="spinner" /> Loading evidence…
          </div>
        ) : filtered.length === 0 ? (
          <div className="dt-empty">No evidence records match your search.</div>
        ) : (
          <div className="ev-grid">
            {filtered.map((ev) => {
              const isVerified = ev.verificationStatus === 'VERIFIED' || verified[ev.evidenceId];
              return (
                <div key={ev.evidenceId} className={`ev-card ${isVerified ? 'verified' : ''}`}>
                  <div className="ev-card-head">
                    <Fingerprint size={14} className="ev-fp" />
                    <span className="mono ev-hash" title={ev.evidenceId}>
                      {ev.evidenceId.slice(0, 24)}…
                    </span>
                    <StatusBadge status={isVerified ? 'VERIFIED' : ev.verificationStatus} />
                  </div>
                  <div className="ev-card-body">
                    <div className="ev-field">
                      <span className="ev-k">Source module</span>
                      <span className="ev-v">{ev.sourceModule}</span>
                    </div>
                    <div className="ev-field">
                      <span className="ev-k">Related finding</span>
                      <span className="ev-v mono">{ev.relatedFinding}</span>
                    </div>
                    <div className="ev-field">
                      <span className="ev-k">Schema</span>
                      <span className="ev-v mono">{ev.schema}</span>
                    </div>
                    <div className="ev-field">
                      <span className="ev-k">Created</span>
                      <span className="ev-v">{fmtTime(ev.createdAt)}</span>
                    </div>
                  </div>
                  <button
                    className={`neo-btn ev-verify-btn ${isVerified ? 'ghost' : 'primary'}`}
                    disabled={verifying[ev.evidenceId]}
                    onClick={() => verify(ev)}
                  >
                    {verifying[ev.evidenceId] ? (
                      <>
                        <span className="spinner" style={{ width: 12, height: 12, borderWidth: 1.6 }} />
                        Verifying…
                      </>
                    ) : isVerified ? (
                      <>
                        <ShieldCheck size={13} /> Verified
                      </>
                    ) : (
                      <>
                        <ShieldCheck size={13} /> Verify Evidence
                      </>
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
