import { useState, useRef, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Search, Bell, Sun, Moon, Radio, LogOut } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import './Topbar.css';

const TITLES = {
  '/': { title: 'Overview', crumb: ['Command Center', 'Overview'] },
  '/workspace': { title: 'Analyst Workspace', crumb: ['Analyst Operations', 'Upload / Trustworthiness'] },
  '/drift-monitor': { title: 'Drift Monitor', crumb: ['Detection Modules', 'Drift Monitor'] },
  '/data-integrity': { title: 'Data Integrity', crumb: ['Detection Modules', 'Data Integrity'] },
  '/model-integrity': { title: 'Model Integrity', crumb: ['Detection Modules', 'Model Integrity'] },
  '/findings': { title: 'Findings', crumb: ['Investigation', 'Findings'] },
  '/evidence-vault': { title: 'Evidence Vault', crumb: ['Trust Layer', 'Evidence Vault'] },
  '/quarantine-review': { title: 'Quarantine Review', crumb: ['Governance', 'Quarantine Review'] },
  '/ledger': { title: 'Fabric Ledger', crumb: ['Governance', 'Fabric Ledger'] },
  '/governance-reports': { title: 'Governance Reports', crumb: ['Governance', 'Reports'] },
  '/system-logs': { title: 'System Logs', crumb: ['Governance', 'System Logs'] },
  '/user-sessions': { title: 'User Sessions', crumb: ['Governance', 'User Sessions'] },
  '/fabric-ledger': { title: 'Fabric Ledger', crumb: ['Trust Layer', 'Fabric Ledger'] },
  '/system-health': { title: 'System Health', crumb: ['Operations', 'System Health'] },
  '/settings': { title: 'Settings', crumb: ['Operations', 'Settings'] }
};

function HudClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const iv = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(iv);
  }, []);
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  const ss = String(now.getSeconds()).padStart(2, '0');
  return (
    <span className="tb-clock mono">
      T+ {hh}:{mm}
      <span className="tb-clock-sec">:{ss}</span>
    </span>
  );
}

/**
 * HUDTopbar — mission-control strip: identity block, system links,
 * live clock, search, link status pills, theme toggle, notifications.
 */
export default function Topbar({ bridgeStatus, fabricStatus, notifications, onOpenFinding, user, onLogout }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const meta = TITLES[pathname] || { title: 'SentinelVision', crumb: ['SentinelVision'] };
  const [showNotifs, setShowNotifs] = useState(false);
  const [query, setQuery] = useState('');
  const notifRef = useRef(null);
  const { theme, toggleTheme } = useTheme();

  useEffect(() => {
    const onClick = (e) => {
      if (notifRef.current && !notifRef.current.contains(e.target)) setShowNotifs(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const unread = notifications.filter((n) => !n.read).length;

  return (
    <header className="topbar">
      {/* Left: identity + systems strip */}
      <div className="tb-left">
        <div className="tb-identity">
          <span className="tb-wordmark">SENTINELVISION</span>
          <span className="tb-tagline">AI SECURITY MISSION CONTROL</span>
        </div>
        <div className="tb-systems mono">
          <span>SENTINELVISION-FABRIC-BRIDGE</span>
        </div>
      </div>

      {/* Right: controls */}
      <div className="tb-right">
        <HudClock />

        <div className="tb-search">
          <Search size={13} />
          <input
            type="text"
            placeholder="SEARCH FINDINGS / HASHES…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && query.trim() && onOpenFinding) {
                onOpenFinding(query.trim());
                setQuery('');
              }
            }}
          />
        </div>

        <div className="tb-pills">
          <span className="tb-pill">
            <span className={`status-dot ${bridgeStatus === 'UP' ? 'ok' : 'err'}`} />
            SYSTEM {bridgeStatus === 'UP' ? 'ONLINE' : 'OFFLINE'}
          </span>
          <span className="tb-pill">
            <Radio size={11} className={fabricStatus === 'CONNECTED' ? 'tb-radio-ok' : ''} />
            FABRIC {fabricStatus}
          </span>
        </div>

        <button
          className="hud-btn icon-only tb-theme-btn"
          onClick={toggleTheme}
          title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          aria-label="Toggle color theme"
        >
          {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
        </button>

        <div className="tb-notifs" ref={notifRef}>
          <button className="hud-btn icon-only" onClick={() => setShowNotifs((s) => !s)} aria-label="Notifications">
            <Bell size={14} />
            {unread > 0 && <span className="tb-badge">{unread}</span>}
          </button>
          {showNotifs && (
            <div className="notif-panel">
              <div className="notif-head">
                <span>// TRANSMISSIONS</span>
                <span className="text-muted">{unread} NEW</span>
              </div>
              <div className="notif-list">
                {notifications.length === 0 && <div className="notif-empty">NO NOTIFICATIONS</div>}
                {notifications.slice(0, 8).map((n, i) => (
                  <button
                    key={i}
                    className={`notif-item ${n.read ? 'read' : ''}`}
                    onClick={() => {
                      if (n.findingId && onOpenFinding) onOpenFinding(n.findingId);
                      setShowNotifs(false);
                    }}
                  >
                    <span className={`notif-dot sev-${n.severity.toLowerCase()}`} />
                    <span className="notif-text">
                      <span className="notif-title">{n.title}</span>
                      <span className="notif-time">{n.time}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Authenticated user identity block */}
        {user ? (
          <div className="tb-user" title={user.email}>
            <div className="tb-user-meta">
              <span className="tb-user-name">{user.fullName}</span>
              <span className={`tb-user-status mono ${user.role === 'AUDITOR' ? 'gov' : 'act'}`}>
                ● {user.role}
              </span>
            </div>
            <div className="tb-avatar">{user.fullName.split(/\s+/).map((p) => p[0]).join('').slice(0, 2).toUpperCase()}</div>
            <button
              className="hud-btn icon-only tb-logout"
              onClick={async () => {
                await onLogout?.();
                navigate('/login', { replace: true });
              }}
              title="Log out"
              aria-label="Log out"
            >
              <LogOut size={14} />
            </button>
          </div>
        ) : (
          <div className="tb-avatar">--</div>
        )}
      </div>
    </header>
  );
}
