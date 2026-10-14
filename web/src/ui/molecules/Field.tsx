// A labelled control with an optional hint: the layout every form row uses.
import type { ReactNode } from "react";
import { FieldLabel, Hint } from "../atoms";

export interface FieldProps {
  label?: ReactNode;
  hint?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
}

export function Field({ label, hint, aside, children }: FieldProps) {
  return (
    <div className="field">
      {label ? (
        <div className="field__head">
          <FieldLabel>{label}</FieldLabel>
          {aside}
        </div>
      ) : null}
      {children}
      {hint ? <Hint>{hint}</Hint> : null}
    </div>
  );
}
