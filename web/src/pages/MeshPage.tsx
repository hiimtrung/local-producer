// Image to a PBR-textured 3D model with TRELLIS.2, previewed in an interactive viewer.
import { useState } from "react";
import { api, isActive, jobFileUrl, type MeshParamsT, paramsOf, refUrl } from "../api/client";
import type { PageProps } from "../app/router";
import { useJob, useJobFinished, useRestore } from "../hooks/useJob";
import { useModels } from "../hooks/useModels";
import { useServerConfig } from "../hooks/useServerConfig";
import { saveFile } from "../lib/files";
import { duration, jobElapsed, shortId } from "../lib/format";
import { Button, Hint, type Option, Slider, Spinner, Switch } from "../ui/atoms";
import {
  ChoiceField,
  EmptyState,
  JobProgress,
  ModelField,
  NumberField,
  PanelSection,
  ResultBar,
  SeedField,
} from "../ui/molecules";
import { ImagePicker, ImageView, ModelView, type PickedImage, useToast } from "../ui/organisms";
import { StageLayout, StagePanel } from "../ui/templates";

/** Every MeshParams field except the image, all present (null = the server default). */
type Settings = Required<Omit<MeshParamsT, "image">>;
type Resolution = NonNullable<Settings["resolution"]>;
type Atlas = NonNullable<Settings["atlas"]>;

const RESOLUTIONS: (Option<Resolution> & { time: string })[] = [
  { value: 512, label: "512", time: "~4.5 min" },
  { value: 1024, label: "1024", time: "~19 min, sharper" },
  { value: 1536, label: "1536", time: "~53 min" },
];
const MATTING: Option<Settings["matting"]>[] = [
  { value: "auto", label: "Auto" },
  { value: "rembg", label: "Remove" },
  { value: "none", label: "Keep" },
];
const MATTE_MODELS: Option<Settings["matte_model"]>[] = [
  { value: "isnet-general-use", label: "ISNet (0.6 s)" },
  { value: "u2net", label: "U²-Net" },
  { value: "birefnet-general-lite", label: "BiRefNet lite (6 s)" },
  { value: "birefnet-general", label: "BiRefNet (10 s)" },
];
const ATLASES: Option<Atlas | 0>[] = [
  { value: 0, label: "Automatic (1024 at 512, 2048 at 1024)" },
  { value: 1024, label: "1024 px" },
  { value: 2048, label: "2048 px" },
  { value: 4096, label: "4096 px" },
];
const DEFAULTS: Settings = {
  matting: "auto",
  matte_model: "isnet-general-use",
  resolution: null,
  steps: null,
  seed: 1234,
  texture: true,
  atlas: null,
  structure_guidance: null,
  shape_guidance: null,
  max_tokens: null,
  model: null,
};

