import { useEffect, useState } from 'react';
import {
  Radar, DatabaseZap, Link2, HeartPulse, ShieldAlert
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import GlassCard from '../components/GlassCard';
import MetricCard from '../components/MetricCard';
import OrbitalMonitor from '../components/OrbitalMonitor';
import { SeverityBadge, StatusBadge } from '../components/Badges';
import { useTheme } from '../context/ThemeContext';
import { getOverview, getActivitySeries, getFindings } from '../services/api';
import './Overview.css';

function buildSparkline(seed, n = 12) {
  let x = seed >>> 0;
  const out = [];
  let v = 50;
  for (let i = 0; i < n; i += 1) {
    x = (Math.imul(1664525, x) + 1013904223) >>> 0;
    v = Math.max(6, Math.min(96, v + (((x / 4294967296) - 0.5) * 18)));
    out.push(Math.round(v));
  }
  return out;
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tip">
      <div className="chart-tip-label">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="chart-tip-row">
          <span className="chart-tip-dot" style={{ background: p.color || p.stroke }} />
          <span>{p.name}:</span>
          <b>{p.value}</b>
        </div>
      ))}
    </div>
  );
}

// Theme-aware series colors
const SERIES = {
  dark: { drift: '#22d3ee', data: '#60a5fa', model: '#a78bfa', findings: '#fb923c', grid: 'rgba(56,189,248,0.09)', axis: '#4d6b83', axisLine: 'rgba(56,189,248,0.2)' },
  light: { drift: '#0e7490', data: '#1d4ed8', model: '#6d28d9', findings: '#c2410c', grid: 'rgba(9,42,96,0.1)', axis: '#5d7189', axisLine: 'rgba(9,42,96,0.22)' }
};

