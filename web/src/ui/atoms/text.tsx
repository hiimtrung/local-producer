// Text atoms: the few type styles the pages repeat, so a change of look happens in one place.
import type { ReactNode } from "react";

export const Hint = ({ children }: { children: ReactNode }) => <p className="footnote field__hint">{children}</p>;

export const FieldLabel = ({ children }: { children: ReactNode }) => (
  <span className="subheadline field__label">{children}</span>
);

export const ErrorText = ({ children }: { children: ReactNode }) => (
  <p className="callout error-text" role="alert">
    {children}
  </p>
);

export const Muted = ({ children }: { children: ReactNode }) => <span className="footnote muted">{children}</span>;
