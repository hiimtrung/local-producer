// Every pipeline without a page of its own, with a form generated from its parameter schema. A pipeline added on
// the server shows up here with no web code (server/app/pipelines/base.py).
import { api, type JobKind } from "../api/client";
import { usePoll } from "../hooks/usePoll";
import { ErrorText, Spinner } from "../ui/atoms";
import { ToolCard } from "../ui/organisms";
import { DocPage } from "../ui/templates";

const OWN_PAGES: readonly JobKind[] = ["image.generate", "image.edit", "mesh.generate", "model.check"];

export function ToolsPage() {
  const { data, error } = usePoll(api.pipelines, 0);
  const tools = (data ?? []).filter((p) => !(OWN_PAGES as readonly string[]).includes(p.kind));
  return (
    <DocPage title="Tools" lede="Smaller steps you can run on their own.">
      {error ? <ErrorText>{error.message}</ErrorText> : null}
      {!data && !error ? <Spinner size="lg" /> : null}
      <div className="card-grid">
        {tools.map((p) => (
          <ToolCard key={p.kind} pipeline={p} />
        ))}
      </div>
    </DocPage>
  );
}
