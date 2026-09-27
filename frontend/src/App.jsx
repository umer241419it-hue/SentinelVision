import { useCallback, useEffect, useState } from 'react';
import { Routes, Route, BrowserRouter, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import DashboardLayout from './layouts/DashboardLayout';
import Overview from './pages/Overview';
import DriftMonitor from './pages/DriftMonitor';
import DataIntegrity from './pages/DataIntegrity';
import DatasetValidation from './pages/DatasetValidation';
import ModelIntegrity from './pages/ModelIntegrity';
import Findings from './pages/Findings';
import EvidenceVault from './pages/EvidenceVault';
import FabricLedger from './pages/FabricLedger';
import SystemHealth from './pages/SystemHealth';
import Settings from './pages/Settings';
import Login from './pages/Login';
import Register from './pages/Register';
import AnalystWorkspace from './pages/AnalystWorkspace';
import QuarantineReview from './pages/QuarantineReview';
import LedgerTransactions from './pages/LedgerTransactions';
import GovernanceReports from './pages/GovernanceReports';
import SystemLogs from './pages/SystemLogs';
import UserSessions from './pages/UserSessions';
import FindingDrawer from './components/FindingDrawer';
import ToastHost from './components/ToastHost';
import { getBridgeStatus, getFindingById, getFindings } from './services/api';

function fmtTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

/** Gate: unauthenticated visitors are redirected to /login. */
function RequireAuth({ children }) {
  const { user, booting } = useAuth();
  const location = useLocation();
  if (booting) {
    return (
      <div className="auth-boot mono">
        <span className="auth-boot-dot" /> ESTABLISHING SECURE SESSION…
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}

/** Gate: page is only reachable by the listed roles (UI-level RBAC).
 *  The bridge independently enforces the same rules server-side. */
function RequireRole({ roles, children }) {
  const { user } = useAuth();
  if (user && roles.includes(user.role)) return children;
  return <Navigate to="/" replace />;
}

/** Redirects authenticated users away from the auth screens. */
function RedirectIfAuthed({ children }) {
  const { user, booting } = useAuth();
  if (!booting && user) return <Navigate to="/" replace />;
  return children;
}

function Dashboard({ bridgeStatus, fabricStatus, notifications, onOpenFinding }) {
  const { user, logout } = useAuth();
  return (
    <DashboardLayout
      bridgeStatus={bridgeStatus}
      fabricStatus={fabricStatus}
      notifications={notifications}
      onOpenFinding={onOpenFinding}
      user={user}
      onLogout={logout}
    />
  );
}

export default function App() {
  const [bridgeStatus, setBridgeStatus] = useState('UP');
  const [fabricStatus, setFabricStatus] = useState('CONNECTED');
  const [notifications, setNotifications] = useState([]);
  const [findingTarget, setFindingTarget] = useState(null);
  const [drawerFinding, setDrawerFinding] = useState(null);
  const [toasts, setToasts] = useState([]);

  const notify = useCallback((message, type = 'info') => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, message, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);

  // Status polling (bridge + fabric). Mock service responds instantly;
  // when wired to the real bridge this reflects actual /health results.
  useEffect(() => {
    let live = true;
    const poll = () =>
      getBridgeStatus().then((s) => {
        if (!live) return;
        setBridgeStatus(s.status === 'DOWN' ? 'DOWN' : 'UP');
        setFabricStatus(s.status === 'DOWN' ? 'DISCONNECTED' : 'CONNECTED');
      });
    poll();
    const iv = setInterval(poll, 30000);
    return () => {
      live = false;
      clearInterval(iv);
    };
  }, []);

  // Seed notifications from the most severe findings.
  useEffect(() => {
    let live = true;
    getFindings().then((findings) => {
      if (!live) return;
      const crit = findings.filter((f) => f.severity === 'CRITICAL' || f.severity === 'HIGH');
      setNotifications(
        crit.slice(0, 6).map((f) => ({
          title: `${f.severity} · ${f.moduleName}: ${f.reason.slice(0, 56)}…`,
          severity: f.severity,
          time: fmtTime(f.timestamp),
          findingId: f.id,
          read: false
        }))
      );
    });
    return () => {
      live = false;
    };
  }, []);

  // Resolve a finding identifier (from search/notifications) to full record.
  const openFindingById = useCallback((idOrAsset) => {
    setFindingTarget({ target: idOrAsset, ts: Date.now() });
    getFindingById(idOrAsset).then((f) => {
      if (f) setDrawerFinding(f);
      else notify(`No finding found for "${idOrAsset}"`, 'error');
    });
  }, [notify]);

  return (
    <AuthProvider>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          {/* Public: authentication screens */}
          <Route path="/login" element={<RedirectIfAuthed><Login /></RedirectIfAuthed>} />
          <Route path="/register" element={<RedirectIfAuthed><Register /></RedirectIfAuthed>} />

          {/* Protected: command center */}
          <Route
            element={
              <RequireAuth>
                <Dashboard
                  bridgeStatus={bridgeStatus}
                  fabricStatus={fabricStatus}
                  notifications={notifications}
                  onOpenFinding={openFindingById}
                />
              </RequireAuth>
            }
          >
            <Route path="/" element={<Overview onOpenFinding={openFindingById} />} />

            {/* Analyst-only */}
            <Route path="/workspace" element={<RequireRole roles={['ANALYST']}><AnalystWorkspace notify={notify} /></RequireRole>} />
            <Route path="/drift-monitor" element={<RequireRole roles={['ANALYST']}><DriftMonitor /></RequireRole>} />
            <Route path="/data-integrity" element={<RequireRole roles={['ANALYST']}><DataIntegrity /></RequireRole>} />
            <Route path="/dataset-validation" element={<RequireRole roles={['ANALYST']}><DatasetValidation notify={notify} /></RequireRole>} />
            <Route path="/model-integrity" element={<RequireRole roles={['ANALYST']}><ModelIntegrity /></RequireRole>} />

            {/* Shared */}
            <Route path="/findings" element={<Findings onOpenFinding={findingTarget} />} />
            <Route
              path="/evidence-vault"
              element={<EvidenceVault notify={notify} />}
            />

            {/* Auditor-only */}
            <Route path="/quarantine-review" element={<RequireRole roles={['AUDITOR']}><QuarantineReview notify={notify} /></RequireRole>} />
            <Route path="/ledger" element={<RequireRole roles={['AUDITOR']}><LedgerTransactions notify={notify} /></RequireRole>} />
            <Route path="/governance-reports" element={<RequireRole roles={['AUDITOR']}><GovernanceReports notify={notify} /></RequireRole>} />
            <Route path="/system-logs" element={<RequireRole roles={['AUDITOR']}><SystemLogs notify={notify} /></RequireRole>} />
            <Route path="/user-sessions" element={<RequireRole roles={['AUDITOR']}><UserSessions notify={notify} /></RequireRole>} />

            {/* Shared operations */}
            <Route
              path="/system-health"
              element={<SystemHealth notify={notify} />}
            />
            <Route path="/settings" element={<Settings notify={notify} />} />
            <Route path="/fabric-ledger" element={<FabricLedger />} />
            <Route path="*" element={<Overview onOpenFinding={openFindingById} />} />
          </Route>
        </Routes>

        <FindingDrawer finding={drawerFinding} onClose={() => setDrawerFinding(null)} />
        <ToastHost toasts={toasts} />
      </BrowserRouter>
    </AuthProvider>
  );
}
