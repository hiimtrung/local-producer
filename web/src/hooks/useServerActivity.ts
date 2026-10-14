// What the server is doing, for the header: its status and the active jobs. Polled every second while something
// runs or waits (so progress moves), every 3 s when idle.
import { useState } from "react";
import { type ApiError, api, isActive, type Job, type SystemInfo } from "../api/client";
import { usePoll } from "./usePoll";

export interface ServerActivity {
  system: SystemInfo | null;
  error: ApiError | null;
  /** Running first, then queued in queue order. */
  active: Job[];
}

const order = (j: Job) => (j.state === "running" ? -1 : (j.queue_position ?? 0));

export function useServerActivity(): ServerActivity {
  const [busy, setBusy] = useState(false);
  const interval = busy ? 1000 : 3000;
  const system = usePoll(api.system, interval, [interval]);
  const jobs = usePoll(
    async () => {
      const list = (await api.jobs(20)).filter(isActive).sort((a, b) => order(a) - order(b));
      setBusy(list.length > 0);
      return list;
    },
    interval,
    [interval],
  );
  return { system: system.data, error: system.error ?? jobs.error, active: jobs.data ?? [] };
}
