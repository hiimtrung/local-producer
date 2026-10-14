// The server's job log, live: every CLI line and the GPU memory per job, followed as it is written.
import { useState } from "react";
import { useLogTail } from "../../hooks/useLogTail";
import { Button, ErrorText, Switch, TextField } from "../../ui/atoms";
import { LogView } from "../../ui/organisms";
import { DocPage } from "../../ui/templates";
import { ServerNav } from "./ServerNav";

export function LogPage() {
  const log = useLogTail();
  const [follow, setFollow] = useState(true);
  const [filter, setFilter] = useState("");
  const download = () => {
    const url = URL.createObjectURL(new Blob(log.lines, { type: "text/plain" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "server.log" });
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <DocPage title="Job log" nav={<ServerNav current="log" />}>
      <section className="console lg-glass lg-glass--thick lg-r-lg" aria-label="Job log">
        <div className="console__bar">
          <span className={`live-dot${log.error ? " live-dot--off" : ""}`} aria-hidden="true" />
          <span className="footnote muted">
            {log.error ? "Reconnecting" : "Live"} · {log.lines.length.toLocaleString()} lines
          </span>
          <TextField
            className="console__filter"
            size="sm"
            leading="search"
            clearable
            placeholder="Filter"
            aria-label="Filter lines"
            value={filter}
            onChange={setFilter}
          />
          <Switch label="Follow" checked={follow} onChange={setFollow} />
          <Button size="sm" disabled={!log.lines.length} onClick={download}>
            Download
          </Button>
        </div>
        {log.error ? <ErrorText>{log.error.message}</ErrorText> : null}
        <LogView label="Job log lines" lines={log.lines} follow={follow} onFollowChange={setFollow} filter={filter} />
      </section>
    </DocPage>
  );
}
