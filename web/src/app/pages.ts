// Page registry: the router and the bottom tab bar are built from it. A new page = a component taking PageProps +
// one entry here (its id goes into PAGE_IDS in router.ts; the compiler then insists on an entry).
import type { ComponentType } from "react";
import { ImagePage } from "../pages/ImagePage";
import { LibraryPage } from "../pages/LibraryPage";
import { MeshPage } from "../pages/MeshPage";
import { EnginesPage } from "../pages/server/EnginesPage";
import { LogPage } from "../pages/server/LogPage";
import { ModelsPage } from "../pages/server/ModelsPage";
import { SettingsPage } from "../pages/server/SettingsPage";
import { StatusPage } from "../pages/server/StatusPage";
import { ToolsPage } from "../pages/ToolsPage";
import type { TabItem } from "../ui/organisms";
import type { PageId, PageProps } from "./router";

export type TabId = "image" | "mesh" | "library" | "tools" | "server";

export interface PageDef {
  title: string;
  /** The bottom-bar tab the page belongs to. */
  tab: TabId;
  component: ComponentType<PageProps>;
}

export const PAGES: Record<PageId, PageDef> = {
  image: { title: "Image", tab: "image", component: ImagePage },
  mesh: { title: "3D model", tab: "mesh", component: MeshPage },
  library: { title: "Library", tab: "library", component: LibraryPage },
  tools: { title: "Tools", tab: "tools", component: ToolsPage },
  status: { title: "Status", tab: "server", component: StatusPage },
  engines: { title: "Engines", tab: "server", component: EnginesPage },
  models: { title: "Models", tab: "server", component: ModelsPage },
  log: { title: "Job log", tab: "server", component: LogPage },
  settings: { title: "Settings", tab: "server", component: SettingsPage },
};

export const TABS: readonly (TabItem<TabId> & { home: PageId })[] = [
  { id: "image", label: "Image", icon: "image", home: "image" },
  { id: "mesh", label: "3D model", icon: "cube", home: "mesh" },
  { id: "library", label: "Library", icon: "library", home: "library" },
  { id: "tools", label: "Tools", icon: "tools", home: "tools" },
  { id: "server", label: "Server", icon: "server", home: "status" },
];
