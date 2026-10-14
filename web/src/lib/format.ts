// Small display helpers.
import type { Job, JobKind, JobState } from "../api/client";
import type { Tone } from "../ui/atoms/lucent";

export function bytes(n: number | null | undefined): string {
  if (n == null) return "–";
  if (n >= 2 ** 30) return `${(n / 2 ** 30).toFixed(1)} GB`;
  if (n >= 2 ** 20) return `${(n / 2 ** 20).toFixed(0)} MB`;
  return `${Math.max(1, Math.round(n / 1024))} KB`;
}

export function duration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "–";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${String(s % 60).padStart(2, "0")} s`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
}

export function timeAgo(epochSeconds: number): string {
  const d = Date.now() / 1000 - epochSeconds;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)} min ago`;
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
  return new Date(epochSeconds * 1000).toLocaleDateString();
}

export const KIND_LABELS: Record<JobKind, string> = {
  "image.generate": "Image",
  "image.edit": "Image edit",
  "image.matte": "Cutout",
  "mesh.generate": "3D model",
  "model.check": "Model test",
};

export const kindLabel = (kind: string): string => (KIND_LABELS as Record<string, string>)[kind] ?? kind;

export const STATE_TONES: Record<JobState, Tone> = {
  queued: "neutral",
  running: "accent",
  done: "success",
  failed: "danger",
  cancelled: "warning",
};

export function jobElapsed(job: Job): number | null {
  if (!job.started) return null;
  return (job.finished ?? Date.now() / 1000) - job.started;
}

export const shortId = (job: Job) => job.id.slice(0, 8);
