// A pipeline without a page of its own, as a card with a form generated from its parameter schema.
import { useState } from "react";
import { api, isActive, type JobKind, type ParamsOf, type PipelineInfo, jobFileUrl } from "../../api/client";
import { saveFile } from "../../lib/files";
import { useJob } from "../../hooks/useJob";
import { Button, Card, ErrorText, ServerImage } from "../atoms";
import { JobProgress } from "../molecules";
import { ImagePicker, type PickedImage } from "./ImagePicker";
import { type FormValues, imageFields, SchemaForm } from "./SchemaForm";
import { useToast } from "./Toaster";

export function ToolCard({ pipeline }: { pipeline: PipelineInfo }) {
  const toast = useToast();
  const schema = pipeline.params;
  const refs = imageFields(schema);
  const [values, setValues] = useState<FormValues>({});
  const [images, setImages] = useState<Record<string, PickedImage | null>>({});
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);
  const ready = refs.every((f) => images[f]);
  const run = async () => {
    const params: FormValues = { ...values };
    for (const f of refs) {
      const ref = images[f]?.ref;
      if (ref) params[f] = { ...ref };
    }
    try {
      // The kind and params come from the server's own schema, so they are only checked there (422 on mismatch).
      const kind = pipeline.kind as JobKind;
      setJobId((await api.submit(kind, params as unknown as ParamsOf<typeof kind>)).id);
    } catch (e) {
      toast("danger", "Can't start the job", (e as Error).message);
    }
  };
  const output = job?.state === "done" ? job.outputs.find((o) => o.endsWith(".png")) : undefined;
  return (
    <Card
      title={pipeline.title}
      subtitle={pipeline.description}
      footer={
        <Button
          variant="prominent"
          disabled={!ready || isActive(job)}
          loading={isActive(job)}
          onClick={() => void run()}
        >
          Run
        </Button>
      }
    >
      <div className="tool">
        {refs.map((f) => (
          <ImagePicker key={f} value={images[f] ?? null} onChange={(v) => setImages({ ...images, [f]: v })} />
        ))}
        <SchemaForm schema={schema} value={values} onChange={setValues} skip={refs} />
        {job && isActive(job) ? <JobProgress job={job} /> : null}
        {job?.state === "failed" ? <ErrorText>{job.error}</ErrorText> : null}
        {job && output ? (
          <div className="tool__result">
            <ServerImage className="checker" url={jobFileUrl(job.id, output)} alt="Result" />
            <Button
              size="sm"
              onClick={() => void saveFile(jobFileUrl(job.id, output), `${job.kind}-${job.id.slice(0, 8)}.png`)}
            >
              Download
            </Button>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
