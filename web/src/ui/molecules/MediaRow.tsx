// An image with a label and an action on one line (the chosen input image).
import type { ReactNode } from "react";
import { ServerImage } from "../atoms";

export function MediaRow({ url, label, action }: { url: string | null; label: string; action?: ReactNode }) {
  return (
    <div className="media-row">
      <ServerImage url={url} alt="" />
      <span className="subheadline media-row__label">{label}</span>
      {action}
    </div>
  );
}
