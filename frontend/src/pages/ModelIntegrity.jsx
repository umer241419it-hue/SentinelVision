import { useEffect, useState } from 'react';
import { ShieldAlert, Activity, Fingerprint, AlertTriangle, Cpu } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { SeverityBadge, StatusBadge } from '../components/Badges';
import { getModelIntegrityResults } from '../services/api';
import './ModelIntegrity.css';

function fmtTime(iso) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function RadialGauge({ value }) {
  const R = 84;
  const C = 2 * Math.PI * R;
  const filled = (value / 100) * C;
  return (
    <div className="mi-gauge">
      <svg viewBox="0 0 200 200" width="230" height="230">
        <defs>
          <linearGradient id="gaugeGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#22d3ee" />
            <stop offset="100%" stopColor="#a78bfa" />
          </linearGradient>
        </defs>
        <circle cx="100" cy="100" r={R} fill="none" stroke="rgba(126,168,255,0.09)" strokeWidth="12" />
        <circle
          cx="100"
          cy="100"
          r={R}
          fill="none"
          stroke="url(#gaugeGrad)"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${C}`}
          transform="rotate(-90 100 100)"
          style={{ filter: 'drop-shadow(0 0 10px rgba(34,211,238,0.4))' }}
        />
        {/* tick marks */}
        {Array.from({ length: 40 }).map((_, i) => {
          const a = (i / 40) * 2 * Math.PI;
          const x1 = 100 + Math.cos(a) * (R - 12);
          const y1 = 100 + Math.sin(a) * (R - 12);
          const x2 = 100 + Math.cos(a) * (R - 17);
          const y2 = 100 + Math.sin(a) * (R - 17);
          return (
            <line
              key={i}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke="rgba(126,168,255,0.14)"
              strokeWidth="1"
            />
          );
        })}
        <text x="100" y="92" textAnchor="middle" className="gauge-num">
          {value}%
        </text>
        <text x="100" y="112" textAnchor="middle" className="gauge-label">
          MODEL INTEGRITY
        </text>
        <text x="100" y="130" textAnchor="middle" className="gauge-sub">
          Neural Cleanse + MAD · STRIP
        </text>
      </svg>
    </div>
  );
}

export default function ModelIntegrity() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getModelIntegrityResults()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return (
      <div className="page-loading">
        <div className="spinner" /> Loading model integrity…
      </div>
    );
  if (error)
    return (
      <div className="page-error">
        <AlertTriangle size={18} /> {error}
      </div>
    );

  const { summary, signals, metadata } = data;

  const statusCards = [
    { label: 'Model Status', value: <StatusBadge status={summary.modelStatus} /> },
    { label: 'Poisoning Risk', value: <StatusBadge status={summary.poisoningRisk} /> },
    { label: 'Trigger Detection', value: summary.triggerDetection },
    { label: 'Activation Anomaly', value: summary.activationAnomaly },
    { label: 'Validation Status', value: summary.validationStatus },
    {
      label: 'Model Fleet',
      value: `${summary.cleanModels} clean · ${summary.reviewModels} review · ${summary.quarantinedModels} quarantine`
    }
  ];

  return (
    <div className="anim-fade">
      <div className="mi-top">
        <GlassCard className="mi-gauge-card" glow="violet">
          <RadialGauge value={summary.integrityScore} />
        </GlassCard>

        <div className="mi-status-grid">
          {statusCards.map((c) => (
            <GlassCard key={c.label} className="mi-status-card">
              <div className="mi-status-label">{c.label}</div>
              <div className="mi-status-value">{c.value}</div>
            </GlassCard>
          ))}
        </div>
      </div>

      <div className="mi-grid">
        {/* Integrity signals */}
        <GlassCard>
          <div className="card-header">
            <h3>
              <Activity size={15} className="hdr-icon" /> Integrity Signals
            </h3>
            <span className="text-muted" style={{ fontSize: 11.5 }}>model {summary.modelId}</span>
          </div>
          <div className="signal-list">
            {signals.map((s) => (
              <div key={s.name} className={`signal-row ${s.ok ? 'ok' : 'flagged'}`}>
                <span className={`signal-dot ${s.ok ? 'ok' : 'flagged'}`} />
                <div className="signal-info">
                  <div className="signal-name">{s.name}</div>
                  <div className="signal-detail">{s.detail}</div>
                </div>
                <StatusBadge status={s.status} />
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Detection results */}
        <GlassCard>
          <div className="card-header">
            <h3>
              <ShieldAlert size={15} className="hdr-icon" /> Detection Results
            </h3>
          </div>
          <div className="det-results">
            <div className="det-row">
              <span className="det-label">Neural Cleanse + MAD</span>
              <span className="det-value mono">anomaly index 3.13 · threshold 2.0 · class 2 flagged</span>
              <SeverityBadge severity="CRITICAL" />
            </div>
            <div className="det-row">
              <span className="det-label">STRIP Verification</span>
              <span className="det-value mono">entropy suppression corroborates class 2</span>
              <SeverityBadge severity="CRITICAL" />
            </div>
            <div className="det-row">
              <span className="det-label">Dual-direction MMD</span>
              <span className="det-value mono">poisoned vs clean proof — OK</span>
              <SeverityBadge severity="LOW" />
            </div>
            <div className="det-row">
              <span className="det-label">Fleet Scan</span>
              <span className="det-value mono">15 models scored across 3 tasks</span>
              <SeverityBadge severity="MEDIUM" />
            </div>
          </div>
          <div className="divider" />
          <div className="det-verdict">
            <ShieldAlert size={15} />
            <div>
              <div className="det-verdict-title">QUARANTINE RECOMMENDED — pending human review</div>
              <div className="det-verdict-sub">
                Two independent detectors agree on class 2. Model withheld from deployment until
                reviewed; evidence sealed with SHA-256 digests on the ledger.
              </div>
            </div>
          </div>
        </GlassCard>

        {/* Evidence */}
        <GlassCard>
          <div className="card-header">
            <h3>
              <Fingerprint size={15} className="hdr-icon" /> Evidence
            </h3>
          </div>
          <div className="mi-evidence">
            <div className="ev-row">
              <span className="ev-label">Trigger artifacts</span>
              <span className="mono hash-chip">mask_epoch49_class2.npy · sealed</span>
            </div>
            <div className="ev-row">
              <span className="ev-label">Activation probe</span>
              <span className="mono hash-chip">probe_report_id-00000112.json</span>
            </div>
            <div className="ev-row">
              <span className="ev-label">STRIP scores</span>
              <span className="mono hash-chip">strip_results.json · SHA-256 sealed</span>
            </div>
            <div className="ev-row">
              <span className="ev-label">Scoring output</span>
              <span className="mono hash-chip">scoring_results.json · committed</span>
            </div>
          </div>
        </GlassCard>

        {/* Metadata */}
        <GlassCard>
          <div className="card-header">
            <h3>
              <Cpu size={15} className="hdr-icon" /> Model Metadata
            </h3>
          </div>
          <div className="meta-grid">
            <div><span className="meta-k">Architecture</span><span className="meta-v">{metadata.architecture}</span></div>
            <div><span className="meta-k">Input</span><span className="meta-v mono">{metadata.inputShape}</span></div>
            <div><span className="meta-k">Classes</span><span className="meta-v">{metadata.classes}</span></div>
            <div><span className="meta-k">Parameters</span><span className="meta-v">{metadata.parameters}</span></div>
            <div><span className="meta-k">Checkpoint</span><span className="meta-v mono">{metadata.checkpoint}</span></div>
            <div><span className="meta-k">Trained</span><span className="meta-v">{fmtTime(metadata.trainedAt)}</span></div>
          </div>
        </GlassCard>
      </div>
    </div>
  );
}
