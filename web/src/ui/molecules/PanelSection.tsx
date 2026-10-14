// A titled group of controls inside a creation panel.
import type { ReactNode } from "react";

export interface PanelSectionProps {
  title?: string;
  aside?: ReactNode;
  children: ReactNode;
}

export function PanelSection({ title, aside, children }: PanelSectionProps) {
  return (
    <section className="panel-section">
      {title ? (
        <div className="panel-section__head">
          <h3 className="headline">{title}</h3>
          {aside}
        </div>
      ) : null}
      <div className="panel-section__body">{children}</div>
    </section>
  );
}
