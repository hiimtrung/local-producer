// Create and edit images with FLUX.2: text to image (with image-to-3D framing) or an edit of an existing image
// (A-pose for rigging, or a custom instruction). The result can go straight to the 3D page.
import { useEffect, useState } from "react";
import {
  api,
  type EditParamsT,
  type Framing,
  type FramingOptions,
  type GenerateParamsT,
  isActive,
  type Job,
  jobFileUrl,
  paramsOf,
  refUrl,
} from "../api/client";
import type { PageProps } from "../app/router";
import { useJob, useJobFinished, useRestore } from "../hooks/useJob";
import { useModels } from "../hooks/useModels";
import { useServerConfig } from "../hooks/useServerConfig";
import { saveFile } from "../lib/files";
import { duration, jobElapsed, shortId } from "../lib/format";
import { Button, Hint, SegmentedControl, Select, Slider, Spinner, Switch, TextArea } from "../ui/atoms";
import { EmptyState, JobProgress, ModelField, PanelSection, ResultBar, SeedField } from "../ui/molecules";
import { ImagePicker, ImageView, type PickedImage, useToast } from "../ui/organisms";
import { StageLayout, StagePanel } from "../ui/templates";

type Mode = "generate" | "edit";
type Size = `${number}x${number}`;

const SIZES: { value: Size; label: string }[] = [
  { value: "1024x1024", label: "1024 × 1024 (square)" },
  { value: "832x1216", label: "832 × 1216 (portrait)" },
  { value: "1216x832", label: "1216 × 832 (landscape)" },
  { value: "768x768", label: "768 × 768 (faster)" },
  { value: "512x512", label: "512 × 512 (draft)" },
];
const MODES = [
  { value: "generate", label: "Generate" },
  { value: "edit", label: "Edit" },
] as const;
const PRESETS = [
  { value: "a_pose", label: "A-pose for rigging" },
  { value: "custom", label: "Custom" },
] as const;

/** The output settings both modes share (ImageCommon on the server). */
interface Output {
  width: number;
  height: number;
  steps: number | null;
  cfg_scale: number;
  seed: number;
  model: string | null;
}
interface GenerateState extends Output {
  prompt: string;
  useFraming: boolean;
  framing: Required<Framing>;
}
interface EditState extends Output {
  source: PickedImage | null;
  preset: "a_pose" | "custom";
  prompt: string;
}

const OUTPUT: Output = { width: 1024, height: 1024, steps: null, cfg_scale: 1.0, seed: -1, model: null };
const FRAMING: Required<Framing> = { subject: "character", style: "stylized", view: "three_quarter" };

function OutputSection<S extends Output>({
  params,
  set,
  defaultSteps,
}: {
  params: S;
  set: (p: Partial<Output>) => void;
  defaultSteps: number;
}) {
  const models = useModels("flux2-klein");
  return (
    <PanelSection title="Output">
      <ModelField models={models} value={params.model} onChange={(model) => set({ model })} />
      <Select
        label="Size"
        options={SIZES}
        value={`${params.width}x${params.height}` as Size}
        onChange={(v) => {
          const [width = 1024, height = 1024] = v.split("x").map(Number);
          set({ width, height });
        }}
      />
      <Slider
        label="Steps"
        min={1}
        max={12}
        step={1}
        showValue
        value={params.steps ?? defaultSteps}
        onChange={(steps) => set({ steps })}
      />
      <Hint>4 is the measured sweet spot; 3 is ~10 s faster with small changes.</Hint>
      <Slider
        label="Guidance (CFG)"
        min={0}
        max={10}
        step={0.5}
        showValue
        value={params.cfg_scale}
        onChange={(cfg_scale) => set({ cfg_scale })}
      />
      <Hint>FLUX.2-klein is distilled for 1.0.</Hint>
      <SeedField seed={params.seed} onChange={(seed) => set({ seed })} />
    </PanelSection>
  );
}

