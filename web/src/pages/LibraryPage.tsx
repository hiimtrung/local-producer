// Every job and its results: open, download, reuse as input, cancel, delete.
import { useState } from "react";
import { api, type Job } from "../api/client";
import type { PageProps } from "../app/router";
import { usePoll } from "../hooks/usePoll";
import { Button, ErrorText, SegmentedControl, Spinner } from "../ui/atoms";
import { EmptyState } from "../ui/molecules";
import { JobDetailDialog, JobTile } from "../ui/organisms";
import { DocPage } from "../ui/templates";

type Filter = "all" | "image" | "mesh";
const FILTERS = [
  { value: "all", label: "All" },
  { value: "image", label: "Images" },
  { value: "mesh", label: "3D models" },
] as const;

const matches = (filter: Filter, j: Job) => filter === "all" || j.kind.startsWith(filter);

export function LibraryPage({ query, navigate }: PageProps) {
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string | null>(query.open ?? null); // #/library?open=<job id>
  const { data, error, reload } = usePoll(() => api.jobs(300), 4000);
  const jobs = (data ?? []).filter((j) => matches(filter, j));
  const current = open ? data?.find((j) => j.id === open) : undefined;
  return (
    <DocPage
      title="Library"
      actions={<SegmentedControl aria-label="Filter" value={filter} onChange={setFilter} options={FILTERS} />}
    >
      {error ? <ErrorText>{error.message}</ErrorText> : null}
      {!data ? (
        error ? null : <Spinner size="lg" />
      ) : jobs.length ? (
        <div className="tile-grid">
          {jobs.map((j) => (
            <JobTile key={j.id} job={j} onOpen={() => setOpen(j.id)} />
          ))}
        </div>
      ) : (
        <EmptyState
          title="Nothing here yet"
          hint="Generate an image or a 3D model and it will be kept here."
          action={
            <Button variant="prominent" onClick={() => navigate("image")}>
              Generate an image
            </Button>
          }
        />
      )}
      {current ? (
        <JobDetailDialog
          job={current}
          onClose={() => setOpen(null)}
          onChanged={() => void reload()}
          onMakeModel={(j) => navigate("mesh", { job: j.id })}
        />
      ) : null}
    </DocPage>
  );
}
