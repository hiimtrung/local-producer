// What a stage or list shows before there is anything in it.
import type { ReactNode } from "react";

export interface EmptyStateProps {
  title: string;
  hint?: ReactNode;
  action?: ReactNode;
  /** "stage": dark text on the studio grey; "page": on the page background. */
  on?: "stage" | "page";
}

export function EmptyState({ title, hint, action, on = "page" }: EmptyStateProps) {
  return (
    <div className={`empty empty--${on}`}>
      <p className="title-3">{title}</p>
      {hint ? <p className="subheadline">{hint}</p> : null}
      {action}
    </div>
  );
}
