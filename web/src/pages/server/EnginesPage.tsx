// Engine packages: what this machine is, the GPU code for it (runtime + CLI builds) in every available version, which
// one is loaded, updates, and where the server keeps its data. Installing, loading or removing needs no restart.
import { useState } from "react";
import { api, type EnginesOverview, type EngineStatus, type UpdateReport } from "../../api/client";
import { usePoll } from "../../hooks/usePoll";
import { bytes, timeAgo } from "../../lib/format";
import { Badge, Button, Card, ErrorText, List, ListItem, Progress, Spinner, type Tone } from "../../ui/atoms";
import { Fact } from "../../ui/molecules";
import { useToast } from "../../ui/organisms";
import { DocPage } from "../../ui/templates";
import { ServerNav } from "./ServerNav";

const STACKS: Record<string, string> = {
  rocm: "AMD ROCm",
  cuda: "NVIDIA CUDA",
  mlx: "Apple MLX / Metal",
  cpu: "CPU only",
};
const STATE: Record<EngineStatus["state"], [Tone, string]> = {
  ready: ["success", "Loaded"],
  none: ["warning", "None loaded"],
  blocked: ["danger", "Blocked"],
};

/** One version of a package as the page shows it: from the catalog, installed, or both. */
interface VersionRow {
  id: string;
  version: string;
  title: string;
  compatible: boolean;
  mismatch: string;
  latest: boolean;
  downloadSize: number | null;
  installed: { size: number; at: number; active: boolean } | null;
}

function versionRows(data: EnginesOverview): Map<string, VersionRow[]> {
  const rows = new Map<string, VersionRow[]>();
  const add = (r: VersionRow) => rows.set(r.id, [...(rows.get(r.id) ?? []), r]);
  for (const p of data.packages) {
    const inst = data.installed.find((i) => i.id === p.id && i.version === p.version);
    add({
      id: p.id,
      version: p.version,
      title: p.title,
      compatible: p.compatible,
      mismatch: p.mismatch,
      latest: p.latest,
      downloadSize: p.download_size,
      installed: inst ? { size: inst.size, at: inst.installed_at, active: inst.active } : null,
    });
  }
  for (const i of data.installed.filter((i) => !i.in_catalog)) {
    add({
      id: i.id,
      version: i.version,
      title: i.title,
      compatible: true,
      mismatch: "",
      latest: false,
      downloadSize: null,
      installed: { size: i.size, at: i.installed_at, active: i.active },
    });
  }
  return rows;
}

export function EnginesPage() {
  const toast = useToast();
  const { data, error, reload } = usePoll(api.engines, 2000);
  const [updates, setUpdates] = useState<UpdateReport | null>(null);
  const [checking, setChecking] = useState(false);
  const act = async (fn: () => Promise<unknown>, what: string) => {
    try {
      await fn();
      await reload();
    } catch (e) {
      toast("danger", `Can't ${what}`, (e as Error).message);
    }
  };
  const checkUpdates = async () => {
    setChecking(true);
    try {
      setUpdates(await api.engineUpdates());
    } catch (e) {
      toast("danger", "Can't check for updates", (e as Error).message);
    } finally {
      setChecking(false);
    }
  };
  const nav = <ServerNav current="engines" />;
  if (!data) {
    return (
      <DocPage title="Engines" nav={nav}>
        {error ? <ErrorText>{error.message}</ErrorText> : <Spinner size="lg" />}
      </DocPage>
    );
  }
  const { host, engine, install } = data;
  const busy = install.running;
  return (
    <DocPage
      title="Engines"
      nav={nav}
      lede="The GPU code for this machine comes as a package: its runtime libraries and the image and 3D generators. Versions install side by side into their own volume and load without restarting the server; the next job uses the loaded one."
      actions={
        <div className="row-actions">
          <Button loading={checking} disabled={busy} onClick={() => void checkUpdates()}>
            Check for updates
          </Button>
          <Button disabled={busy} onClick={() => void act(api.reloadEngines, "reload the engine")}>
            Reload
          </Button>
        </div>
      }
    >
      <div className="facts">
        <Fact label="This machine" value={`${host.os} ${host.arch}`} />
        <Fact label="GPU" value={host.gpu} />
        <Fact label="Compute stack" value={STACKS[host.accelerator] ?? host.accelerator} />
        <Fact
          label="Engine"
          value={STATE[engine.state][1]}
          tone={STATE[engine.state][0]}
          detail={engine.state === "ready" ? `${engine.id} · ${engine.version}` : undefined}
        />
      </div>
      {engine.state === "ready" ? (
        <p className="callout">
          {engine.title} ({engine.version}) is loaded: {engine.runners.join(", ")}.
        </p>
      ) : (
        <ErrorText>{engine.problem}</ErrorText>
      )}
      {busy ? (
        <Card title={`Installing, file ${install.done_items + 1} of ${install.total_items}`} subtitle={install.item}>
          <Progress
            value={install.item_size ? Math.round((100 * install.item_done) / install.item_size) : 0}
            showValue
            label={`${bytes(install.item_done)} of ${bytes(install.item_size)}`}
          />
        </Card>
      ) : null}
      {install.error ? <ErrorText>Install failed: {install.error}</ErrorText> : null}
      {updates ? <Updates report={updates} /> : null}
      {[...versionRows(data)].map(([id, rows]) => (
        <Versions
          key={id}
          rows={rows}
          busy={busy}
          onInstall={(r) => void act(() => api.installEngine(r.id, r.version), "install")}
          onLoad={(r) => void act(() => api.loadEngine(r.id, r.version), "load the version")}
          onRemove={(r) => void act(() => api.removeEngine(r.id, r.version), "remove the version")}
        />
      ))}
      <List header="Coming soon">
        {data.planned.map((p) => (
          <ListItem
            key={p.accelerator}
            title={p.title}
            subtitle={p.description}
            trailing={<Badge tone="neutral">Planned</Badge>}
          />
        ))}
      </List>
      <List header="Storage">
        {data.storage.map((s) => (
          <ListItem
            key={s.name}
            title={s.name}
            subtitle={s.source || s.path}
            detail={s.free == null ? "" : `${bytes(s.free)} free`}
          />
        ))}
      </List>
    </DocPage>
  );
}

