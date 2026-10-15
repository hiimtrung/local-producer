// The server API in one place, typed from the server's own models (types.gen.ts, generated from pydantic). Every
// call sends the access token when one is set (Settings), turns error bodies into readable messages, and never
// builds URLs from anything but ids the server returned.
import { authHeaders } from "../lib/token";
import type * as T from "./types.gen";

export type {
  AddonInfo,
  EngineStatus,
  EnginesOverview,
  UpdateReport,
  FramingOptions,
  ImageRef,
  Job,
  JobInfo,
  JobProgress,
  JobRequest,
  JsonValue,
  ModelInfo,
  ModelsOverview,
  PipelineInfo,
  RuntimeConfig,
  SetupStatus,
  SystemInfo,
  UploadInfo,
} from "./types.gen";

export type GenerateParamsT = T.GenerateParams;
export type EditParamsT = T.EditParams;
export type MeshParamsT = T.MeshParams;
export type JobState = T.Job["state"];
export type JobKind = T.JobRequest["kind"];
type ParamsByKind = { [R in T.JobRequest as R["kind"]]: R["params"] };
/** The parameters of a job kind, e.g. ParamsOf<"mesh.generate"> = MeshParams. */
export type ParamsOf<K extends JobKind> = ParamsByKind[K];
export type Framing = T.Framing;
/** A JSON schema as the server sends it (pydantic's model_json_schema). */
export type JsonSchema = { [key: string]: T.JsonValue };

/** A job's params, typed by its kind. The server validated them against that kind's model before queueing. */
export function paramsOf<K extends JobKind>(job: T.Job, kind: K): ParamsOf<K> | null {
  if (job.kind !== kind) return null;
  return job.params as unknown as ParamsOf<K>;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

function detailText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return (detail as T.ValidationError[])
      .map((e) => {
        const where = (e.loc ?? []).filter((p) => p !== "body").join(".");
        return where ? `${where}: ${e.msg}` : e.msg;
      })
      .join("; ");
  }
  return JSON.stringify(detail);
}

type Body = { json: unknown } | { form: FormData } | undefined;

async function send(method: string, path: string, body?: Body): Promise<Response> {
  const headers: Record<string, string> = { ...authHeaders() };
  let payload: BodyInit | undefined;
  if (body && "json" in body) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body.json);
  } else if (body) {
    payload = body.form;
  }
  let res: Response;
  try {
    res = await fetch(path, { method, headers, body: payload ?? null });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check that it is running (make server-up).");
  }
  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = (await res.json()) as { detail?: unknown };
      message = detailText(data.detail ?? data);
    } catch {
      /* not JSON */
    }
    if (res.status === 401) message = "The server needs an access token. Add it in Settings.";
    throw new ApiError(res.status, message);
  }
  return res;
}

async function json<R>(method: string, path: string, body?: Body): Promise<R> {
  return (await (await send(method, path, body)).json()) as R;
}

