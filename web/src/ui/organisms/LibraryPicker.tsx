// Pick an image from earlier results (thumbnails of finished image jobs).
import { useEffect, useState } from "react";
import { api, type ImageRef, type Job, jobFileUrl } from "../../api/client";
import { kindLabel, timeAgo } from "../../lib/format";
import { Hint, Spinner } from "../atoms";
import { Thumb } from "../molecules";

export interface PickedImage {
  ref: ImageRef;
  label: string;
}

const isImageResult = (j: Job) => j.state === "done" && j.outputs.includes("image.png") && j.kind !== "mesh.generate";

export function LibraryPicker({ value, onPick }: { value: ImageRef | undefined; onPick: (v: PickedImage) => void }) {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  useEffect(() => {
    api.jobs(120).then(setJobs, () => setJobs([]));
  }, []);
  if (!jobs) return <Spinner />;
  const images = jobs.filter(isImageResult);
  if (!images.length) return <Hint>No images yet. Generate one or upload a file.</Hint>;
  return (
    <div className="thumb-grid">
      {images.map((j) => (
        <Thumb
          key={j.id}
          url={jobFileUrl(j.id, "image.png")}
          title={`${kindLabel(j.kind)}, ${timeAgo(j.created)}`}
          selected={value?.job === j.id}
          onSelect={() => onPick({ ref: { job: j.id, file: "image.png" }, label: kindLabel(j.kind) })}
        />
      ))}
    </div>
  );
}