export function MeshPage({ query }: PageProps) {
  const toast = useToast();
  const config = useServerConfig();
  const models = useModels("trellis2");
  const [source, setSource] = useState<PickedImage | null>(
    query.job ? { ref: { job: query.job, file: "image.png" }, label: "From library" } : null,
  );
  const [p, setP] = useState<Settings>(DEFAULTS);
  const [advanced, setAdvanced] = useState(false);
  const [jobId, setJobId] = useState<string | null>(query.result ?? null);
  const job = useJob(jobId);
  const set = (x: Partial<Settings>) => setP((v) => ({ ...v, ...x }));

  useRestore(job, query.result, (j) => {
    const params = paramsOf(j, "mesh.generate");
    if (!params) return;
    const { image, ...rest } = params;
    setSource({ ref: image, label: "Source" });
    setP((v) => ({ ...v, ...rest }));
  });
  useJobFinished(job, (j) => {
    if (j.state === "done") toast("success", "3D model ready", `${j.info.faces?.toLocaleString() ?? "?"} faces`);
    if (j.state === "failed") toast("danger", "The job failed", j.error);
  });

  const running = isActive(job);
  const done = job?.state === "done" && job.outputs.includes("model.glb") ? job : null;
  const resolution = p.resolution ?? config.mesh_resolution;

  const run = async () => {
    if (!source) return;
    try {
      setJobId((await api.submit("mesh.generate", { image: source.ref, ...p })).id);
    } catch (e) {
      toast("danger", "Can't start the job", (e as Error).message);
    }
  };

  const panel = (
    <StagePanel
      title="3D model"
      action={
        <Button
          variant="prominent"
          block
          size="lg"
          disabled={!source || running}
          loading={running}
          onClick={() => void run()}
        >
          Generate 3D model
        </Button>
      }
    >
      <PanelSection title="Input image">
        <ImagePicker value={source} onChange={setSource} />
      </PanelSection>
      <PanelSection title="Background">
        <ChoiceField
          label="Background"
          hideLabel
          options={MATTING}
          value={p.matting}
          onChange={(matting) => set({ matting })}
          hint="Auto removes it unless the image already has transparency."
        />
        {p.matting !== "none" ? (
          <ChoiceField
            label="Cutout model"
            options={MATTE_MODELS}
            value={p.matte_model}
            onChange={(matte_model) => set({ matte_model })}
          />
        ) : null}
      </PanelSection>
      <PanelSection title="Quality">
        <ModelField models={models} value={p.model} onChange={(model) => set({ model })} />
        <ChoiceField
          label="Resolution"
          options={RESOLUTIONS}
          value={resolution}
          onChange={(r) => set({ resolution: r })}
          hint={`${RESOLUTIONS.find((r) => r.value === resolution)?.time ?? ""} for a character; bulky objects take longer.`}
        />
        <Slider
          label="Steps"
          min={2}
          max={16}
          step={1}
          showValue
          value={p.steps ?? config.mesh_steps}
          onChange={(steps) => set({ steps })}
        />
        <Hint>8 by default; 6 is ~14 % faster and looks almost the same.</Hint>
        <Switch label="Texture" checked={p.texture} onChange={(texture) => set({ texture })} />
        {p.texture ? (
          <ChoiceField
            label="Texture atlas"
            options={ATLASES}
            value={p.atlas ?? 0}
            onChange={(v) => set({ atlas: v === 0 ? null : v })}
          />
        ) : null}
        <SeedField seed={p.seed} fixed={1234} onChange={(seed) => set({ seed })} />
      </PanelSection>
      <PanelSection
        title="Advanced"
        aside={<Switch aria-label="Show advanced" checked={advanced} onChange={setAdvanced} />}
      >
        {advanced ? (
          <>
            <Slider
              label="Structure guidance"
              min={0}
              max={20}
              step={0.5}
              showValue
              value={p.structure_guidance ?? 7.5}
              onChange={(structure_guidance) => set({ structure_guidance })}
            />
            <Slider
              label="Shape guidance"
              min={0}
              max={20}
              step={0.5}
              showValue
              value={p.shape_guidance ?? 7.5}
              onChange={(shape_guidance) => set({ shape_guidance })}
            />
            <NumberField
              optional
              label="Token budget (1024+)"
              placeholder="49152"
              min={4096}
              max={49152}
              hint="Lower is faster at high resolution and loses detail"
              value={p.max_tokens}
              onChange={(max_tokens) => set({ max_tokens })}
            />
            <Button
              size="sm"
              variant="plain"
              onClick={() => set({ structure_guidance: null, shape_guidance: null, max_tokens: null })}
            >
              Reset to model defaults
            </Button>
          </>
        ) : (
          <Hint>Guidance strengths and the token budget.</Hint>
        )}
      </PanelSection>
    </StagePanel>
  );

  let content;
  if (done) content = <ModelView url={jobFileUrl(done.id, "model.glb")} />;
  else if (source) content = <ImageView url={refUrl(source.ref)} alt="Input image" />;
  else if (jobId && !job) content = <Spinner size="lg" />;
  else {
    content = (
      <EmptyState
        on="stage"
        title="Your 3D model appears here"
        hint="Use an image with one subject on a plain background; generate one on the Image page."
      />
    );
  }

  const overlay = running ? (
    <JobProgress job={job} />
  ) : done ? (
    <ResultBar summary={`${done.info.faces?.toLocaleString() ?? "?"} faces, ${duration(jobElapsed(done))}`}>
      <Button
        size="sm"
        variant="prominent"
        onClick={() => void saveFile(jobFileUrl(done.id, "model.glb"), `model-${shortId(done)}.glb`)}
      >
        Download GLB
      </Button>
    </ResultBar>
  ) : null;

  return (
    <StageLayout label="3D preview" panel={panel} overlay={overlay}>
      {content}
    </StageLayout>
  );
}
