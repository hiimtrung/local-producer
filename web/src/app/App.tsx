// The app: theme, hash router (with a page transition when the page changes), frame with the bottom tab bar, toasts.
import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { transitionPage } from "../lib/transitions";
import { AppShell } from "../ui/templates";
import { ToastProvider } from "../ui/organisms";
import { PAGES, TABS, type TabId } from "./pages";
import { navigate, parseHash } from "./router";

export function App() {
  const [route, setRoute] = useState(parseHash);
  const current = useRef(route.page);
  current.current = route.page;
  useEffect(() => {
    const onHash = () => {
      const next = parseHash();
      if (next.page === current.current) {
        setRoute(next); // same page, new query (a dialog, a result): no transition
        return;
      }
      transitionPage(
        () => {
          flushSync(() => setRoute(next));
          window.scrollTo(0, 0);
        },
        document.querySelector<HTMLElement>(".app__page"),
      );
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const page = PAGES[route.page];
  const Page = page.component;
  const key = `${route.page}?${new URLSearchParams(route.query).toString()}`; // a new query remounts the page
  const onTab = (id: TabId) => {
    const tab = TABS.find((t) => t.id === id);
    if (tab && id !== page.tab) navigate(tab.home);
  };
  useEffect(() => {
    document.title = `${page.title} · Local Producer`;
  }, [page.title]);
  return (
    <ToastProvider>
      <AppShell tabs={TABS} activeTab={page.tab} onTab={onTab}>
        <Page key={key} query={route.query} navigate={navigate} />
      </AppShell>
    </ToastProvider>
  );
}
