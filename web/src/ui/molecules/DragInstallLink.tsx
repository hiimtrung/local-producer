// A link Blender installs from when it is dragged into a Blender window (Blender 4.2+ extensions, the same mechanism
// as extensions.blender.org and lab.blender.org): the package URL carries the repository it belongs to, so Blender can
// check it against the repository's index (hash, version) and offer to add the repository the first time.
// Clicking it downloads the zip instead.
import type { MouseEvent } from "react";
import type { AddonInfo } from "../../api/client";
import { AppIcon } from "../atoms";

/** Absolute URLs on this server: Blender fetches them itself. */
export function dragInstallUrls(info: AddonInfo, origin = window.location.origin) {
  const repository = origin + info.repository;
  const query = new URLSearchParams({ repository, blender_version_min: info.blender_version_min });
  return { repository, package: origin + info.download, drag: `${origin + info.download}?${query}` };
}

export interface DragInstallLinkProps {
  info: AddonInfo;
  onClick?: (e: MouseEvent<HTMLAnchorElement>) => void;
}

export function DragInstallLink({ info, onClick }: DragInstallLinkProps) {
  const urls = dragInstallUrls(info);
  return (
    <a
      className="drag-install lg-btn lg-btn--prominent lg-btn--lg lg-focusable"
      href={urls.drag}
      draggable
      onClick={onClick}
      title="Drag this button into a Blender window to install, or click to download the zip"
    >
      <AppIcon name="drag" size={20} />
      <span>Drag into Blender to install</span>
      <span className="drag-install__version">{info.version}</span>
    </a>
  );
}
