import { useState } from 'react';
import { Settings as SettingsIcon, Server, Link2, Bell, Palette, Info, Save, Sun, Moon } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import GlassCard from '../components/GlassCard';
import { getBridgeStatus } from '../services/api';
import './Settings.css';

export default function Settings({ notify }) {
  const [bridgeUrl, setBridgeUrl] = useState('http://127.0.0.1:3000');
  const [fabricCfg, setFabricCfg] = useState({ channel: 'mychannel', chaincode: 'basic' });
  const [notifPrefs, setNotifPrefs] = useState({
    critical: true,
    high: true,
    medium: false,
    ledger: true,
    sound: false
  });
  const [saving, setSaving] = useState(false);
  const { theme, setTheme, accent, setAccent } = useTheme();

  const save = async () => {
    setSaving(true);
    await getBridgeStatus(); // probe (mock)
    await new Promise((r) => setTimeout(r, 500));
    setSaving(false);
    notify?.('Settings saved (frontend preferences only)', 'success');
  };

  return (
    <div className="anim-fade">
      <div className="settings-grid">
        {/* Backend/API */}
        <GlassCard>
          <div className="card-header">
            <h3>
              <Server size={15} className="hdr-icon" /> Backend / API Connection
            </h3>
          </div>
          <label className="set-label" htmlFor="bridge-url">Bridge base URL</label>
          <input
            id="bridge-url"
            className="set-input mono"
            value={bridgeUrl}
            onChange={(e) => setBridgeUrl(e.target.value)}
          />
          <p className="set-hint">
            The Express bridge (bridge/src/index.js) exposes <span className="mono">GET /health</span>,{' '}
            <span className="mono">POST /findings</span> and{' '}
            <span className="mono">GET /findings/:id</span>. The UI service layer targets these
            endpoints when mock mode is disabled.
          </p>
        </GlassCard>

        {/* Fabric */}
        <GlassCard>
          <div className="card-header">
            <h3>
              <Link2 size={15} className="hdr-icon" /> Fabric Connection
            </h3>
          </div>
          <div className="set-two-col">
            <div>
              <label className="set-label" htmlFor="ch">Channel</label>
              <input
                id="ch"
                className="set-input mono"
                value={fabricCfg.channel}
                onChange={(e) => setFabricCfg({ ...fabricCfg, channel: e.target.value })}
              />
            </div>
            <div>
              <label className="set-label" htmlFor="cc">Chaincode</label>
              <input
                id="cc"
                className="set-input mono"
                value={fabricCfg.chaincode}
                onChange={(e) => setFabricCfg({ ...fabricCfg, chaincode: e.target.value })}
              />
            </div>
          </div>
          <p className="set-hint">
            Defaults mirror the bridge environment (CHANNEL_NAME / CHAINCODE_NAME). Changing these
            values here only affects this UI's display labels.
          </p>
        </GlassCard>

        {/* Notifications */}
        <GlassCard>
          <div className="card-header">
            <h3>
              <Bell size={15} className="hdr-icon" /> Notification Preferences
            </h3>
          </div>
          <div className="toggle-list">
            {[
              ['critical', 'Critical findings'],
              ['high', 'High severity findings'],
              ['medium', 'Medium severity findings'],
              ['ledger', 'Ledger commit confirmations'],
              ['sound', 'Play alert sound']
            ].map(([key, label]) => (
              <div key={key} className="toggle-row">
                <span className="toggle-label">{label}</span>
                <button
                  className={`neo-toggle ${notifPrefs[key] ? 'on' : ''}`}
                  role="switch"
                  aria-checked={notifPrefs[key]}
                  aria-label={label}
                  onClick={() => setNotifPrefs((p) => ({ ...p, [key]: !p[key] }))}
                >
                  <span className="neo-toggle-thumb" />
                </button>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Appearance */}
        <GlassCard>
          <div className="card-header">
            <h3>
              <Palette size={15} className="hdr-icon" /> Appearance
            </h3>
          </div>
          <label className="set-label">Theme</label>
          <div className="theme-toggle-row">
            <button
              className={`theme-opt ${theme === 'light' ? 'active' : ''}`}
              onClick={() => setTheme('light')}
            >
              <Sun size={14} /> Light
            </button>
            <button
              className={`theme-opt ${theme === 'dark' ? 'active' : ''}`}
              onClick={() => setTheme('dark')}
            >
              <Moon size={14} /> Dark
            </button>
          </div>

          <label className="set-label">Accent color</label>
          <div className="accent-row">
            {[
              ['cyan', '#22d3ee'],
              ['violet', '#a78bfa'],
              ['blue', '#60a5fa'],
              ['green', '#34d399'],
              ['amber', '#fbbf24'],
              ['rose', '#fb7185']
            ].map(([name, color]) => (
              <button
                key={name}
                className={`accent-swatch ${accent === name ? 'active' : ''}`}
                style={{ '--sw': color }}
                onClick={() => setAccent(name)}
                aria-label={`${name} accent`}
                title={`${name[0].toUpperCase()}${name.slice(1)} accent`}
              />
            ))}
          </div>
          <p className="set-hint">
            Theme and accent preferences apply instantly and persist between launches.
          </p>
        </GlassCard>

        {/* App info */}
        <GlassCard className="app-info">
          <div className="card-header">
            <h3>
              <Info size={15} className="hdr-icon" /> Application Information
            </h3>
          </div>
          <div className="info-grid">
            <div><span className="meta-k">Product</span><span className="meta-v">SentinelVision Command Center</span></div>
            <div><span className="meta-k">Version</span><span className="meta-v mono">1.0.0</span></div>
            <div>
              <span className="meta-k">Runtime</span>
              <span className="meta-v mono">
                {window.sentinel?.isElectron
                  ? `Electron ${window.sentinel.versions.electron}`
                  : 'Browser (Vite dev)'}
              </span>
            </div>
            <div><span className="meta-k">Modules</span><span className="meta-v">DriftMonitor · DataIntegrity · ModelIntegrity</span></div>
            <div><span className="meta-k">Ledger</span><span className="meta-v">Hyperledger Fabric (fabric-gateway)</span></div>
          </div>
        </GlassCard>

        {/* Save */}
        <GlassCard className="save-card">
          <div className="save-inner">
            <SettingsIcon size={18} className="save-icon" />
            <div>
              <div className="save-title">Preferences</div>
              <div className="save-sub">Stored locally in this UI session</div>
            </div>
            <button className="hud-btn primary" onClick={save} disabled={saving}>
              <Save size={13} />
              {saving ? 'Saving…' : 'Save Changes'}
            </button>
          </div>
        </GlassCard>
      </div>
    </div>
  );
}
