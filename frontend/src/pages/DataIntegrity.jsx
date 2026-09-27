import { useEffect, useState } from 'react';
import { useTheme } from '../context/ThemeContext';
import { DatabaseZap, AlertTriangle, CopyPlus, Shuffle, BoxSelect, ScanSearch } from 'lucide-react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import GlassCard from '../components/GlassCard';
import MetricCard from '../components/MetricCard';
import DataTable from '../components/DataTable';
import { SeverityBadge, DispositionBadge } from '../components/Badges';
import { getDataIntegrityResults } from '../services/api';
import './DataIntegrity.css';

function fmtTime(iso) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

// Theme-aware donut palette (light theme uses deeper hues for contrast)
const DONUT = {
  dark: ['#34d399', '#60a5fa', '#fbbf24', '#a78bfa'],
  light: ['#059669', '#2563eb', '#b45309', '#7c3aed']
};

export default function DataIntegrity() {
  const { theme } = useTheme();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getDataIntegrityResults()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return (
      <div className="page-loading">
        <div className="spinner" /> Loading data integrity…
      </div>
    );
  if (error)
    return (
      <div className="page-error">
        <AlertTriangle size={18} /> {error}
      </div>
    );

  const { summary, breakdown, samples } = data;

  return (
    <div className="anim-fade">
      <div className="kpi-row kpi-5">
        <MetricCard
          icon={BoxSelect}
          label="Total Samples"
          value={summary.totalSamples}
          status="SCANNED"
          sparkColor="#60a5fa"
          sparkData={[80, 82, 81, 84, 83, 85, 84, 86, 85, 85]}
        />
        <MetricCard
          icon={CopyPlus}
          label="Duplicate Samples"
          value={summary.duplicates}
          status="REVIEW"
          sparkColor="#fbbf24"
          sparkData={[4, 6, 5, 8, 9, 11, 12, 14, 16, 20]}
        />
        <MetricCard
          icon={Shuffle}
          label="Label Flips"
          value={summary.labelFlips}
          status="HIGH RISK"
          sparkColor="#f87171"
          sparkData={[0, 1, 1, 2, 2, 3, 4, 4, 5, 6]}
        />
        <MetricCard
          icon={BoxSelect}
          label="OOD Samples"
          value={summary.oodSamples}
          status="FLAGGED"
          sparkColor="#a78bfa"
          sparkData={[1, 1, 2, 2, 3, 4, 5, 6, 7, 9]}
        />
        <MetricCard
          icon={ScanSearch}
          label="Suspicious Samples"
          value={summary.suspicious}
          status="AGGREGATE"
          sparkColor="#22d3ee"
          sparkData={[10, 14, 15, 19, 22, 25, 27, 30, 33, 35]}
        />
      </div>

      <div className="di-grid">
        <GlassCard>
          <div className="card-header">
            <h3>
              <DatabaseZap size={15} className="hdr-icon" /> Integrity Breakdown
            </h3>
            <span className="text-muted" style={{ fontSize: 11.5 }}>
              run {fmtTime(summary.lastRun)}
            </span>
          </div>
          <div className="di-donut">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={breakdown}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="58%"
                  outerRadius="80%"
                  paddingAngle={3}
                  strokeWidth={0}
                >
                  {breakdown.map((entry, i) => (
                    <Cell key={entry.name} fill={(DONUT[theme] || DONUT.dark)[i]} />
                  ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const p = payload[0];
                    return (
                      <div className="chart-tip glass">
                        <div className="chart-tip-row">
                          <span className="chart-tip-dot" style={{ background: p.payload.color }} />
                          <span>{p.name}:</span>
                          <b>{p.value}</b>
                        </div>
                      </div>
                    );
                  }}
                />
                <Legend
                  iconType="circle"
                  iconSize={8}
                  wrapperStyle={{ fontSize: 11.5, color: '#a3b1d0' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>

        <GlassCard>
          <div className="card-header">
            <h3>
              <ScanSearch size={15} className="hdr-icon" /> Checks Run
            </h3>
          </div>
          <div className="checks-list">
            {summary.checksRun.map((c) => (
              <div key={c} className="check-row">
                <span className="check-name mono">{c}</span>
                <span className="check-desc">
                  {c === 'duplicate' && 'Near-duplicate detection via standardized cosine ≥ 0.99'}
                  {c === 'ood' && 'Embedding distance vs 99th percentile of reference battery'}
                  {c === 'label_flip' && 'Predicted label conflicts with weak label key'}
                </span>
                <span className="status-badge st-pass">ENABLED</span>
              </div>
            ))}
          </div>
          <div className="divider" />
          <div className="di-footnote">
            Flagged samples generate evidence records whose SHA-256 digests are committed to the
            Fabric ledger through the bridge.
          </div>
        </GlassCard>
      </div>

      <GlassCard className="di-table-card">
        <div className="card-header">
          <h3>
            <ScanSearch size={15} className="hdr-icon" /> Flagged Samples
          </h3>
          <span className="text-muted" style={{ fontSize: 11.5 }}>{samples.length} shown</span>
        </div>
        <DataTable
          columns={[
            { key: 'sampleId', label: 'Sample ID', render: (r) => <span className="mono">{r.sampleId}</span> },
            {
              key: 'detectionType',
              label: 'Detection Type',
              render: (r) => <span className="type-chip mono">{r.detectionType}</span>
            },
            { key: 'confidence', label: 'Confidence', render: (r) => `${(r.confidence * 100).toFixed(0)}%` },
            { key: 'severity', label: 'Severity', render: (r) => <SeverityBadge severity={r.severity} /> },
            { key: 'disposition', label: 'Disposition', render: (r) => <DispositionBadge disposition={r.disposition} /> },
            {
              key: 'evidenceHash',
              label: 'Evidence Hash',
              render: (r) => (
                <span className="hash-chip" title={r.evidenceHash}>
                  {r.evidenceHash.slice(0, 12)}…
                </span>
              )
            },
            { key: 'timestamp', label: 'Timestamp', render: (r) => fmtTime(r.timestamp) }
          ]}
          rows={samples}
        />
      </GlassCard>
    </div>
  );
}
