// Follow one job: poll every second while it is queued or running; tell the caller when it finishes.
import { useEffect, useRef, useState } from "react";
import { api, isActive, type Job } from "../api/client";

export function useJob(id: string | null): Job | null {
  const [job, setJob] = useState<Job | null>(null);
  useEffect(() => {
    if (!id) {
      setJob(null);
      return undefined;
    }
    let stop = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const j = await api.job(id);
        if (stop) return;
        setJob(j);
        if (isActive(j)) timer = setTimeout(tick, 1000);
      } catch {
        if (!stop) timer = setTimeout(tick, 3000);
      }
    };
    void tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [id]);
  return job;
}

/** Calls onFinish once when a job that was queued or running while watched reaches a final state. */
export function useJobFinished(job: Job | null, onFinish: (job: Job) => void): void {
  const last = useRef<Job["state"] | undefined>(undefined);
  const callback = useRef(onFinish);
  callback.current = onFinish;
  useEffect(() => {
    const was = last.current;
    last.current = job?.state;
    if (job && (was === "queued" || was === "running") && !isActive(job)) callback.current(job);
  }, [job]);
}

/** Runs once with the job that matches `id` (e.g. a result opened from the library) to restore its settings. */
export function useRestore(job: Job | null, id: string | undefined, restore: (job: Job) => void): void {
  const done = useRef(false);
  const callback = useRef(restore);
  callback.current = restore;
  useEffect(() => {
    if (!job || done.current || job.id !== id) return;
    done.current = true;
    callback.current(job);
  }, [job, id]);
}
