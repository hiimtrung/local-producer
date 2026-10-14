// Which model a job runs with: the built-in one (null) or one added on the Models page. Hidden while there is no
// choice; a model that failed its test is marked.
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
  const options = models.map((m) => ({
    value: m.builtin ? "" : m.id,
    label: `${m.title}${m.check?.state === "failed" ? " (failed its test)" : ""}`,
  }));
  return (
    <ChoiceField
      label="Model"
      options={options}
      value={value ?? ""}
      onChange={(v) => onChange(v || null)}
      hint="Add or test models on Server > Models."
    />
  );
}
