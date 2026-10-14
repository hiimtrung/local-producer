// A job in the library grid: its picture (or an icon), kind, state and age.
import { type Job, jobFileUrl } from "../../api/client";
import { kindLabel, STATE_TONES, timeAgo } from "../../lib/format";
import { AppIcon, Badge, ServerImage } from "../atoms";

function thumbName(job: Job): string | null {
  if (job.state !== "done") return null;
  if (job.outputs.includes("image.png")) return "image.png";
  if (job.outputs.includes("input.png")) return "input.png";
  return null;
}

export function JobTile({ job, onOpen }: { job: Job; onOpen: () => void }) {
  const name = thumbName(job);
  const mesh = job.kind === "mesh.generate";
  return (
    <button type="button" className="tile lg-focusable" onClick={onOpen}>
      <div className="tile__media">
        {name ? (
          <ServerImage url={jobFileUrl(job.id, name)} alt="" lazy />
        ) : (
          <AppIcon name={mesh ? "cube" : "image"} size={32} />
        )}
        {mesh && job.state === "done" ? (
          <span className="tile__kind">
            <AppIcon name="cube" size={16} label="3D model" />
          </span>
        ) : null}
      </div>
      <div className="tile__meta">
        <span className="subheadline">{kindLabel(job.kind)}</span>
        <Badge tone={STATE_TONES[job.state]}>{job.state}</Badge>
      </div>
      <span className="footnote muted tile__time">{timeAgo(job.created)}</span>
    </button>
  );
}
