// The sub-navigation of the Server tab: status (with the Blender add-on), log, engines, models, settings. (Defined here, not taken from the page
// registry, because the registry imports these pages.)
import { navigate, type PageId } from "../../app/router";
import { type Option, SegmentedControl } from "../../ui/atoms";

const OPTIONS: Option<PageId>[] = [
  { value: "status", label: "Status" },
  { value: "log", label: "Log" },
  { value: "engines", label: "Engines" },
  { value: "models", label: "Models" },
  { value: "settings", label: "Settings" },
];

export function ServerNav({ current }: { current: PageId }) {
  return (
    <SegmentedControl
      className="server-nav"
      aria-label="Server pages"
      value={current}
      options={OPTIONS}
      onChange={(id) => navigate(id)}
    />
  );
}
