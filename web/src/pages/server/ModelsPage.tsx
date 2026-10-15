// Models: per family, the shared components (pinned files every model of the family runs with) and the main models
// added from a suggestion, Hugging Face, another link or an upload; each can be tested with the loaded engine (a tiny
// real run) and one is the default. The Image / 3D pages offer every model that is present. Below, the component
// files: download what is missing, verify checksums.
import { useRef, useState } from "react";
import { api, isActive, type ModelInfo, type ModelsOverview, type SetupStatus } from "../../api/client";
import { useJob } from "../../hooks/useJob";
import { usePoll } from "../../hooks/usePoll";
import { bytes, timeAgo } from "../../lib/format";
import {
  Badge,
  Button,
  Card,
  ErrorText,
  List,
  ListItem,
  Progress,
  SegmentedControl,
  Spinner,
  TextField,
  type Tone,
} from "../../ui/atoms";
import { ChoiceField } from "../../ui/molecules";
import { useToast } from "../../ui/organisms";
import { DocPage } from "../../ui/templates";
import { ServerNav } from "./ServerNav";

const FILE_STATE: Record<SetupStatus["items"][number]["state"], [Tone, string]> = {
  ok: ["success", "Installed"],
  missing: ["warning", "Missing"],
  "wrong-size": ["danger", "Damaged"],
};

export function ModelsPage() {
  const toast = useToast();
  const setup = usePoll(api.setup, 2000);
  const models = usePoll(api.models, 2000);
  const start = async (fn: () => Promise<unknown>, what: string) => {
    try {
      await fn();
      await Promise.all([setup.reload(), models.reload()]);
    } catch (e) {
      toast("danger", `Can't ${what}`, (e as Error).message);
    }
  };
  const nav = <ServerNav current="models" />;
  const data = setup.data;
  if (!data || !models.data) {
    const error = setup.error ?? models.error;
    return (
      <DocPage title="Models" nav={nav}>
        {error ? <ErrorText>{error.message}</ErrorText> : <Spinner size="lg" />}
      </DocPage>
    );
  }
  const dl = data.download;
  const missing = data.items.filter((i) => i.state !== "ok");
  const itemPct = dl.item_size ? Math.round((100 * dl.item_done) / dl.item_size) : 0;
  return (
    <DocPage
      title="Models"
      nav={nav}
      lede="Each kind of model runs with shared components (text encoder, VAE, image encoder, decoders) plus a main model you choose. Add main models from the suggestions, Hugging Face, a link or an upload, then test them: the loaded engine makes a tiny real output, so you know the model runs on this machine before you use it."
      actions={
        <div className="row-actions">
          {!data.ready && !dl.running ? (
            <Button variant="prominent" onClick={() => void start(api.downloadModels, "start the download")}>
              {`${data.to_add.length ? "Download components and recommended models" : "Download components"} (${bytes(data.missing_bytes)})`}
            </Button>
          ) : null}
          <Button
            disabled={dl.running || data.verify.running}
            loading={data.verify.running}
            onClick={() => void start(api.verifyModels, "start the verification")}
          >
            Verify checksums
          </Button>
        </div>
      }
    >
      {data.engine.state !== "ready" ? (
        <p className="callout">
          No engine package is loaded: {data.engine.problem}. The download installs the one for this machine first, or
          see <a href="#/engines">Engines</a>.
        </p>
      ) : null}
      {dl.running ? (
        <Card title={`Downloading ${dl.done_items + 1} of ${dl.total_items}`} subtitle={dl.item}>
          <Progress value={itemPct} showValue label={`${bytes(dl.item_done)} of ${bytes(dl.item_size)}`} />
        </Card>
      ) : null}
      {dl.error ? <ErrorText>Download failed: {dl.error}</ErrorText> : null}
      {models.data.adding.running ? <AddingProgress adding={models.data.adding} /> : null}
      {models.data.families.map((f) => (
        <List key={f.id} header={f.title}>
          <ComponentsRow parts={models.data?.components.find((c) => c.family === f.id)} />
          {models.data?.models.some((m) => m.family === f.id) ? null : (
            <ListItem title="No model yet" subtitle="Add one of the suggestions below, or your own with Add a model" />
          )}
          {models.data?.models
            .filter((m) => m.family === f.id)
            .map((m) => (
              <ModelRow
                key={m.id}
                model={m}
                engine={data.engine.state === "ready" ? `${data.engine.id} ${data.engine.version}` : null}
                onTest={() => api.checkModel(m.id)}
                onDefault={() => void start(() => api.defaultModel(m.id), "make it the default")}
                onRemove={() => void start(() => api.removeModel(m.id), "remove the model")}
                onError={(what, e) => toast("danger", `Can't ${what}`, e.message)}
              />
            ))}
          {models.data?.suggestions
            .filter((s) => s.family === f.id && !s.added)
            .map((s) => (
              <ListItem
                key={s.url}
                title={s.title}
                subtitle={`${s.recommended ? "Recommended" : "Suggested"} · ${s.note} · ${bytes(s.size)} download`}
                trailing={
                  <Button
                    size="sm"
                    disabled={models.data?.adding.running}
                    onClick={() =>
                      void start(
                        () => api.addModel({ family: s.family, title: s.title, url: s.url }),
                        "add the model",
                      )
                    }
                  >
                    Add
                  </Button>
                }
              />
            ))}
        </List>
      ))}
      <AddModelCard overview={models.data} onAdded={() => void models.reload()} />
      {data.verify.bad != null ? (
        <p className="callout">
          {data.verify.bad.length ? `Checksum mismatch: ${data.verify.bad.join(", ")}` : "All checksums match."}
        </p>
      ) : null}
      <details className="log-details">
        <summary className="footnote">
          Component files: {missing.length ? `${missing.length} missing` : `all ${data.items.length} installed`}
        </summary>
        <List>
          {data.items.map((i) => (
            <ListItem
              key={i.id}
              title={i.id}
              subtitle={i.dest}
              detail={bytes(i.size)}
              trailing={
                <Badge tone={FILE_STATE[i.state][0]} icon>
                  {FILE_STATE[i.state][1]}
                </Badge>
              }
            />
          ))}
        </List>
      </details>
      {dl.log.length ? (
        <details className="log-details">
          <summary className="footnote">Download log</summary>
          <pre className="log code">{dl.log.join("\n")}</pre>
        </details>
      ) : null}
    </DocPage>
  );
}

