// The server's defaults (RuntimeConfig), used to show what an empty field means.
import { useEffect, useState } from "react";
import { api, type RuntimeConfig } from "../api/client";

const FALLBACK: RuntimeConfig = {
  image_steps: 4,
  mesh_steps: 8,
  mesh_resolution: 512,
  job_timeout_s: 7200,
  keep_jobs: 200,
  keep_uploads: 500,
};

export function useServerConfig(): RuntimeConfig {
  const [config, setConfig] = useState<RuntimeConfig>(FALLBACK);
  useEffect(() => {
    api.config().then(setConfig, () => {});
  }, []);
  return config;
}
