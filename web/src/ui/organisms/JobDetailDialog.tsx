// One job in a dialog: the result (image or 3D viewer), what it was made with, and what to do with it.
import { useState } from "react";
import { api, isActive, type Job, jobFileUrl } from "../../api/client";
import { saveFile } from "../../lib/files";
import { duration, jobElapsed, kindLabel, shortId, timeAgo } from "../../lib/format";
import { Button, Dialog } from "../atoms";
import { ConfirmBar } from "../molecules";
import { ImageView } from "./ImageView";
import { ModelView } from "./ModelView";
import { useToast } from "./Toaster";

export interface JobDetailDialogProps {
  job: Job;
  onClose: () => void;
  onChanged: () => void;
  onMakeModel: (job: Job) => void;
}

export function JobDetailDialog({ job, onClose, onChanged, onMakeModel }: JobDetailDialogProps) {
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const image = job.outputs.includes("image.png");
  const model = job.outputs.includes("model.glb");
  const remove = async () => {
    try {
      await api.remove(job.id);
      toast("success", "Deleted");
      onChanged();
      onClose();
    } catch (e) {
      toast("danger", "Can't delete", (e as Error).message);
    }
  };
  const download = (name: "image.png" | "model.glb", as: string) =>
    saveFile(jobFileUrl(job.id, name), as).catch((e: Error) => toast("danger", "Download failed", e.message));
  const prompt = job.info.prompt ?? (typeof job.params.prompt === "string" ? job.params.prompt : null);
  const facts: [string, string | number | null | undefined][] = [
    ["State", `${job.state}${job.error ? `: ${job.error}` : ""}`],
    ["Time", duration(jobElapsed(job))],
    ["Seed", job.info.seed],
    ["Steps", job.info.steps],
    ["Resolution", job.info.resolution],
    ["Faces", job.info.faces?.toLocaleString()],
    ["Prompt", prompt],
  ];
  return (
    <Dialog
      open
      onClose={onClose}
      title={`${kindLabel(job.kind)}, ${timeAgo(job.created)}`}
      actions={
        <>
          {isActive(job) ? (
            <Button variant="destructive" onClick={() => void api.cancel(job.id).then(onChanged)}>
              Cancel job
            </Button>
          ) : (
            <Button variant="plain" onClick={() => setConfirm(true)}>
              Delete
            </Button>
          )}
          {image ? <Button onClick={() => onMakeModel(job)}>Make 3D model</Button> : null}
          {image ? (
            <Button variant="prominent" onClick={() => void download("image.png", `image-${shortId(job)}.png`)}>
              Download
            </Button>
          ) : null}
          {model ? (
            <Button variant="prominent" onClick={() => void download("model.glb", `model-${shortId(job)}.glb`)}>
              Download GLB
            </Button>
          ) : null}
        </>
      }
    >
      <div className="job-detail">
        {model || image ? (
          <div className="job-detail__media">
            {model ? (
              <ModelView url={jobFileUrl(job.id, "model.glb")} />
            ) : (
              <ImageView url={jobFileUrl(job.id, "image.png")} alt="Result" />
            )}
          </div>
        ) : null}
        <dl className="job-detail__facts footnote">
          {facts
            .filter(([, v]) => v != null && v !== "")
            .map(([k, v]) => (
              <div key={k} className="job-detail__fact">
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
        </dl>
        {confirm ? (
          <ConfirmBar
            question="Delete this job and its files?"
            confirm="Delete"
            onConfirm={() => void remove()}
            onCancel={() => setConfirm(false)}
          />
        ) : null}
      </div>
    </Dialog>
  );
}
