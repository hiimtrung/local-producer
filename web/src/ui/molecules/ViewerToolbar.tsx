// The glass capsule of view controls over a preview (zoom, orbit, fit, full screen), in groups split by hairlines.
import { Fragment, type ReactNode } from "react";
import { AppIcon, type AppIconName, IconButton } from "../atoms";

export interface ViewerTool {
  icon: AppIconName;
  label: string;
  /** Shown in the tooltip after the label, e.g. "+" or "Scroll". */
  shortcut?: string;
  onClick: () => void;
  /** For toggles (auto-rotate): rendered as aria-pressed. */
  pressed?: boolean;
  disabled?: boolean;
}

export interface ViewerToolbarProps {
  label: string;
  groups: ViewerTool[][];
  /** A short live value after the first group, e.g. the zoom level. */
  readout?: ReactNode;
}

export function ViewerToolbar({ label, groups, readout }: ViewerToolbarProps) {
  return (
    <div className="viewer-toolbar lg-glass lg-r-capsule" role="toolbar" aria-label={label}>
      {groups.map((group, i) => (
        <Fragment key={group.map((t) => t.label).join()}>
          {i > 0 ? <span className="viewer-toolbar__sep" aria-hidden="true" /> : null}
          {group.map((t) => (
            <IconButton
              key={t.label}
              variant="plain"
              size="sm"
              className={t.pressed ? "viewer-toolbar__on" : undefined}
              icon={<AppIcon name={t.icon} size={18} />}
              label={t.label}
              title={t.shortcut ? `${t.label} (${t.shortcut})` : t.label}
              aria-pressed={t.pressed}
              disabled={t.disabled}
              onClick={t.onClick}
            />
          ))}
          {i === 0 && readout != null ? (
            <output className="viewer-toolbar__readout footnote" aria-live="polite">
              {readout}
            </output>
          ) : null}
        </Fragment>
      ))}
    </div>
  );
}
