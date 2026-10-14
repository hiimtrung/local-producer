// Document pages (library, tools, server pages): a header and the content, as wide as the app bar so every page
// lines up the same way.
import type { ReactNode } from "react";
import { DocHeader } from "../molecules";

export interface DocPageProps {
  title: string;
  lede?: ReactNode;
  actions?: ReactNode;
  /** Shown above the header, e.g. the sub-navigation of a section. */
  nav?: ReactNode;
  children: ReactNode;
}

export function DocPage({ title, lede, actions, nav, children }: DocPageProps) {
  return (
    <div className="doc-page">
      {nav}
      <DocHeader title={title} lede={lede} actions={actions} />
      {children}
    </div>
  );
}
