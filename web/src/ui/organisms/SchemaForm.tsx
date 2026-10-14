// Forms generated from the server's JSON schemas (pydantic): a new pipeline or setting gets a working form without
// web code. Mapping: bounded integer -> slider, number -> number field, boolean -> switch, enum -> choice (segmented
// up to 4 options, else a menu), string -> text field; an optional field (anyOf [..., null]) offers "Default".
import type { JsonSchema, JsonValue } from "../../api/client";
import { Button, Slider, Switch, TextField } from "../atoms";
import { ChoiceField, Field, NumberField } from "../molecules";

/** The part of a JSON schema property the form understands. */
interface PropSchema {
  type?: string;
  enum?: (string | number)[];
  anyOf?: PropSchema[];
  $ref?: string;
  title?: string;
  description?: string;
  default?: JsonValue;
  minimum?: number;
  maximum?: number;
  multipleOf?: number;
}

interface FieldInfo extends PropSchema {
  optional: boolean;
}

export type FormValues = Record<string, JsonValue>;

/** Resolve a property schema: unwrap Optional (anyOf with null) and $ref. */
export function fieldInfo(prop: PropSchema, defs: Record<string, PropSchema> = {}): FieldInfo {
  let s: PropSchema = prop;
  let optional = false;
  if (s.anyOf) {
    const rest = s.anyOf.filter((x) => x.type !== "null");
    optional = rest.length < s.anyOf.length;
    s = { ...rest[0], title: prop.title, description: prop.description, default: prop.default };
  }
  if (s.$ref) s = { ...defs[s.$ref.split("/").pop() ?? ""], ...s };
  return { ...s, optional };
}

const titleOf = (name: string, info: FieldInfo) =>
  info.title ?? name.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

const DEFAULT = "__default";

interface SchemaFieldProps {
  name: string;
  prop: PropSchema;
  defs: Record<string, PropSchema>;
  value: JsonValue | undefined;
  onChange: (value: JsonValue) => void;
}

export function SchemaField({ name, prop, defs, value, onChange }: SchemaFieldProps) {
  const info = fieldInfo(prop, defs);
  const title = titleOf(name, info);
  const hint = info.description;
  const current = value === undefined ? (info.default ?? null) : value;

  if (info.enum) {
    const numeric = typeof info.enum[0] === "number";
    const options = [
      ...(info.optional ? [{ value: DEFAULT, label: "Default" }] : []),
      ...info.enum.map((v) => ({ value: String(v), label: String(v) })),
    ];
    return (
      <ChoiceField
        label={title}
        hint={hint}
        options={options}
        value={current == null ? DEFAULT : String(current)}
        onChange={(v) => onChange(v === DEFAULT ? null : numeric ? Number(v) : v)}
      />
    );
  }
  if (info.type === "boolean") {
    return (
      <Field hint={hint}>
        <Switch label={title} checked={current === true} onChange={onChange} />
      </Field>
    );
  }
  const { minimum: min, maximum: max } = info;
  if (info.type === "integer" && min != null && max != null && max - min <= 200) {
    const useDefault = info.optional && current == null;
    return (
      <Field hint={hint}>
        <Slider
          label={title}
          min={min}
          max={max}
          step={info.multipleOf ?? 1}
          showValue
          value={useDefault ? (typeof info.default === "number" ? info.default : min) : Number(current)}
          format={(v) => (useDefault ? "Default" : String(v))}
          onChange={onChange}
        />
        {info.optional && !useDefault ? (
          <Button size="sm" variant="plain" onClick={() => onChange(null)}>
            Use default
          </Button>
        ) : null}
      </Field>
    );
  }
  if (info.type === "integer" || info.type === "number") {
    const number = typeof current === "number" ? current : null;
    return info.optional ? (
      <NumberField optional label={title} hint={hint} min={min} max={max} value={number} onChange={onChange} />
    ) : (
      <NumberField label={title} hint={hint} min={min} max={max} value={number ?? 0} onChange={onChange} />
    );
  }
  if (info.type === "string") {
    return <TextField label={title} hint={hint} value={typeof current === "string" ? current : ""} onChange={onChange} />;
  }
  return null;
}

export interface SchemaFormProps {
  schema: JsonSchema;
  value: FormValues;
  onChange: (value: FormValues) => void;
  /** Field names rendered elsewhere (e.g. image references handled by an ImagePicker). */
  skip?: readonly string[];
}

const propertiesOf = (schema: JsonSchema) => (schema.properties ?? {}) as unknown as Record<string, PropSchema>;

export function SchemaForm({ schema, value, onChange, skip = [] }: SchemaFormProps) {
  const defs = (schema.$defs ?? {}) as unknown as Record<string, PropSchema>;
  return (
    <div className="schema-form">
      {Object.entries(propertiesOf(schema))
        .filter(([name]) => !skip.includes(name))
        .map(([name, prop]) => (
          <SchemaField
            key={name}
            name={name}
            prop={prop}
            defs={defs}
            value={value[name]}
            onChange={(v) => onChange({ ...value, [name]: v })}
          />
        ))}
    </div>
  );
}

/** Names of the fields whose schema is an image reference. */
export function imageFields(schema: JsonSchema): string[] {
  return Object.entries(propertiesOf(schema))
    .filter(([, p]) => (p.$ref ?? "").endsWith("/ImageRef"))
    .map(([name]) => name);
}
