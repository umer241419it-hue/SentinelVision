import { useEffect, useState } from 'react';
import { useTheme } from '../context/ThemeContext';
import { HeartPulse, RefreshCw, Clock } from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import GlassCard from '../components/GlassCard';
import { StatusBadge } from '../components/Badges';
import { getSystemHealth, getBridgeStatus } from '../services/api';
import './SystemHealth.css';

const HEALTH_COLORS = {
  dark: { area: '#34d399', grid: 'rgba(126,168,255,0.08)', axis: '#66738f', axisLine: 'rgba(126,168,255,0.14)' },
  light: { area: '#059669', grid: 'rgba(28,60,120,0.1)', axis: '#667085', axisLine: 'rgba(28,60,120,0.18)' }
};

export default function SystemHealth({ notify }) {
  const { theme } = useTheme();
  const hc = HEALTH_COLORS[theme] || HEALTH_COLORS.dark;
  const [health, setHealth] = useState(null);
  const [lastCheck, setLastCheck] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = () => {
    setRefreshing(true);
    Promise.all([getSystemHealth(), getBridgeStatus()])
      .then(([h, b]) => {
        setHealth({ ...h, bridge: b });
        setLastCheck(new Date());
      })
      .finally(() => setRefreshing(false));
  };

  useEffect(() => {
    load();
  }, []);

  if (!health)
    return (
      <div className="page-loading">
        <div className="spinner" /> Checking system health…
      </div>
    );

  const passCount = health.services.filter((s) => s.status === 'PASS').length;

  return (
    <div className="anim-fade">
      {/* Overall */}
      <div className="sh-top">
        <GlassCard className="sh-score-card" glow="cyan">
          <div className="sh-score-left">
            <div className="sh-score-ring">
              <svg viewBox="0 0 120 120" width="128" height="128">
                <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(126,168,255,0.1)" strokeWidth="8" />
                <circle
                  cx="60"
                  cy="60"
                  r="52"
                  fill="none"
                  stroke="#34d399"
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray={`${(health.score / 100) * 327} 327`}
                  transform="rotate(-90 60 60)"
                  style={{ filter: 'drop-shadow(0 0 8px rgba(52,211,153,0.45))' }}
                />
                <text x="60" y="58" textAnchor="middle" className="sh-ring-num">
                  {health.score}
                </text>
                <text x="60" y="75" textAnchor="middle" className="sh-ring-label">
                  HEALTH SCORE
                </text>
              </svg>
            </div>
            <div>
              <div className="sh-overall">
                Overall <StatusBadge status={health.overall} />
              </div>
              <div className="sh-passcount">
                {passCount}/{health.services.length} services passing
              </div>
              <button className="hud-btn sh-refresh" onClick={load} disabled={refreshing}>
                <RefreshCw size={13} className={refreshing ? 'spin-icon' : ''} />
                {refreshing ? 'Checking…' : 'Re-run checks'}
              </button>
            </div>
          </div>
        </GlassCard>

        <GlassCard className="sh-history-card">
          <div className="card-header">
            <h3>
              <HeartPulse size={15} className="hdr-icon" /> Health History
            </h3>
            <span className="text-muted" style={{ fontSize: 11.5 }}>
              <Clock size={11} style={{ verticalAlign: '-1px' }} /> last check:{' '}
              {lastCheck ? lastCheck.toLocaleTimeString() : '—'}
            </span>
          </div>
          <div className="sh-chart">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={health.history} margin={{ top: 8, right: 10, left: -18, bottom: 0 }}>
                <defs>
                  <linearGradient id="gHealth" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={hc.area} stopOpacity={0.3} />
                    <stop offset="100%" stopColor={hc.area} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={hc.grid} vertical={false} />
                <XAxis
                  dataKey="time"
                  tick={{ fill: hc.axis, fontSize: 10.5 }}
                  axisLine={{ stroke: hc.axisLine }}
                  tickLine={false}
                />
                <YAxis
                  domain={[80, 100]}
                  tick={{ fill: hc.axis, fontSize: 10.5 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    return (
                      <div className="chart-tip glass">
                        <div className="chart-tip-label">{label}</div>
                        <div className="chart-tip-row">
                          <span className="chart-tip-dot" style={{ background: '#34d399' }} />
                          <span>score:</span>
                          <b>{payload[0].value}</b>
                        </div>
                      </div>
                    );
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="score"
                  stroke={hc.area}
                  strokeWidth={2}
                  fill="url(#gHealth)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>
      </div>

      {/* Service checks */}
      <GlassCard>
        <div className="card-header">
          <h3>
            <HeartPulse size={15} className="hdr-icon" /> Service Checks
          </h3>
          <span className="text-muted" style={{ fontSize: 11.5 }}>
            mirrors results/system_status.json pipeline
          </span>
        </div>
        <div className="sh-services">
          {health.services.map((s) => (
            <div key={s.name} className={`sh-service st-border-${s.status.toLowerCase()}`}>
              <div className="sh-service-head">
                <span className="sh-service-name">{s.name}</span>
                <StatusBadge status={s.status} />
              </div>
              <div className="sh-service-detail">{s.detail}</div>
              <div className="sh-service-foot">
                <span>uptime {s.uptime}</span>
                <span className="mono">operational</span>
              </div>
            </div>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}
