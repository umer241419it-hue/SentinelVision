import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Radar, DatabaseZap, ScanFace, ListChecks, Vault,
  Link2, HeartPulse, Settings, ShieldCheck, UploadCloud, Gavel,
  ScrollText, Users, FileBarChart, FileCheck2, Building2, PlugZap
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import './Sidebar.css';

// Role-scoped navigation (task spec §29). `roles` gates visibility in the UI;
// backend authorization is enforced independently by the bridge.
const NAV = [
  // Shared
  { to: '/', label: 'Overview', code: 'SYS-01', icon: LayoutDashboard, end: true, roles: ['ANALYST', 'AUDITOR'] },
  // Analyst modules
  { to: '/workspace', label: 'Upload / Trustworthiness', code: 'ANA-01', icon: UploadCloud, roles: ['ANALYST'] },
  { to: '/drift-monitor', label: 'Drift Monitor', code: 'ANA-02', icon: Radar, roles: ['ANALYST'] },
  { to: '/data-integrity', label: 'Data Integrity', code: 'ANA-03', icon: DatabaseZap, roles: ['ANALYST'] },
  { to: '/dataset-validation', label: 'Dataset Validation', code: 'ANA-05', icon: FileCheck2, roles: ['ANALYST'] },
  { to: '/model-validation', label: 'Model Validation', code: 'ANA-06', icon: FileCheck2, roles: ['ANALYST'] },
  { to: '/model-hooks', label: 'Model Hooks', code: 'ANA-07', icon: PlugZap, roles: ['ANALYST'] },
  { to: '/model-integrity', label: 'Model Integrity', code: 'ANA-04', icon: ScanFace, roles: ['ANALYST'] },
  // Shared
  { to: '/contributors', label: 'Contributors / Vendors', code: 'SHR-04', icon: Building2, roles: ['ANALYST', 'AUDITOR'] },
  { to: '/findings', label: 'Findings', code: 'SHR-05', icon: ListChecks, roles: ['ANALYST', 'AUDITOR'] },
  { to: '/evidence-vault', label: 'Evidence Vault', code: 'SHR-06', icon: Vault, roles: ['ANALYST', 'AUDITOR'] },
  // Auditor modules
  { to: '/quarantine-review', label: 'Quarantine Review', code: 'AUD-01', icon: Gavel, roles: ['AUDITOR'] },
  { to: '/ledger', label: 'Fabric Ledger', code: 'AUD-02', icon: Link2, roles: ['AUDITOR'] },
  { to: '/governance-reports', label: 'Governance Reports', code: 'AUD-03', icon: FileBarChart, roles: ['AUDITOR'] },
  { to: '/system-logs', label: 'System Logs', code: 'AUD-04', icon: ScrollText, roles: ['AUDITOR'] },
  { to: '/user-sessions', label: 'User Sessions', code: 'AUD-05', icon: Users, roles: ['AUDITOR'] },
  // Shared
  { to: '/system-health', label: 'System Health', code: 'SHR-08', icon: HeartPulse, roles: ['ANALYST', 'AUDITOR'] },
  { to: '/settings', label: 'Settings', code: 'SHR-09', icon: Settings, roles: ['ANALYST', 'AUDITOR'] }
];

/**
 * HUDSidebar — technical navigation panel; items are filtered by the
 * authenticated user's role. Server-side RBAC still guards every endpoint.
 */
export default function Sidebar({ bridgeStatus, fabricStatus }) {
  const { user } = useAuth();
  const role = user?.role || 'ANALYST';
  const items = NAV.filter((n) => n.roles.includes(role));

  return (
    <aside className="sidebar">
      <div className="sb-logo">
        <div className="sb-logo-mark">
          <ShieldCheck size={19} strokeWidth={2} />
        </div>
        <div className="sb-logo-text">
          <span className="sb-logo-name">SENTINELVISION</span>
          <span className="sb-logo-sub">AI SECURITY · v2.0</span>
        </div>
      </div>

      <div className="sb-section-label">{role} Modules</div>

      <nav className="sb-nav">
        {items.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `sb-item ${isActive ? 'active' : ''}`}
          >
            <Icon size={15} strokeWidth={1.9} />
            <span className="sb-item-label">{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="sb-footer">
        <div className="sb-section-label">Systems</div>
        <div className="sb-status">
          <div className="sb-status-row">
            <span className={`status-dot ${bridgeStatus === 'UP' ? 'ok' : 'err'}`} />
            <span className="sb-status-label">API LINK</span>
            <span className="sb-status-val">{bridgeStatus === 'UP' ? 'ONLINE' : 'OFFLINE'}</span>
          </div>
          <div className="sb-status-row">
            <span className={`status-dot ${fabricStatus === 'CONNECTED' ? 'ok' : 'warn'}`} />
            <span className="sb-status-label">FABRIC</span>
            <span className="sb-status-val">{fabricStatus}</span>
          </div>
          <div className="sb-status-row">
            <span className="status-dot info" />
            <span className="sb-status-label">ROLE</span>
            <span className="sb-status-val">{role}</span>
          </div>
        </div>
        <div className="sb-user">
          <div className="sb-avatar">
            {(user?.fullName || '??').split(/\s+/).map((p) => p[0]).join('').slice(0, 2).toUpperCase()}
          </div>
          <div className="sb-user-text">
            <div className="sb-user-name">{role} · {(user?.fullName || '—').split(/\s+/)[0]?.toUpperCase()}</div>
            <div className="sb-user-role">{user?.email || 'NO SESSION'}</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
