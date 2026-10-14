// Server status: queue, GPU memory, the loaded engine package, and the Blender add-on that talks to this server.
// The job log has its own page.
import { api } from "../../api/client";
import type { PageProps } from "../../app/router";
import { usePoll } from "../../hooks/usePoll";
import { bytes } from "../../lib/format";
import { Button, ErrorText } from "../../ui/atoms";
import { Fact } from "../../ui/molecules";
import { DocPage } from "../../ui/templates";
import { AddonSection } from "./AddonSection";
import { ServerNav } from "./ServerNav";

export function StatusPage({ navigate }: PageProps) {
  const sys = usePoll(api.system, 3000);
  const s = sys.data;
  return (
    <DocPage
      title="Status"
      nav={<ServerNav current="status" />}
      actions={
        <Button size="sm" onClick={() => navigate("log")}>
          Open the job log
        </Button>
      }
    >
      {sys.error ? <ErrorText>{sys.error.message}</ErrorText> : null}
      {s && s.engine.state !== "ready" ? (
        <ErrorText>
          No GPU jobs can run: {s.engine.problem} (<a href="#/engines">Engines</a>)
        </ErrorText>
      ) : null}
      {s ? (
        <div className="facts">
          <Fact label="Version" value={s.version} />
          <Fact label="Jobs" value={`${s.jobs_running} running, ${s.jobs_queued} queued`} />
          <Fact label="GPU memory in use" value={bytes(s.gpu_memory_in_use_bytes)} />
          <Fact
            label="Models"
            value={s.models_ready ? "Ready" : "Missing"}
            tone={s.models_ready ? "success" : "warning"}
          />
          <Fact label="GPU" value={s.gpu} />
          <Fact
            label="Engine"
            value={s.engine.state === "ready" ? "Loaded" : "Not loaded"}
            tone={s.engine.state === "ready" ? "success" : "danger"}
            detail={s.engine.state === "ready" ? `${s.engine.id} · ${s.engine.version}` : undefined}
          />
          <Fact label="Access token" value={s.token_required ? "Required" : "Off"} />
        </div>
      ) : null}
      <AddonSection />
    </DocPage>
  );
}
