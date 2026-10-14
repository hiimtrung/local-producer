// The glass capsule under a finished result: a short summary and the actions for it.
import type { ReactNode } from "react";

export function ResultBar({ summary, children }: { summary: ReactNode; children: ReactNode }) {
  return (
    <div className="result-bar lg-glass lg-r-capsule">
      <span className="footnote muted">{summary}</span>
      {children}
    </div>
  );
}