export const api = {
  system: () => json<T.SystemInfo>("GET", "/v1/system"),
  setup: () => json<T.SetupStatus>("GET", "/v1/setup"),
  downloadModels: () => json<T.Started>("POST", "/v1/setup/download"),
  verifyModels: () => json<T.Started>("POST", "/v1/setup/verify"),
  engines: () => json<T.EnginesOverview>("GET", "/v1/engines"),
  reloadEngines: () => json<T.EngineStatus>("POST", "/v1/engines/reload"),
  models: () => json<T.ModelsOverview>("GET", "/v1/models"),
  addModel: (req: T.AddModel) => json<T.Started>("POST", "/v1/models", { json: req }),
  async uploadModel(family: string, title: string, file: File): Promise<T.ModelInfo> {
    const qs = new URLSearchParams({ family, title, filename: file.name });
    let res: Response;
    try {
      res = await fetch(`/v1/models/upload?${qs}`, { method: "PUT", headers: authHeaders(), body: file });
    } catch {
      throw new ApiError(0, "Can't reach the server. Check that it is running (make server-up).");
    }
    if (!res.ok) {
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      throw new ApiError(res.status, detailText(data.detail ?? res.statusText));
    }
    return (await res.json()) as T.ModelInfo;
  },
  dismissAdding: async (): Promise<void> => {
    await send("DELETE", "/v1/models/adding");
  },
  checkModel: (id: string) => json<T.Job>("POST", `/v1/models/${encodeURIComponent(id)}/check`),
  defaultModel: (id: string) => json<T.ModelInfo>("PUT", `/v1/models/${encodeURIComponent(id)}/default`),
  removeModel: async (id: string): Promise<void> => {
    await send("DELETE", `/v1/models/${encodeURIComponent(id)}`);
  },
  engineUpdates: () => json<T.UpdateReport>("GET", "/v1/engines/updates"),
  installEngine: (id: string, version: string) =>
    json<T.Started>("POST", `/v1/engines/${encodeURIComponent(id)}/${encodeURIComponent(version)}/install`),
  loadEngine: (id: string, version: string) =>
    json<T.EngineStatus>("POST", `/v1/engines/${encodeURIComponent(id)}/${encodeURIComponent(version)}/load`),
  removeEngine: async (id: string, version: string): Promise<void> => {
    await send("DELETE", `/v1/engines/${encodeURIComponent(id)}/${encodeURIComponent(version)}`);
  },
  config: () => json<T.RuntimeConfig>("GET", "/v1/config"),
  configSchema: () => json<JsonSchema>("GET", "/v1/config/schema"),
  saveConfig: (changes: Partial<T.RuntimeConfig>) => json<T.RuntimeConfig>("PUT", "/v1/config", { json: changes }),
  pipelines: () => json<T.PipelineInfo[]>("GET", "/v1/pipelines"),
  framing: () => json<T.FramingOptions>("GET", "/v1/prompts/framing"),
  compose: (prompt: string, framing: T.Framing | null) =>
    json<T.ComposedPrompt>("POST", "/v1/prompts/compose", { json: { prompt, framing } satisfies T.ComposeRequest }),
  upload(file: File): Promise<T.UploadInfo> {
    const form = new FormData();
    form.append("file", file, file.name || "image.png");
    return json<T.UploadInfo>("POST", "/v1/uploads", { form });
  },
  submit: <K extends JobKind>(kind: K, params: ParamsOf<K>) =>
    json<T.Job>("POST", "/v1/jobs", { json: { kind, params } }),
  job: (id: string) => json<T.Job>("GET", `/v1/jobs/${id}`),
  jobs: (limit = 60) => json<T.Job[]>("GET", `/v1/jobs?limit=${limit}`),
  cancel: (id: string) => json<T.Job>("POST", `/v1/jobs/${id}/cancel`),
  remove: async (id: string): Promise<void> => {
    await send("DELETE", `/v1/jobs/${id}`);
  },
  logs: (lines = 300, since?: number) =>
    json<T.LogLines>("GET", `/v1/logs?lines=${lines}${since === undefined ? "" : `&since=${since}`}`),
  addon: () => json<T.AddonInfo>("GET", "/v1/addon"),
};

/** The files a job can produce (server/app/storage.py NAME_RE); naming one that does not exist is a type error. */
export type JobFile = "image.png" | "input.png" | "model.glb";

export const jobFileUrl = (jobId: string, name: JobFile | string) => `/v1/jobs/${jobId}/files/${name}`;
export const uploadUrl = (id: string) => `/v1/uploads/${id}`;

/** An image reference as the URL of its file. */
export function refUrl(ref: T.ImageRef | null | undefined): string | null {
  if (!ref) return null;
  if (ref.upload) return uploadUrl(ref.upload);
  return ref.job ? jobFileUrl(ref.job, ref.file ?? "image.png") : null;
}

export const isActive = (job: T.Job | null | undefined): job is T.Job =>
  !!job && (job.state === "queued" || job.state === "running");