export default function Overview({ onOpenFinding }) {
  const { theme } = useTheme();
  const C = SERIES[theme] || SERIES.dark;
  const [kpis, setKpis] = useState(null);
  const [threats, setThreats] = useState([]);
  const [series, setSeries] = useState([]);
  const [range, setRange] = useState('24H');
  const [recent, setRecent] = useState([]);

  useEffect(() => {
    let live = true;
    getOverview().then((d) => {
      if (!live) return;
      setKpis(d.kpis);
      setThreats(d.threats);
    });
    getFindings().then((f) => live && setRecent(f.slice(0, 6)));
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    let live = true;
    getActivitySeries(range).then((s) => live && setSeries(s));
    return () => {
      live = false;
    };
  }, [range]);

  const kpiDefs = kpis
    ? [
        { icon: HeartPulse, label: 'SYSTEM HEALTH', value: kpis.systemHealth.value, status: 'STABLE', trend: kpis.systemHealth.trend, up: kpis.systemHealth.up, spark: buildSparkline(11), color: C.drift },
        { icon: ShieldAlert, label: 'ACTIVE FINDINGS', value: String(kpis.activeFindings.value).padStart(2, '0'), status: 'MONITORING', trend: kpis.activeFindings.trend, up: kpis.activeFindings.up, spark: buildSparkline(22), color: C.findings },
        { icon: Radar, label: 'DRIFT EVENTS', value: String(kpis.driftEvents.value).padStart(2, '0'), status: 'DETECTED', trend: kpis.driftEvents.trend, up: kpis.driftEvents.up, spark: buildSparkline(33), color: C.drift },
        { icon: DatabaseZap, label: 'INTEGRITY ALERTS', value: String(kpis.integrityAlerts.value).padStart(2, '0'), status: 'REVIEW', trend: kpis.integrityAlerts.trend, up: kpis.integrityAlerts.up, spark: buildSparkline(44), color: C.model },
        { icon: Link2, label: 'LEDGER TRANSACTIONS', value: String(kpis.ledgerTx.value).padStart(3, '0'), status: 'VERIFIED', trend: kpis.ledgerTx.trend, up: kpis.ledgerTx.up, spark: buildSparkline(55), color: C.data }
      ]
    : [];

  return (
    <div className="anim-fade">
      {/* Greeting banner */}
      <div className="hero-banner">
        <h1>AI Security Command Center</h1>
        <p>Real-time monitoring of AI systems, data integrity and model security</p>
      </div>

      {/* HUD metrics */}
      <div className="kpi-row">
        {kpiDefs.map((k) => (
          <MetricCard
            key={k.label}
            icon={k.icon}
            label={k.label}
            value={k.value}
            status={k.status}
            trend={k.trend}
            up={k.up}
            sparkData={k.spark}
            sparkColor={k.color}
          />
        ))}
      </div>

      <div className="dash-grid-main">
        {/* Orbital monitor */}
        <GlassCard className="orbital-card">
          <div className="card-header">
            <h3>System monitor</h3>
            <span className="hdr-meta">Data · Model · Integrity · Findings</span>
          </div>
          <OrbitalMonitor threats={threats} status="NOMINAL" />
        </GlassCard>

        {/* Threat overview */}
        <GlassCard>
          <div className="card-header">
            <h3>Threat overview</h3>
            <span className="hdr-meta">Last 24h</span>
          </div>
          <div className="threat-list">
            {threats.map((t) => (
              <div key={t.level} className="threat-row">
                <div className="threat-meta">
                  <span className="threat-level" style={{ color: t.color }}>
                    {t.level.toUpperCase()}
                  </span>
                  <span className="threat-count mono">{String(t.count).padStart(2, '0')}</span>
                </div>
                <div className="threat-bar-track">
                  <div
                    className="threat-bar"
                    style={{
                      width: `${(t.count / Math.max(...threats.map((x) => x.count), 1)) * 100}%`,
                      background: `linear-gradient(90deg, transparent, ${t.color})`
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
          <div className="divider" />
          <div className="threat-footnote mono">
            Severity distribution across detection modules
          </div>
        </GlassCard>
      </div>

      {/* Security activity */}
      <GlassCard className="activity-card">
        <div className="card-header">
          <h3>Security activity</h3>
          <div className="range-toggle">
            {['24H', '7D', '30D'].map((r) => (
              <button
                key={r}
                className={`range-btn ${range === r ? 'active' : ''}`}
                onClick={() => setRange(r)}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
        <div className="activity-chart">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
              <defs>
                <linearGradient id="gDrift" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={C.drift} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={C.drift} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gData" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={C.data} stopOpacity={0.24} />
                  <stop offset="100%" stopColor={C.data} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gModel" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={C.model} stopOpacity={0.24} />
                  <stop offset="100%" stopColor={C.model} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={C.grid} vertical={false} strokeDasharray="3 5" />
              <XAxis
                dataKey="time"
                tick={{ fill: C.axis, fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
                axisLine={{ stroke: C.axisLine }}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: C.axis, fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: C.drift, strokeOpacity: 0.3, strokeDasharray: '3 3' }} />
              <Legend iconType="plainline" wrapperStyle={{ fontSize: 10, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.08em' }} />
              <Area type="monotone" dataKey="drift" name="DRIFT" stroke={C.drift} strokeWidth={1.8} fill="url(#gDrift)" />
              <Area type="monotone" dataKey="dataIntegrity" name="INTEGRITY" stroke={C.data} strokeWidth={1.8} fill="url(#gData)" />
              <Area type="monotone" dataKey="modelIntegrity" name="MODEL" stroke={C.model} strokeWidth={1.8} fill="url(#gModel)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </GlassCard>

      {/* Recent findings HUD table */}
      <GlassCard className="live-findings">
        <div className="card-header">
          <h3>Recent findings</h3>
          <span className="hdr-meta">{recent.length} records</span>
        </div>
        <div className="lf-rows">
          {recent.map((f) => (
            <button key={f.id} className="lf-row" onClick={() => onOpenFinding?.(f.id)}>
              <SeverityBadge severity={f.severity} />
              <span className="lf-reason">{f.reason}</span>
              <span className="lf-module mono">{f.moduleName}</span>
              <span className="mono lf-conf">{(f.confidence * 100).toFixed(0)}%</span>
              <span className="lf-hash mono" title={f.evidenceHash}>
                #{f.evidenceHash.slice(0, 8)}
              </span>
              <StatusBadge status={f.ledgerStatus} />
            </button>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}
