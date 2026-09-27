import { useEffect, useMemo, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import './OrbitalMonitor.css';

/**
 * OrbitalMonitor — "SECURITY ORBIT / SYSTEM MONITOR" centerpiece.
 * Concentric rotating rings represent Data / Model / Integrity /
 * Findings layers with detection markers and a radar sweep.
 * Pure SVG + CSS animations; pauses when the tab is hidden.
 */
export default function OrbitalMonitor({ threats = [], status = 'NOMINAL' }) {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReduced(mq.matches);
    const fn = (e) => setReduced(e.matches);
    mq.addEventListener?.('change', fn);
    return () => mq.removeEventListener?.('change', fn);
  }, []);

  const total = threats.reduce((s, t) => s + t.count, 0) || 1;

  // Detection markers placed per severity ring
  const markers = useMemo(() => {
    const out = [];
    const per = { Critical: 5, High: 4, Medium: 3, Low: 2 };
    threats.forEach((t) => {
      const n = per[t.level] || 2;
      for (let i = 0; i < n; i++) {
        const a = (i / n) * 360 + t.level.length * 13;
        out.push({ angle: a, color: t.color, level: t.level });
      }
    });
    return out;
  }, [threats]);

  const RINGS = [
    { r: 52, label: 'DATA', dur: 26, dir: 'cw' },
    { r: 82, label: 'MODEL', dur: 38, dir: 'ccw' },
    { r: 112, label: 'INTEGRITY', dur: 52, dir: 'cw' },
    { r: 142, label: 'FINDINGS', dur: 70, dir: 'ccw' }
  ];

  return (
    <div className={`orbital ${reduced ? 'orbital-still' : ''}`}>
      <svg viewBox="0 0 360 360" className="orbital-svg" role="img" aria-label="Security orbit monitor">
        <defs>
          <linearGradient id="orbSweep" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Static guide rings + ticks */}
        <g className="orb-guidebar">
          <circle cx="180" cy="180" r="168" fill="none" stroke="rgba(56,189,248,0.1)" strokeWidth="1" strokeDasharray="2 6" />
          {Array.from({ length: 72 }).map((_, i) => {
            const a = (i * 5 * Math.PI) / 180;
            const inner = i % 6 === 0 ? 158 : 163;
            return (
              <line
                key={i}
                x1={180 + Math.cos(a) * inner}
                y1={180 + Math.sin(a) * inner}
                x2={180 + Math.cos(a) * 167}
                y2={180 + Math.sin(a) * 167}
                stroke="rgba(56,189,248,0.28)"
                strokeWidth="1"
              />
            );
          })}
        </g>

        {/* Rotating system rings */}
        {RINGS.map((ring, idx) => (
          <g
            key={ring.label}
            className={`orb-ring ${ring.dir === 'cw' ? 'spin-cw' : 'spin-ccw'}`}
            style={{ animationDuration: `${ring.dur}s`, transformOrigin: '180px 180px' }}
          >
            <circle
              cx="180"
              cy="180"
              r={ring.r}
              fill="none"
              stroke="rgba(56,189,248,0.22)"
              strokeWidth="1"
              strokeDasharray={idx % 2 ? '10 6' : 'none'}
            />
            <circle cx={180 + ring.r} cy="180" r="2.4" fill="#22d3ee" opacity="0.85" />
            <text
              x={180}
              y={180 - ring.r - 6}
              textAnchor="middle"
              className="orb-ring-label"
            >
              {ring.label}
            </text>
          </g>
        ))}

        {/* Radar sweep */}
        <g className="orb-sweep spin-cw" style={{ animationDuration: '9s', transformOrigin: '180px 180px' }}>
          <path d="M180,180 L348,180 A168,168 0 0,0 322,88 Z" fill="url(#orbSweep)" opacity="0.35" />
        </g>

        {/* Detection markers */}
        {markers.map((m, i) => {
          const a = (m.angle * Math.PI) / 180;
          const ringR = m.level === 'Critical' ? 52 : m.level === 'High' ? 82 : m.level === 'Medium' ? 112 : 142;
          const x = 180 + Math.cos(a) * ringR;
          const y = 180 + Math.sin(a) * ringR;
          return (
            <g key={i} className="orb-marker">
              <circle cx={x} cy={y} r="3.2" fill={m.color} opacity="0.95" />
              <circle cx={x} cy={y} r="6.5" fill="none" stroke={m.color} strokeWidth="1" opacity="0.4" />
            </g>
          );
        })}

        {/* Center core */}
        <circle cx="180" cy="180" r="34" fill="rgba(8,16,32,0.9)" stroke="rgba(56,189,248,0.4)" strokeWidth="1" />
        <circle cx="180" cy="180" r="41" fill="none" stroke="rgba(56,189,248,0.2)" strokeWidth="1" strokeDasharray="4 4" className="spin-cw" style={{ animationDuration: '18s', transformOrigin: '180px 180px' }} />
        <g transform="translate(180 174)" className="orb-core-icon">
          <ShieldCheck size={26} strokeWidth={1.8} x={-13} y={-13} width={26} height={26} />
        </g>
        <text x="180" y="204" textAnchor="middle" className="orb-core-label">SENTINEL</text>
      </svg>

      <div className="orbital-side">
        <div className="orbital-status">
          <span className={`status-dot ${status === 'NOMINAL' ? 'ok' : 'warn'}`} />
          <span className="orbital-status-text">SYSTEM {status}</span>
        </div>
        <div className="orbital-legend">
          {threats.map((t) => (
            <div key={t.level} className="orbital-legend-row">
              <span className="orbital-legend-dot" style={{ background: t.color }} />
              <span className="orbital-legend-label">{t.level.toUpperCase()}</span>
              <span className="orbital-legend-count">{t.count}</span>
            </div>
          ))}
        </div>
        <div className="orbital-total mono">
          <span>TRACKED</span>
          <b>{total}</b>
        </div>
      </div>
    </div>
  );
}
