// The models of one family the server can run (built in and added on the Models page), for a model picker.
import { useEffect, useState } from "react";
import { api, type ModelInfo } from "../api/client";

export function useModels(family: string): ModelInfo[] {
  const [models, setModels] = useState<ModelInfo[]>([]);
  useEffect(() => {
    api.models().then((o) => setModels(o.models.filter((m) => m.family === family && m.present)), () => {});
  }, [family]);
  return models;
}
