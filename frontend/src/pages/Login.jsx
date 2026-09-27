import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ShieldCheck, Loader2, AlertTriangle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import './Auth.css';

/**
 * Login — HUD/Sci-Fi authentication screen.
 * Bridges to POST /api/auth/login (bcrypt-hashed credentials, JWT session).
 */
export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function onSubmit(e) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await login(email.trim(), password);
      navigate('/', { replace: true });
    } catch (err) {
      const msg =
        err.status === 401
          ? 'Invalid credentials — access denied.'
          : err.status === 403
            ? err.message
            : err.status === 429
              ? 'Too many attempts. Wait 15 minutes and retry.'
              : err.message || 'Login failed.';
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-frame">
        {/* HUD corner brackets */}
        <span className="hud-corner tl" />
        <span className="hud-corner tr" />
        <span className="hud-corner bl" />
        <span className="hud-corner br" />

        <div className="auth-head">
          <div className="auth-sigil">
            <ShieldCheck size={22} strokeWidth={1.6} />
          </div>
          <h1 className="auth-title">SENTINELVISION</h1>
          <p className="auth-tagline">AI SECURITY MISSION CONTROL · OPERATOR ACCESS</p>
        </div>

        <form className="auth-form" onSubmit={onSubmit} noValidate>
          <label className="auth-field">
            <span className="auth-label">EMAIL</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="operator@sentinelvision.io"
              autoComplete="email"
              autoFocus
              required
            />
          </label>

          <label className="auth-field">
            <span className="auth-label">PASSWORD</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              autoComplete="current-password"
              required
            />
          </label>

          {error && (
            <div className="auth-error" role="alert">
              <AlertTriangle size={13} />
              <span>{error}</span>
            </div>
          )}

          <button type="submit" className="auth-submit" disabled={busy || !email || !password}>
            {busy ? (
              <>
                <Loader2 size={14} className="spin" /> AUTHENTICATING…
              </>
            ) : (
              'LOGIN'
            )}
          </button>
        </form>

        <div className="auth-alt">
          <span>NO OPERATOR ACCOUNT?</span>
          <Link to="/register">CREATE ACCOUNT →</Link>
        </div>

        <div className="auth-foot mono">
          <span>SESSION · JWT · 12H TTL</span>
          <span>CREDS · BCRYPT-HASHED</span>
        </div>
      </div>
    </div>
  );
}