function outputOf(p: Partial<GenerateParamsT | EditParamsT>): Partial<Output> {
  const out: Partial<Output> = {};
  if (p.width != null) out.width = p.width;
  if (p.height != null) out.height = p.height;
  if (p.steps !== undefined) out.steps = p.steps;
  if (p.cfg_scale != null) out.cfg_scale = p.cfg_scale;
  if (p.seed != null) out.seed = p.seed;
  if (p.model !== undefined) out.model = p.model;
  return out;
}

export function ImagePage({ query, navigate }: PageProps) {
  const toast = useToast();
  const config = useServerConfig();
  const [mode, setMode] = useState<Mode>(query.mode === "edit" ? "edit" : "generate");
  const [framingInfo, setFramingInfo] = useState<FramingOptions | null>(null);
  const [gen, setGen] = useState<GenerateState>({ ...OUTPUT, prompt: "", useFraming: true, framing: FRAMING });
  const [edit, setEdit] = useState<EditState>({
    ...OUTPUT,
    seed: 7,
    source: query.job ? { ref: { job: query.job, file: "image.png" }, label: "From library" } : null,
    preset: "a_pose",
    prompt: "",
  });
  const [composed, setComposed] = useState("");
  const [jobId, setJobId] = useState<string | null>(query.result ?? null);
  const job = useJob(jobId);
  const setG = (p: Partial<GenerateState>) => setGen((g) => ({ ...g, ...p }));
  const setE = (p: Partial<EditState>) => setEdit((e) => ({ ...e, ...p }));

  useEffect(() => {
    api.framing().then(setFramingInfo, () => {});
  }, []);

  useEffect(() => {
    if (mode !== "generate" || !gen.prompt.trim()) {
      setComposed("");
      return undefined;
    }
    const t = setTimeout(() => {
      api.compose(gen.prompt, gen.useFraming ? gen.framing : null).then(
        (r) => setComposed(r.prompt),
        () => {},
      );
    }, 400);
    return () => clearTimeout(t);
  }, [mode, gen.prompt, gen.useFraming, gen.framing]);

  // Opening a result (#/image?result=<id>) shows the settings it was made with.
  useRestore(job, query.result, (j: Job) => {
    const e = paramsOf(j, "image.edit");
    const g = paramsOf(j, "image.generate");
    if (e) {
      setMode("edit");
      setE({
        ...outputOf(e),
        source: { ref: e.image, label: "Source" },
        preset: e.preset ?? "a_pose",
        prompt: e.prompt ?? "",
      });
    } else if (g) {
      setG({ ...outputOf(g), prompt: g.prompt, useFraming: !!g.framing, framing: { ...FRAMING, ...g.framing } });
    }
  });
  useJobFinished(job, (j) => {
    if (j.state === "done") toast("success", j.kind === "image.edit" ? "Image edited" : "Image generated");
    if (j.state === "failed") toast("danger", "The job failed", j.error);
  });

  const running = isActive(job);
  const run = async () => {
    try {
      const { width, height, steps, cfg_scale, seed, model } = mode === "generate" ? gen : edit;
      const output = { width, height, steps, cfg_scale, seed, model };
      let created: Job;
      if (mode === "generate") {
        created = await api.submit("image.generate", {
          ...output,
          prompt: gen.prompt,
          framing: gen.useFraming ? gen.framing : null,
        });
      } else {
        if (!edit.source) return;
        created = await api.submit("image.edit", {
          ...output,
          image: edit.source.ref,
          preset: edit.preset,
          prompt: edit.prompt,
        });
      }
      setJobId(created.id);
    } catch (e) {
      toast("danger", "Can't start the job", (e as Error).message);
    }
  };

  const ready =
    mode === "generate"
      ? gen.prompt.trim().length > 0
      : !!edit.source && (edit.preset === "a_pose" || edit.prompt.trim().length > 0);
  const done = job?.state === "done" && job.outputs.includes("image.png") ? job : null;

  const panel = (
    <StagePanel
      title="Image"
      action={
        <Button
          variant="prominent"
          block
          size="lg"
          disabled={!ready || running}
          loading={running}
          onClick={() => void run()}
        >
          {mode === "generate" ? "Generate image" : "Edit image"}
        </Button>
      }
    >
      <SegmentedControl aria-label="Mode" value={mode} onChange={setMode} options={MODES} />
      {mode === "generate" ? (
        <>
          <PanelSection title="Prompt">
            <TextArea
              label="Describe the subject"
              autoGrow
              maxRows={6}
              maxLength={4000}
              placeholder="a brass steam engine with a flywheel"
              value={gen.prompt}
              onChange={(prompt) => setG({ prompt })}
            />
            <Switch
              label="Image-to-3D framing"
              checked={gen.useFraming}
              onChange={(useFraming) => setG({ useFraming })}
            />
            {gen.useFraming && framingInfo ? (
              <>
                <SegmentedControl
                  size="sm"
                  aria-label="Subject"
                  value={gen.framing.subject}
                  options={framingInfo.subjects}
                  onChange={(subject) => setG({ framing: { ...gen.framing, subject } })}
                />
                <SegmentedControl
                  size="sm"
                  aria-label="Style"
                  value={gen.framing.style}
                  options={framingInfo.styles}
                  onChange={(style) => setG({ framing: { ...gen.framing, style } })}
                />
                <SegmentedControl
                  size="sm"
                  aria-label="View"
                  value={gen.framing.view}
                  options={framingInfo.views}
                  onChange={(view) => setG({ framing: { ...gen.framing, view } })}
                />
              </>
            ) : null}
            {composed ? (
              <details className="composed">
                <summary className="footnote">Full prompt sent to the model</summary>
                <p className="footnote muted">{composed}</p>
              </details>
            ) : null}
          </PanelSection>
          <OutputSection params={gen} set={setG} defaultSteps={config.image_steps} />
        </>
      ) : (
        <>
          <PanelSection title="Source image">
            <ImagePicker value={edit.source} onChange={(source) => setE({ source })} />
          </PanelSection>
          <PanelSection title="Change">
            <SegmentedControl
              size="sm"
              aria-label="Edit"
              value={edit.preset}
              onChange={(preset) => setE({ preset })}
              options={PRESETS}
            />
            {edit.preset === "custom" ? (
              <TextArea
                label="What should change"
                autoGrow
                maxRows={6}
                maxLength={4000}
                placeholder="Make the jacket red, keep everything else the same"
                value={edit.prompt}
                onChange={(prompt) => setE({ prompt })}
              />
            ) : (
              <Hint>Arms down and out at about 45°, same character, same view.</Hint>
            )}
          </PanelSection>
          <OutputSection params={edit} set={setE} defaultSteps={config.image_steps} />
        </>
      )}
    </StagePanel>
  );

  let content;
  if (done) {
    content = <ImageView url={jobFileUrl(done.id, "image.png")} alt="Generated image" />;
  } else if (mode === "edit" && edit.source) {
    content = <ImageView url={refUrl(edit.source.ref)} alt="Source image" />;
  } else if (jobId && !job) {
    content = <Spinner size="lg" />;
  } else {
    content = (
      <EmptyState
        on="stage"
        title="Your image appears here"
        hint={
          mode === "generate"
            ? "Describe a subject and generate. The grey backdrop is what image-to-3D expects."
            : "Choose an image to edit."
        }
      />
    );
  }

  const overlay = running ? (
    <JobProgress job={job} />
  ) : done ? (
    <ResultBar summary={`${duration(jobElapsed(done))}, seed ${done.info.seed ?? "?"}`}>
      <Button size="sm" onClick={() => void saveFile(jobFileUrl(done.id, "image.png"), `image-${shortId(done)}.png`)}>
        Download
      </Button>
      <Button
        size="sm"
        onClick={() => {
          setMode("edit");
          setE({ source: { ref: { job: done.id, file: "image.png" }, label: "Result" } });
          setJobId(null);
        }}
      >
        Edit this image
      </Button>
      <Button size="sm" variant="prominent" onClick={() => navigate("mesh", { job: done.id })}>
        Make 3D model
      </Button>
    </ResultBar>
  ) : null;

  return (
    <StageLayout label="Image preview" panel={panel} overlay={overlay}>
      {content}
    </StageLayout>
  );
}
