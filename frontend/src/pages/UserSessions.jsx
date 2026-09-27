import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, UserCheck, UserX } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { listSessions, listUsers, setUserStatus, approvePendingUser } from '../services/workflowApi';
import './AuditorPages.css';

/**
 * UserSessions — auditor-only session directory + account administration
 * (task spec §26). Never shows password material — the API doesn't return it.
 */
export default function UserSessions({ notify }) {
  const [sessions, setSessions] = useState([]);
  const [users, setUsers] = useState([]);
  const [tab, setTab] = useState('sessions');
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [s, u] = await Promise.all([listSessions(), listUsers()]);
      setSessions(s);
      setUsers(u);
    } catch (err) {
      notify?.(err.message, 'error');
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function act(fn, okMsg) {
    try {
      await fn();
      notify?.(okMsg, 'success');
      await refresh();
    } catch (err) {
      notify?.(err.message, 'error');
    }
  }

  const pending = users.filter((u) => u.accountStatus === 'PENDING');

  return (
    <div className="anim-fade">
      <GlassCard>
        <div className="card-header">
          <h3>USER SESSIONS &amp; ACCOUNTS</h3>
          <div className="aud-toolbar">
            <div className="range-toggle">
              {['sessions', 'accounts'].map((tb) => (
                <button
                  key={tb}
                  className={`range-btn ${tab === tb ? 'active' : ''}`}
                  onClick={() => setTab(tb)}
                >
                  {tb.toUpperCase()}{tb === 'accounts' && pending.length > 0 ? ` · ${pending.length} PENDING` : ''}
                </button>
              ))}
            </div>
            <button className="hud-btn icon-only" onClick={refresh} title="Refresh">
              <RefreshCw size={13} />
            </button>
          </div>
        </div>

        {tab === 'sessions' && (
          <div className="aud-table-wrap">
            <table className="aud-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Login</th>
                  <th>Last activity</th>
                  <th>Logout</th>
                  <th>Status</th>
                  <th>IP</th>
                  <th>Device</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.sessionId}>
                    <td>{s.userName || s.userId}</td>
                    <td className="mono">{s.userRole || '—'}</td>
                    <td className="mono">{s.loginAt ? new Date(s.loginAt).toLocaleString() : '—'}</td>
                    <td className="mono">{s.lastActivityAt ? new Date(s.lastActivityAt).toLocaleString() : '—'}</td>
                    <td className="mono">{s.logoutAt ? new Date(s.logoutAt).toLocaleString() : '—'}</td>
                    <td>
                      <span className={`qr-act ${s.status === 'ACTIVE' ? 'ok' : ''}`} style={{ padding: '2px 8px', pointerEvents: 'none' }}>
                        {s.status}
                      </span>
                    </td>
                    <td className="mono">{s.ip || '—'}</td>
                    <td className="mono" title={s.device}>{(s.device || '—').slice(0, 34)}</td>
                  </tr>
                ))}
                {!loading && sessions.length === 0 && (
                  <tr><td colSpan={8} className="aw-empty">NO SESSIONS RECORDED</td></tr>
                )}
                {loading && <tr><td colSpan={8} className="aw-empty">LOADING…</td></tr>}
              </tbody>
            </table>
          </div>
        )}

        {tab === 'accounts' && (
          <div className="aud-table-wrap">
            <table className="aud-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Registered</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u._id}>
                    <td>{u.fullName}</td>
                    <td className="mono">{u.email}</td>
                    <td className="mono">{u.role}</td>
                    <td>
                      <span className={`qr-act ${u.accountStatus === 'ACTIVE' ? 'ok' : u.accountStatus === 'PENDING' ? 'warn' : 'crit'}`} style={{ padding: '2px 8px', pointerEvents: 'none' }}>
                        {u.accountStatus}
                      </span>
                    </td>
                    <td className="mono">{u.createdAt ? new Date(u.createdAt).toLocaleDateString() : '—'}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        {u.accountStatus === 'PENDING' && (
                          <button
                            className="qr-act ok"
                            onClick={() => act(() => approvePendingUser(u._id), `${u.fullName} approved.`)}
                          >
                            <UserCheck size={12} /> APPROVE
                          </button>
                        )}
                        {u.accountStatus === 'ACTIVE' && (
                          <button
                            className="qr-act crit"
                            onClick={() => act(() => setUserStatus(u._id, 'SUSPENDED'), `${u.fullName} suspended.`)}
                          >
                            <UserX size={12} /> SUSPEND
                          </button>
                        )}
                        {u.accountStatus === 'SUSPENDED' && (
                          <button
                            className="qr-act ok"
                            onClick={() => act(() => setUserStatus(u._id, 'ACTIVE'), `${u.fullName} re-activated.`)}
                          >
                            <UserCheck size={12} /> RE-ACTIVATE
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>
    </div>
  );
}
