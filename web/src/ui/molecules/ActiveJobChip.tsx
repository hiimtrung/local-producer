// The job the server is working on, for the header: what, which stage, how far, for how long, and how many wait
// behind it. Links to where its result will show.
import { useEffect, useState } from "react";
import type { Job } from "../../api/client";
import { duration, jobElapsed, kindLabel } from "../../lib/format";
import { AppIcon, type AppIconName, ProgressRing } from "../atoms";

const ICONS: Record<string, AppIconName> = {
  "image.generate": "image",
  "image.edit": "image",
  "image.matte": "tools",
  "mesh.generate": "cube",
};

/** Where a job's result is shown: its creation page, or the library. */
export function jobHref(job: Job): string {
  if (job.kind.startsWith("image.") && job.kind !== "image.matte") return `#/image?result=${job.id}`;
  if (job.kind === "mesh.generate") return `#/mesh?result=${job.id}`;
  return `#/library?open=${job.id}`;
}

function stage(job: Job): string {
  if (job.state === "queued") return "Waiting to start";
  const p = job.progress;
  return `${p.stage ?? "Working"}${p.steps ? ` ${p.step ?? 0}/${p.steps}` : ""}`;
}

export function ActiveJobChip({ job, waiting }: { job: Job; waiting: number }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const fraction = job.state === "running" ? (job.progress.fraction ?? null) : null;
  return (
    <a className="job-chip" href={jobHref(job)} title="Open this job">
      <ProgressRing value={fraction} label={`${kindLabel(job.kind)} progress`} />
      <span className="job-chip__kind">
        <AppIcon name={ICONS[job.kind] ?? "tools"} size={16} />
        {kindLabel(job.kind)}
      </span>
      <span className="job-chip__stage footnote">{stage(job)}</span>
      <span className="job-chip__numbers footnote">
        {fraction != null ? <strong>{Math.round(fraction * 100)} %</strong> : null}
        <span>{duration(jobElapsed(job) ?? 0)}</span>
      </span>
      {waiting > 0 ? <span className="job-chip__queue footnote">+{waiting} queued</span> : null}
    </a>
  );
}
