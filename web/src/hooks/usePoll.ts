// Load data now and again every intervalMs while the page is visible (0 = once).
import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiError } from "../api/client";

export interface Polled<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => Promise<void>;
}

export function usePoll<T>(load: () => Promise<T>, intervalMs: number, deps: readonly unknown[] = []): Polled<T> {
  const [state, setState] = useState<Omit<Polled<T>, "reload">>({ data: null, error: null, loading: true });
  const loadRef = useRef(load);
  loadRef.current = load;
  const reload = useCallback(async () => {
    try {
      const data = await loadRef.current();
      setState({ data, error: null, loading: false });
    } catch (error) {
      setState((s) => ({ ...s, error: error as ApiError, loading: false }));
    }
  }, []);
  useEffect(() => {
    void reload();
    if (!intervalMs) return undefined;
    const t = setInterval(() => {
      if (!document.hidden) void reload();
    }, intervalMs);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, reload, ...deps]);
  return { ...state, reload };
}
