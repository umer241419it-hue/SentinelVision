import { useEffect, useState } from 'react';
import { useTheme } from '../context/ThemeContext';
import { Radar, AlertTriangle, Gauge } from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, Scatter, ComposedChart
} from 'recharts';
import GlassCard from '../components/GlassCard';
import DataTable from '../components/DataTable';
import { StatusBadge } from '../components/Badges';
import { getDriftResults } from '../services/api';
import './DriftMonitor.css';

function fmtTime(iso) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

// Theme-aware chart colors
const C =
  ({ dark: { drift: '#22d3ee', warn: '#fbbf24', danger: '#f87171', grid: 'rgba(126,168,255,0.08)', axis: '#66738f', axisLine: 'rgba(126,168,255,0.14)' },
    light: { drift: '#0891b2', warn: '#b45309', danger: '#dc2626', grid: 'rgba(28,60,120,0.1)', axis: '#667085', axisLine: 'rgba(28,60,120,0.18)' } });

export default function DriftMonitor() {
  const { theme } = useTheme();
  const colors = C[theme] || C.dark;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getDriftResults()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return (
      <div className="page-loading">
        <div className="spinner" /> Loading drift monitor…
      </div>
    );
  if (error)
    return (
      <div className="page-error">
        <AlertTriangle size={18} /> {error}
      </div>
    );

  const { summary, series, windows } = data;
  const driftRatio = Math.min(100, (summary.currentScore / summary.threshold) * 100);

  return (
    <div className="anim-fade">
      {/* Summary stat row */}
      <div className="drift-stat-row">
        <GlassCard className="drift-score-card" glow="cyan">
          <div className="dsc-ring">
            <svg viewBox="0 0 120 120" width="118" height="118">
              <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(126,168,255,0.1)" strokeWidth="8" />
              <circle
                cx="60"
                cy="60"
                r="52"
                fill="none"
                stroke="#22d3ee"
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={`${(driftRatio / 100) * 327} 327`}
                transform="rotate(-90 60 60)"
                style={{ filter: 'drop-shadow(0 0 6px rgba(34,211,238,0.5))' }}
              />
              <text x="60" y="57" textAnchor="middle" className="drift-ring-num">
                {summary.currentScore.toFixed(3)}
              </text>
              <text x="60" y="74" textAnchor="middle" className="drift-ring-label">
                MMD SCORE
              </text>
            </svg>
          </div>
          <div className="dsc-meta">
            <div className="dsc-title">Current Drift Score</div>
            <div className="dsc-sub">
              {driftRatio >= 100
                ? 'Exceeds calibrated threshold'
                : `${driftRatio.toFixed(0)}% of threshold`}
            </div>
            <StatusBadge status={summary.detectionStatus} />
          </div>
        </GlassCard>

        <GlassCard className="drift-kv">
          <div className="kv-item">
            <span className="kv-label">Threshold (calibrated)</span>
            <span className="kv-value mono">{summary.threshold}</span>
          </div>
          <div className="kv-item">
            <span className="kv-label">Calibration ID</span>
            <span className="kv-value mono">{summary.calibrationId}</span>
          </div>
          <div className="kv-item">
            <span className="kv-label">Reference Dataset</span>
            <span className="kv-value small">{summary.referenceDataset}</span>
          </div>
          <div className="kv-item">
            <span className="kv-label">Monitoring Window</span>
            <span className="kv-value small mono">{summary.monitoringWindow}</span>
          </div>
          <div className="kv-item">
            <span className="kv-label">Last Checked</span>
            <span className="kv-value">{fmtTime(summary.lastChecked)}</span>
          </div>
        </GlassCard>
      </div>

      {/* Main chart */}
      <GlassCard className="drift-chart-card">
        <div className="card-header">
          <h3>
            <Gauge size={15} className="hdr-icon" /> Distribution Drift Over Time
          </h3>
          <span className="text-muted" style={{ fontSize: 11.5 }}>
            MMD (RBF kernel, permutation test n=200) · window size 100, step 25
          </span>
        </div>
        <div className="drift-chart">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={series} margin={{ top: 10, right: 14, left: -12, bottom: 0 }}>
              <CartesianGrid stroke={colors.grid} vertical={false} />
              <XAxis
                dataKey="time"
                tick={{ fill: colors.axis, fontSize: 10.5 }}
                axisLine={{ stroke: colors.axisLine }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: colors.axis, fontSize: 10.5 }}
                axisLine={false}
                tickLine={false}
                domain={[0, 'auto']}
              />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <div className="chart-tip glass">
                      <div className="chart-tip-label">{label}</div>
                      {payload.map((p) => (
                        <div key={p.dataKey} className="chart-tip-row">
                          <span className="chart-tip-dot" style={{ background: p.color }} />
                          <span>{p.name}:</span>
                          <b>{typeof p.value === 'number' ? p.value.toFixed(4) : p.value}</b>
                        </div>
                      ))}
                    </div>
                  );
                }}
              />
              <ReferenceLine
                y={summary.threshold}
                stroke={colors.warn}
                strokeDasharray="6 4"
                label={{
                  value: `threshold ${summary.threshold}`,
                  fill: colors.warn,
                  fontSize: 10.5,
                  position: 'insideTopRight'
                }}
              />
              <Line
                type="monotone"
                dataKey="drift"
                name="MMD drift score"
                stroke={colors.drift}
                strokeWidth={2.2}
                dot={false}
                activeDot={{ r: 4, fill: colors.drift }}
              />
              <Scatter
                name="Anomaly"
                dataKey="drift"
                data={series.filter((p) => p.anomaly)}
                fill={colors.danger}
                shape="circle"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="drift-legend">
          <span className="legend-item"><span className="legend-swatch" style={{ background: colors.drift }} /> MMD score</span>
          <span className="legend-item"><span className="legend-swatch dashed" /> Calibrated threshold</span>
          <span className="legend-item"><span className="legend-swatch" style={{ background: colors.danger, borderRadius: '50%' }} /> Anomaly points</span>
        </div>
      </GlassCard>

      {/* Windows table */}
      <GlassCard className="drift-table-card">
        <div className="card-header">
          <h3>
            <Radar size={15} className="hdr-icon" /> Drift Windows
          </h3>
          <span className="text-muted" style={{ fontSize: 11.5 }}>
            {windows.length} windows monitored
          </span>
        </div>
        <DataTable
          columns={[
            { key: 'window', label: 'Window', render: (r) => <span className="mono">{r.window}</span> },
            {
              key: 'mmdScore',
              label: 'MMD Score',
              render: (r) => (
                <span className={r.mmdScore > r.threshold ? 'mono text-danger' : 'mono'}>
                  {r.mmdScore.toFixed(6)}
                </span>
              )
            },
            { key: 'threshold', label: 'Threshold', render: (r) => <span className="mono">{r.threshold}</span> },
            { key: 'confidence', label: 'Confidence', render: (r) => `${(r.confidence * 100).toFixed(0)}%` },
            { key: 'status', label: 'Status', render: (r) => <StatusBadge status={r.status} /> },
            { key: 'timestamp', label: 'Timestamp', render: (r) => fmtTime(r.timestamp) }
          ]}
          rows={windows}
        />
      </GlassCard>
    </div>
  );
}
