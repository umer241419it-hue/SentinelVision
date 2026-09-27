import { ArrowUpRight, ArrowDownRight } from 'lucide-react';
import GlassCard from './GlassCard';
import Sparkline from './Sparkline';
import './MetricCard.css';

/**
 * HUDMetric (legacy name: MetricCard) — technical metric panel with
 * HUD label, large value, status tag, trend and tiny sparkline.
 */
export default function MetricCard({
  icon: Icon,
  label,
  value,
  status,
  trend,
  up,
  sparkColor = '#22d3ee',
  sparkData = []
}) {
  return (
    <GlassCard className="metric-card clickable" corners={false}>
      <div className="metric-inner">
        <div className="metric-top">
          <div className="metric-icon">
            <Icon size={15} strokeWidth={1.9} />
          </div>
          <span className="metric-hud-label">{label}</span>
          {sparkData.length > 0 && <Sparkline data={sparkData} color={sparkColor} width={92} height={26} />}
        </div>
        <div className="hud-metric-value">{value}</div>
        <div className="metric-bottom">
          {status && <span className="metric-status">{status}</span>}
          {trend && (
            <span className={`metric-trend ${up ? 'up' : 'down'}`}>
              {up ? <ArrowUpRight size={11} /> : <ArrowDownRight size={11} />}
              {trend}
            </span>
          )}
        </div>
      </div>
    </GlassCard>
  );
}
