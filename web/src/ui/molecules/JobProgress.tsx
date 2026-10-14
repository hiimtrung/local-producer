// A running job as a glass capsule: what it is doing, how far, how long, and a way to stop it.
import { useEffect, useState } from "react";
import { api, isActive, type Job } from "../../api/client";
import { duration, jobElapsed } from "../../lib/format";
import { Button, Progress } from "../atoms";

function stageText(job: Job): string {
  if (job.state === "queued") {
    const ahead = (job.queue_position ?? 1) - 1;
    return ahead > 0 ? `Waiting for ${ahead} job(s) ahead` : "Starting";
  }
  const p = job.progress;
  const step = p.steps ? `, step ${p.step ?? 0} of ${p.steps}` : "";
  return `${p.stage ?? "Working"}${step}`;
}

export function JobProgress({ job }: { job: Job }) {
  const [, tick] = useState(0);
  const active = isActive(job);
  useEffect(() => {
    if (!active) return undefined;
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [active]);
  if (!active) return null;
  const fraction = job.progress.fraction;
  return (
    <div className="job-progress lg-glass lg-glass--thick lg-r-capsule" role="status">
      <div className="job-progress__text">
        <span className="subheadline">{stageText(job)}</span>
        <span className="footnote muted">{duration(jobElapsed(job) ?? 0)}</span>
      </div>
      <Progress
        value={fraction != null ? Math.round(fraction * 100) : undefined}
        indeterminate={fraction == null}
        label="Progress"
      />
      <Button size="sm" variant="plain" onClick={() => void api.cancel(job.id)}>
        Cancel
      </Button>
    </div>
  );
}
