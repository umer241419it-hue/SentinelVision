import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { UserPlus, Loader2, AlertTriangle, CheckCircle2, Circle, ShieldCheck } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { passwordStrength } from '../services/authApi';
import './Auth.css';

/**
 * Register — HUD/Sci-Fi operator enrollment.
 * Bridges to POST /api/auth/register (password hashed server-side with bcrypt;
 * only the hash is stored — the API never returns password material).
 * AUDITOR registrations follow the bridge policy: APPROVAL puts them PENDING.
 */
export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    fullName: '',
    email: '',
    password: '',
    confirmPassword: '',
    role: 'ANALYST'
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const strength = useMemo(() => passwordStrength(form.password), [form.password]);

  const passwordsMatch =
    !form.confirmPassword || form.password === form.confirmPassword;

  function setField(k, v) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function onSubmit(e) {
    e.preventDefault();
    setError('');
    setNotice('');

    if (!passwordsMatch) {
      setError('Passwords do not match.');
      return;
    }
    if (strength.score < 4) {
      setError('Password too weak — satisfy at least: 8+ chars, uppercase, lowercase, digit.');
      return;
    }

    setBusy(true);
    try {
      const data = await register(form);
      if (data.pending) {
        setNotice(
          'Registration received. AUDITOR accounts require approval by an existing auditor before activation.'
        );
        setTimeout(() => navigate('/login'), 2600);
      } else {
        navigate('/login', {
          state: { registered: data.user?.email || form.email }
        });
      }
    } catch (err) {
      if (err.status === 409) setError('An account with this email already exists.');
      else if (err.status === 400) setError(err.message || 'Validation failed.');
      else setError(err.message || 'Registration failed.');
    } finally {
      setBusy(false);
    }
  }

  const canSubmit =
    form.fullName.trim().length >= 2 &&
    /\S+@\S+\.\S+/.test(form.email) &&
    strength.score >= 4 &&
    form.password === form.confirmPassword &&
    !busy;

  return (
    <div className="auth-shell">
      <div className="auth-frame wide">
        <span className="hud-corner tl" />
        <span className="hud-corner tr" />
        <span className="hud-corner bl" />
        <span className="hud-corner br" />

        <div className="auth-head">
          <div className="auth-sigil">
            <UserPlus size={22} strokeWidth={1.6} />
          </div>
          <h1 className="auth-title">OPERATOR ENROLLMENT</h1>
          <p className="auth-tagline">SENTINELVISION · NEW ACCOUNT PROVISIONING</p>
        </div>

        <form className="auth-form" onSubmit={onSubmit} noValidate>
          <label className="auth-field">
            <span className="auth-label">FULL NAME</span>
            <input
              type="text"
              value={form.fullName}
              onChange={(e) => setField('fullName', e.target.value)}
              placeholder="e.g. Maria Imran"
              autoComplete="name"
              autoFocus
              required
            />
          </label>

          <label className="auth-field">
            <span className="auth-label">EMAIL</span>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setField('email', e.target.value)}
              placeholder="operator@sentinelvision.io"
              autoComplete="email"
              required
            />
          </label>

          <div className="auth-field-row">
            <label className="auth-field">
              <span className="auth-label">PASSWORD</span>
              <input
                type="password"
                value={form.password}
                onChange={(e) => setField('password', e.target.value)}
                placeholder="••••••••••••"
                autoComplete="new-password"
                required
              />
            </label>
            <label className="auth-field">
              <span className="auth-label">CONFIRM PASSWORD</span>
              <input
                type="password"
                value={form.confirmPassword}
                onChange={(e) => setField('confirmPassword', e.target.value)}
                placeholder="••••••••••••"
                autoComplete="new-password"
                required
              />
            </label>
          </div>

          {/* Live password strength meter */}
          <div className={`auth-strength s${strength.score}`}>
            <div className="auth-strength-bars">
              {[1, 2, 3, 4, 5].map((i) => (
                <span key={i} className={strength.score >= i ? 'on' : ''} />
              ))}
            </div>
            <span className="auth-strength-label mono">
              {form.password ? strength.label : 'STRENGTH'}
            </span>
          </div>
          <div className="auth-strength-checks">
            {strength.checks.map((c) => (
              <span key={c.label} className={`auth-check ${c.ok ? 'ok' : ''}`}>
                {c.ok ? <CheckCircle2 size={11} /> : <Circle size={11} />} {c.label}
              </span>
            ))}
          </div>

          <div className="auth-field">
            <span className="auth-label">ROLE</span>
            <div className="auth-roles">
              <button
                type="button"
                className={`auth-role ${form.role === 'ANALYST' ? 'selected' : ''}`}
                onClick={() => setField('role', 'ANALYST')}
              >
                <strong>ANALYST</strong>
                <span>Upload datasets &amp; models · run trust checks · submit for review</span>
              </button>
              <button
                type="button"
                className={`auth-role ${form.role === 'AUDITOR' ? 'selected' : ''}`}
                onClick={() => setField('role', 'AUDITOR')}
              >
                <strong>AUDITOR</strong>
                <span>Governance · quarantine review · ledger commit (requires approval)</span>
              </button>
            </div>
          </div>

          {error && (
            <div className="auth-error" role="alert">
              <AlertTriangle size={13} />
              <span>{error}</span>
            </div>
          )}
          {notice && (
            <div className="auth-notice" role="status">
              <ShieldCheck size={13} />
              <span>{notice}</span>
            </div>
          )}
          {!passwordsMatch && (
            <div className="auth-error" role="alert">
              <AlertTriangle size={13} />
              <span>Passwords do not match.</span>
            </div>
          )}

          <button type="submit" className="auth-submit" disabled={!canSubmit}>
            {busy ? (
              <>
                <Loader2 size={14} className="spin" /> PROVISIONING…
              </>
            ) : (
              'CREATE ACCOUNT'
            )}
          </button>
        </form>

        <div className="auth-alt">
          <span>ALREADY CLEARED FOR ACCESS?</span>
          <Link to="/login">LOGIN →</Link>
        </div>

        <div className="auth-foot mono">
          <span>PASSWORDS · BCRYPT · NEVER STORED PLAINTEXT</span>
          <span>AUDITOR · APPROVAL POLICY</span>
        </div>
      </div>
    </div>
  );
}
