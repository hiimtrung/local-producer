// The server at a glance, for the header: online (a live dot), GPU memory in use, and whether the engine and the
// models are there (a link to fix it when not).
import type { ApiError, SystemInfo } from "../../api/client";
import { bytes } from "../../lib/format";
import { Badge } from "../atoms";

export function ServerVitals({ system, error }: { system: SystemInfo | null; error: ApiError | null }) {
  if (error) {
    return (
      <div className="vitals">
        <span className="vitals__dot vitals__dot--off" aria-hidden="true" />
        <span className="footnote">{error.status === 401 ? "Token needed" : "Offline"}</span>
      </div>
    );
  }
  if (!system) return <div className="vitals" />;
  return (
    <div className="vitals">
      <span className="vitals__item footnote" title={`Server ${system.version}, online`}>
        <span className={`vitals__dot${system.gpu_busy ? " vitals__dot--busy" : ""}`} aria-hidden="true" />
        <span className="vitals__label">{system.gpu_busy ? "GPU busy" : "Online"}</span>
      </span>
      <span className="vitals__item vitals__gpu footnote" title="GPU memory in use">
        <span className="muted">GPU</span> {bytes(system.gpu_memory_in_use_bytes)}
      </span>
      {system.engine.state !== "ready" ? (
        <a href="#/engines" title={system.engine.problem}>
          <Badge tone={system.engine.state === "blocked" ? "danger" : "warning"} icon>
            {system.engine.state === "blocked" ? "Engine blocked" : "No engine"}
          </Badge>
        </a>
      ) : system.models_ready ? (
        <Badge tone="success" icon>
          Models ready
        </Badge>
      ) : (
        <a href="#/models">
          <Badge tone="warning" icon>
            Models missing
          </Badge>
        </a>
      )}
    </div>
  );
}
