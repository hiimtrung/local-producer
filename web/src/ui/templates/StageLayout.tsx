// Creation pages: the grey studio sweep the subject sits on (the same mid grey images are generated on), the
// parameter panel floating over its right edge, and an overlay (progress or result actions) at the bottom.
import type { ReactNode } from "react";
import { StageInsetContext } from "../../hooks/useStageInset";

/** Room the overlay takes at the bottom of the stage: its offset, a bar, and a little air. */
const INSET_WITH_OVERLAY = { bottom: 96 };
const NO_INSET = { bottom: 0 };

export interface StageLayoutProps {
  /** Accessible name of the preview area. */
  label: string;
  panel: ReactNode;
  overlay?: ReactNode;
  children: ReactNode;
}

export function StageLayout({ label, panel, overlay, children }: StageLayoutProps) {
  return (
    <div className="stage-layout">
      <section className="stage" aria-label={label}>
        <div className="stage__content">
          <StageInsetContext.Provider value={overlay ? INSET_WITH_OVERLAY : NO_INSET}>{children}</StageInsetContext.Provider>
        </div>
        {overlay ? <div className="stage__overlay">{overlay}</div> : null}
      </section>
      <aside className="stage__panel lg-glass lg-glass--thick lg-r-lg">{panel}</aside>
    </div>
  );
}

/** The panel's content: a title, sections, and the main action pinned at the bottom. */
export function StagePanel({ title, action, children }: { title: string; action: ReactNode; children: ReactNode }) {
  return (
    <div className="panel">
      <h2 className="title-2">{title}</h2>
      {children}
      <div className="panel__actions">{action}</div>
    </div>
  );
}
