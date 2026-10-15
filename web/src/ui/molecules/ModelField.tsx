// Which model a job runs with. The menu always shows a model: the one picked, else the family's default
// (Server > Models); null in the params = the default. Hidden while there is no choice; a model that failed its test
// is marked.
import type { ModelInfo } from "../../api/client";
import { ChoiceField } from "./ChoiceField";

export function ModelField({
  models,
  value,
  onChange,
}: {
  models: readonly ModelInfo[];
  value: string | null;
  onChange: (id: string | null) => void;
}) {
  if (models.length < 2) return null;
  const fallback = models.find((m) => m.default) ?? models[0];
  const shown = models.some((m) => m.id === value) ? value : fallback?.id;
  const options = models.map((m) => ({
    value: m.id,
    label: `${m.title}${m.default ? " (default)" : ""}${m.check?.state === "failed" ? " (failed its test)" : ""}`,
  }));
  return (
    <ChoiceField
      label="Model"
      options={options}
      value={shown ?? ""}
      onChange={(id) => onChange(models.find((m) => m.id === id)?.default ? null : id)}
      hint="Add, test or pick the default on Server > Models."
    />
  );
}
