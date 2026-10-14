// Hash routing (#/<page>?key=value): page ids, typed navigation, parsing.
export const PAGE_IDS = ["image", "mesh", "tools", "library", "engines", "models", "status", "log", "settings"] as const;
export type PageId = (typeof PAGE_IDS)[number];
export type Query = Readonly<Record<string, string>>;
export type Navigate = (page: PageId, query?: Record<string, string>) => void;

/** What every page component receives. */
export interface PageProps {
  query: Query;
  navigate: Navigate;
}

export interface Route {
  page: PageId;
  query: Query;
}

export const DEFAULT_PAGE: PageId = "image";
const isPageId = (v: string): v is PageId => (PAGE_IDS as readonly string[]).includes(v);
/** Pages that were merged into another, so old links still land somewhere sensible. */
const MOVED: Readonly<Record<string, PageId>> = { addon: "status" };

export function parseHash(hash = window.location.hash): Route {
  const [path = "", qs = ""] = hash.replace(/^#\/?/, "").split("?");
  const page = isPageId(path) ? path : (MOVED[path] ?? DEFAULT_PAGE);
  return { page, query: Object.fromEntries(new URLSearchParams(qs)) };
}

export const navigate: Navigate = (page, query = {}) => {
  const qs = new URLSearchParams(query).toString();
  window.location.hash = `#/${page}${qs ? `?${qs}` : ""}`;
};
