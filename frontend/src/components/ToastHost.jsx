import { CheckCircle2, AlertTriangle, Info, XCircle } from 'lucide-react';
import './ToastHost.css';

const ICONS = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info
};

export default function ToastHost({ toasts }) {
  if (!toasts.length) return null;
  return (
    <div className="toast-host" role="status" aria-live="polite">
      {toasts.map((t) => {
        const Icon = ICONS[t.type] || Info;
        return (
          <div key={t.id} className={`toast toast-${t.type}`}>
            <Icon size={15} />
            <span>{t.message}</span>
          </div>
        );
      })}
    </div>
  );
}
