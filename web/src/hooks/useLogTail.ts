// Follow the server's job log live: one tail, then only the lines written since (by byte offset), once a second
// while the page is visible. Keeps the newest `keep` lines.
import { useEffect, useRef, useState } from "react";
import { api, type ApiError } from "../api/client";

export interface LogTail {
  lines: string[];
  error: ApiError | null;
  /** Lines received since the tail was loaded, for a "new lines" hint. */
  received: number;
}

export function useLogTail(intervalMs = 1000, keep = 5000): LogTail {
  const [state, setState] = useState<LogTail>({ lines: [], error: null, received: 0 });
  const offset = useRef<number | undefined>(undefined);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      if (!document.hidden) {
        try {
          const r = await api.logs(Math.min(keep, 2000), offset.current);
          if (cancelled) return;
          offset.current = r.offset;
          if (r.reset) setState({ lines: r.lines, error: null, received: 0 });
          else if (r.lines.length) {
            setState((s) => ({
              lines: [...s.lines, ...r.lines].slice(-keep),
              error: null,
              received: s.received + r.lines.length,
            }));
          } else setState((s) => (s.error ? { ...s, error: null } : s));
        } catch (e) {
          if (!cancelled) setState((s) => ({ ...s, error: e as ApiError }));
        }
      }
      if (!cancelled) timer = setTimeout(() => void poll(), intervalMs);
    };
    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [intervalMs, keep]);
  return state;
}
