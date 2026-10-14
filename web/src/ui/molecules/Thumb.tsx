// A small square image button (pick an image from the library).
import { ServerImage } from "../atoms";

export interface ThumbProps {
  url: string;
  title: string;
  selected?: boolean;
  onSelect: () => void;
}

export function Thumb({ url, title, selected, onSelect }: ThumbProps) {
  return (
    <button
      type="button"
      className={`thumb lg-focusable${selected ? " thumb--selected" : ""}`}
      onClick={onSelect}
      aria-pressed={selected}
      title={title}
    >
      <ServerImage url={url} alt="" lazy />
    </button>
  );
}