function AddingProgress({ adding }: { adding: ModelsOverview["adding"] }) {
  return (
    <Card title={`Adding a model, file ${adding.done_items + 1} of ${adding.total_items}`} subtitle={adding.item}>
      <Progress
        value={adding.item_size ? Math.round((100 * adding.item_done) / adding.item_size) : 0}
        showValue
        label={`${bytes(adding.item_done)}${adding.item_size ? ` of ${bytes(adding.item_size)}` : ""}`}
      />
    </Card>
  );
}

const ROLE_LABEL: Record<string, string> = {
  text_encoder: "Qwen3-4B text encoder",
  vae: "VAE",
  dinov3: "DINOv3 image encoder",
  ss_dec: "structure decoder",
  shape_dec: "shape decoder",
  tex_dec: "texture decoder",
};

function ComponentsRow({ parts }: { parts: ModelsOverview["components"][number] | undefined }) {
  if (!parts) return null;
  return (
    <ListItem
      title="Shared components"
      subtitle={parts.components.map((c) => ROLE_LABEL[c.role] ?? c.role).join(", ")}
      trailing={
        <Badge tone={parts.ready ? "success" : "warning"} icon>
          {parts.ready ? "Installed" : "Missing"}
        </Badge>
      }
    />
  );
}

function checkBadge(m: ModelInfo, engine: string | null): [Tone, string] {
  if (!m.present) return ["warning", "Files missing"];
  if (!m.check) return ["neutral", "Not tested"];
  if (m.check.state === "failed") return ["danger", "Failed"];
  return m.check.engine === engine ? ["success", "Runs here"] : ["info", "Tested with another engine"];
}

