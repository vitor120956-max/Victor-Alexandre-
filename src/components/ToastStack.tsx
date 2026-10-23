import { Check, Info, TriangleAlert, X } from 'lucide-react';
import { useApp } from '../context/AppContext';

export function ToastStack() {
  const { toasts, dismissToast } = useApp();
  return (
    <div className="toast-stack" aria-live="polite">
      {toasts.map((toast) => {
        const Icon = toast.tone === 'warning' ? TriangleAlert : toast.tone === 'info' ? Info : Check;
        return (
          <div className={`toast toast-${toast.tone}`} key={toast.id}>
            <span className="toast-icon"><Icon size={17} /></span>
            <div>
              <strong>{toast.title}</strong>
              {toast.description && <p>{toast.description}</p>}
            </div>
            <button onClick={() => dismissToast(toast.id)} aria-label="Dispensar notificação"><X size={16} /></button>
          </div>
        );
      })}
    </div>
  );
}
