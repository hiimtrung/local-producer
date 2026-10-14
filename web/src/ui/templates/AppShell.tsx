// The app frame: the moving backdrop, a slim top bar (name, the running job, server vitals, all live), the page, and the bottom tab bar.
import type { ReactNode } from "react";
import { HeaderActivity, TabBar, type TabItem } from "../organisms";

export interface AppShellProps<I extends string> {
  tabs: readonly TabItem<I>[];
  activeTab: I;
  onTab: (id: I) => void;
  children: ReactNode;
}

export function AppShell<I extends string>({ tabs, activeTab, onTab, children }: AppShellProps<I>) {
  return (
    <div className="app">
      <div className="backdrop" aria-hidden="true">
        <span className="backdrop__blob" />
        <span className="backdrop__blob" />
        <span className="backdrop__blob" />
        <span className="backdrop__blob" />
      </div>
      <header className="app__bar lg-glass lg-r-capsule">
        <a className="app__brand" href="#/">
          <span className="headline">Local Producer</span>
          <span className="footnote muted">3D asset studio</span>
        </a>
        <HeaderActivity />
      </header>
      <main className="app__page">{children}</main>
      <TabBar items={tabs} active={activeTab} onSelect={onTab} />
    </div>
  );
}
