// The title block of a document page: title, optional lede and actions on the right.
import type { ReactNode } from "react";

export interface DocHeaderProps {
  title: string;
  lede?: ReactNode;
  actions?: ReactNode;
}

export function DocHeader({ title, lede, actions }: DocHeaderProps) {
  return (
    <header className="doc-header">
      <div className="doc-header__row">
        <h1 className="large-title">{title}</h1>
        {actions}
      </div>
      {lede ? <p className="body doc-header__lede">{lede}</p> : null}
    </header>
  );
}
