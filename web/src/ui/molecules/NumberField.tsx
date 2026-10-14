// A number input. With `optional`, an empty field means "the server default" (null).
import { TextField } from "../atoms";

interface Common {
  label: string;
  hint?: string;
  min?: number;
  max?: number;
  placeholder?: string;
}

export type NumberFieldProps = Common &
  (
    | { optional: true; value: number | null; onChange: (value: number | null) => void }
    | { optional?: false; value: number; onChange: (value: number) => void }
  );

const clamp = (v: number, min = -Infinity, max = Infinity) => Math.min(max, Math.max(min, v));

export function NumberField(props: NumberFieldProps) {
  const { label, hint, min, max, placeholder } = props;
  const change = (text: string) => {
    if (props.optional) props.onChange(text === "" ? null : clamp(Number(text) || 0, min, max));
    else props.onChange(clamp(Number(text) || 0, min, max));
  };
  return (
    <TextField
      label={label}
      hint={hint}
      type="number"
      inputMode="numeric"
      min={min}
      max={max}
      placeholder={placeholder ?? (props.optional ? "Default" : undefined)}
      value={props.value == null ? "" : String(props.value)}
      onChange={change}
    />
  );
}
