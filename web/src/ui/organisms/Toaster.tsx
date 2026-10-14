// App-wide notifications: Lucent toasts stacked at the bottom centre, hidden after 5 s (8 s for errors).
import { createContext, type ReactNode, useCallback, useContext, useState } from "react";
import { Toast, type ToastProps } from "../atoms";

type ToastTone = NonNullable<ToastProps["tone"]>;
export type ShowToast = (tone: ToastTone, title: string, message?: string) => void;

interface Item {
  id: string;
  tone: ToastTone;
  title: string;
  message: string | undefined;
}

const ToastContext = createContext<ShowToast>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Item[]>([]);
  const close = useCallback((id: string) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const show = useCallback<ShowToast>(
    (tone, title, message) => {
      const id = Math.random().toString(36).slice(2);
      setToasts((t) => [...t.slice(-2), { id, tone, title, message }]);
      setTimeout(() => close(id), tone === "danger" ? 8000 : 5000);
    },
    [close],
  );
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <Toast key={t.id} tone={t.tone} title={t.title} message={t.message} onClose={() => close(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