function ModelRow({
  model: m,
  engine,
  onTest,
  onDefault,
  onRemove,
  onError,
}: {
  model: ModelInfo;
  engine: string | null;
  onTest: () => Promise<{ id: string }>;
  onDefault: () => void;
  onRemove: () => void;
  onError: (what: string, e: Error) => void;
}) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const job = useJob(jobId);
  const testing = jobId !== null && (job === null || isActive(job));
  const [tone, label] = checkBadge(m, engine);
  const c = m.check;
  const result = c
    ? c.state === "ok"
      ? `tested ${timeAgo(c.at)} with ${c.engine}: ${c.seconds ?? "?"} s`
      : `failed ${timeAgo(c.at)} with ${c.engine}: ${c.message}`
    : "";
  return (
    <ListItem
      title={m.default ? `${m.title} (default)` : m.title}
      subtitle={[m.source, bytes(m.size), result].filter(Boolean).join(" · ")}
      trailing={
        <div className="row-actions">
          {testing ? (
            <Badge tone="accent">{job?.progress.stage ?? "Queued"}</Badge>
          ) : (
            <Badge tone={tone} icon>
              {label}
            </Badge>
          )}
          <Button
            size="sm"
            disabled={testing || !m.present || !engine}
            onClick={() =>
              onTest().then(
                (j) => setJobId(j.id),
                (e: Error) => onError("start the test", e),
              )
            }
          >
            Test
          </Button>
          {m.default ? null : (
            <Button size="sm" variant="plain" disabled={!m.present} onClick={onDefault}>
              Make default
            </Button>
          )}
          <Button
            size="sm"
            variant="plain"
            disabled={testing}
            onClick={() => {
              if (!confirm) return setConfirm(true);
              setConfirm(false);
              onRemove();
            }}
          >
            {confirm ? "Confirm remove" : "Remove"}
          </Button>
        </div>
      }
    />
  );
}

type Source = "link" | "upload";

function AddModelCard({ overview, onAdded }: { overview: ModelsOverview; onAdded: () => void }) {
  const toast = useToast();
  const [family, setFamily] = useState(overview.families[0]?.id ?? "");
  const [title, setTitle] = useState("");
  const [source, setSource] = useState<Source>("link");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const fam = overview.families.find((f) => f.id === family);
  const canUpload = fam?.adds === "file";
  const mode: Source = canUpload ? source : "link";
  const adding = overview.adding;
  const busy = adding.running || uploading;

  const add = async () => {
    try {
      if (mode === "link") {
        await api.addModel({ family, title: title.trim(), url: url.trim() });
        toast("info", "Downloading the model", "It appears in the list when it is complete.");
      } else if (file) {
        setUploading(true);
        await api.uploadModel(family, title.trim(), file);
        toast("success", "Model added", "Test it before you use it.");
      }
      setTitle("");
      setUrl("");
      setFile(null);
      onAdded();
    } catch (e) {
      toast("danger", "Can't add the model", (e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <Card
      title="Add a model"
      subtitle={fam?.description}
      footer={
        <Button
          variant="prominent"
          disabled={busy || !title.trim() || (mode === "link" ? !url.trim() : !file)}
          loading={busy}
          onClick={() => void add()}
        >
          {mode === "link" ? "Download and add" : "Upload and add"}
        </Button>
      }
    >
      <div className="stack">
        <ChoiceField
          label="Kind"
          options={overview.families.map((f) => ({ value: f.id, label: f.title }))}
          value={family}
          onChange={setFamily}
        />
        <TextField label="Name" placeholder="e.g. FLUX.2-klein-4B Q4_0" value={title} onChange={setTitle} />
        {canUpload ? (
          <SegmentedControl
            aria-label="Source"
            value={source}
            options={[
              { value: "link", label: "Link" },
              { value: "upload", label: "Upload" },
            ]}
            onChange={setSource}
          />
        ) : null}
        {mode === "link" ? (
          <TextField
            label={canUpload ? "Link to a .gguf or .safetensors file" : "Hugging Face folder"}
            placeholder={
              canUpload
                ? "https://huggingface.co/<owner>/<repo>/blob/main/<file>.gguf"
                : "https://huggingface.co/<owner>/<repo>/tree/main/<folder>"
            }
            value={url}
            onChange={setUrl}
          />
        ) : (
          <div className="row-actions">
            <input
              ref={input}
              type="file"
              accept=".gguf,.safetensors"
              hidden
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <Button onClick={() => input.current?.click()}>Choose a file</Button>
            <span className="footnote muted">{file ? `${file.name}, ${bytes(file.size)}` : "No file chosen"}</span>
          </div>
        )}
        <p className="footnote muted">
          Hugging Face files are pinned to the current commit and checked against the SHA256 it publishes; any other
          http(s) link works too, also on this machine or your network: you are responsible for what it points to.
          Only weights (.gguf, .safetensors) are accepted, never code.
        </p>
        {adding.error ? (
          <div className="row-actions">
            <ErrorText>Adding failed: {adding.error}</ErrorText>
            <Button size="sm" variant="plain" onClick={() => void api.dismissAdding().then(onAdded, () => {})}>
              Dismiss
            </Button>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
