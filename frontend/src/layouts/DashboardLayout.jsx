import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import './DashboardLayout.css';

/**
 * DashboardLayout — persistent desktop shell: sidebar + topbar + routed content.
 * forwards the authenticated user + logout handler to the Topbar identity block.
 */
export default function DashboardLayout({
  bridgeStatus,
  fabricStatus,
  notifications,
  onOpenFinding,
  user,
  onLogout
}) {
  return (
    <div className="dash-shell">
      <Sidebar bridgeStatus={bridgeStatus} fabricStatus={fabricStatus} />
      <div className="dash-main">
        <Topbar
          bridgeStatus={bridgeStatus}
          fabricStatus={fabricStatus}
          notifications={notifications}
          onOpenFinding={onOpenFinding}
          user={user}
          onLogout={onLogout}
        />
        <main className="dash-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
