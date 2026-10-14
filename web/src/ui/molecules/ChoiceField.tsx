// One choice out of a few: a segmented control when up to four short options fit, a menu otherwise.
import type { ReactNode } from "react";
import { type Option, type OptionValue, SegmentedControl, Select } from "../atoms";
import { Field } from "./Field";

export interface ChoiceFieldProps<V extends OptionValue> {
  label: string;
  options: readonly Option<V>[];
  value: V;
  onChange: (value: V) => void;
  hint?: ReactNode;
  /** The label is still the control's accessible name, only not shown (e.g. under a section of the same name). */
  hideLabel?: boolean;
}

/** Characters of option labels a segmented control in the 380 px panel shows without clipping. */
const SEGMENTED_CHARS = 30;

export function ChoiceField<V extends OptionValue>(props: ChoiceFieldProps<V>) {
  const { label, options, value, onChange, hint, hideLabel } = props;
  const chars = options.reduce((n, o) => n + o.label.length, 0);
  if (options.length > 4 || chars > SEGMENTED_CHARS) {
    return (
      <Field hint={hint}>
        <Select
          label={hideLabel ? undefined : label}
          aria-label={label}
          options={options}
          value={value}
          onChange={onChange}
        />
      </Field>
    );
  }
  return (
    <Field label={hideLabel ? undefined : label} hint={hint}>
      <SegmentedControl size="sm" aria-label={label} options={options} value={value} onChange={onChange} />
    </Field>
  );
}