function Updates({ report }: { report: UpdateReport }) {
  return (
    <Card title="Updates" subtitle={`Checked ${timeAgo(report.checked_at)}`}>
      <ul className="steps">
        {report.packages.length ? (
          report.packages.map((p) => (
            <li key={`${p.id}/${p.version}`}>
              {p.title} {p.version} is available; install it below.
            </li>
          ))
        ) : (
          <li>The newest packaged version is installed.</li>
        )}
        {report.upstream.map((u) => (
          <li key={u.repo}>
            {u.error ? (
              `${u.repo}: can't read the latest release (${u.error})`
            ) : u.newer ? (
              <>
                {u.repo} has a newer release, <a href={u.url}>{u.latest}</a> (packaged: {u.pinned}). A package is
                built from it once it has been tested on this hardware.
              </>
            ) : (
              `${u.repo}: ${u.pinned} is the latest release.`
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Versions({
  rows,
  busy,
  onInstall,
  onLoad,
  onRemove,
}: {
  rows: VersionRow[];
  busy: boolean;
  onInstall: (r: VersionRow) => void;
  onLoad: (r: VersionRow) => void;
  onRemove: (r: VersionRow) => void;
}) {
  const [confirm, setConfirm] = useState<string | null>(null);
  const first = rows[0];
  if (!first) return null;
  return (
    <List header={`${first.title} · versions`}>
      {rows.map((r) => {
        const facts = [
          r.latest ? "newest" : null,
          r.installed ? `installed ${timeAgo(r.installed.at)}, ${bytes(r.installed.size)}` : null,
          !r.installed && r.downloadSize != null ? `${bytes(r.downloadSize)} download` : null,
          r.downloadSize == null ? "no longer in the catalog" : null,
          r.compatible ? null : `not for this machine: ${r.mismatch}`,
        ].filter(Boolean);
        const removing = confirm === r.version;
        return (
          <ListItem
            key={r.version}
            title={r.version}
            subtitle={facts.join(" · ")}
            trailing={
              <div className="row-actions">
                {r.installed?.active ? (
                  <Badge tone="success" icon>
                    Loaded
                  </Badge>
                ) : null}
                {r.installed && !r.installed.active ? (
                  <Button size="sm" disabled={busy} onClick={() => onLoad(r)}>
                    Load
                  </Button>
                ) : null}
                {!r.installed && r.compatible ? (
                  <Button size="sm" variant="prominent" disabled={busy} onClick={() => onInstall(r)}>
                    Install
                  </Button>
                ) : null}
                {r.installed ? (
                  <Button
                    size="sm"
                    variant="plain"
                    disabled={busy}
                    title={r.installed.active ? "Unloads it first: no GPU job runs until another version is loaded" : ""}
                    onClick={() => {
                      if (!removing) return setConfirm(r.version);
                      setConfirm(null);
                      onRemove(r);
                    }}
                  >
                    {removing ? (r.installed.active ? "Confirm: unload and remove" : "Confirm remove") : "Remove"}
                  </Button>
                ) : null}
              </div>
            }
          />
        );
      })}
    </List>
  );
}
