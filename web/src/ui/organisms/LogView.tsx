// A live log: monospace lines, errors and finished jobs tinted, and "follow" that keeps the newest line in view.
// Scrolling up stops following; scrolling back to the bottom (or the Latest button) resumes it.
import { useLayoutEffect, useRef } from "react";
import { Button } from "../atoms";

/** Within this many pixels of the bottom counts as at the bottom. */
const BOTTOM_SLACK = 24;

/** Terminal control sequences the CLIs write for their progress bars (erase line, colours). */
const ANSI = /\x1b\[[0-9;?]*[A-Za-z]/g;

type Tone = "error" | "done" | "plain";
const toneOf = (line: string): Tone =>
  /\b(error|failed|traceback|exception)\b/i.test(line) ? "error" : /\b(done|finished)\b/i.test(line) ? "done" : "plain";

export interface LogViewProps {
  lines: readonly string[];
  follow: boolean;
  onFollowChange: (follow: boolean) => void;
  /** Show only lines containing this text (case-insensitive). */
  filter?: string;
  label: string;
}

export function LogView({ lines, follow, onFollowChange, filter = "", label }: LogViewProps) {
  const box = useRef<HTMLDivElement>(null);
  const needle = filter.trim().toLowerCase();
  const shown = needle ? lines.filter((l) => l.toLowerCase().includes(needle)) : lines;

  useLayoutEffect(() => {
    const el = box.current;
    if (follow && el) el.scrollTop = el.scrollHeight;
  }, [follow, shown]);

  const onScroll = () => {
    const el = box.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= BOTTOM_SLACK;
    if (atBottom !== follow) onFollowChange(atBottom);
  };

  return (
    <div className="log-view">
      <div ref={box} className="log-view__scroll code" role="log" aria-label={label} tabIndex={0} onScroll={onScroll}>
        {shown.length ? (
          shown.map((line, i) => (
            // eslint-disable-next-line react/no-array-index-key -- log lines repeat; position is their identity
            <div key={i} className={`log-view__line log-view__line--${toneOf(line)}`}>
              {line.replace(ANSI, "").replace(/\r?\n$/, "") || " "}
            </div>
          ))
        ) : (
          <div className="log-view__empty footnote">{needle ? "No line matches the filter." : "The log is empty."}</div>
        )}
      </div>
      {!follow ? (
        <Button className="log-view__latest" size="sm" variant="prominent" onClick={() => onFollowChange(true)}>
          Latest ↓
        </Button>
      ) : null}
    </div>
  );
}
