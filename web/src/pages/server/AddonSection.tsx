// The Blender add-on section of the Status page: drag it into Blender to install (Blender 4.2+ extension
// repository), or download the zip.
import { api } from "../../api/client";
import { usePoll } from "../../hooks/usePoll";
import { saveFile } from "../../lib/files";
import { Button, Card, ErrorText, Spinner, TextField } from "../../ui/atoms";
import { DragInstallLink, dragInstallUrls } from "../../ui/molecules";
import { useToast } from "../../ui/organisms";

export function AddonSection() {
  const toast = useToast();
  const { data, error } = usePoll(api.addon, 0);
  const copy = (text: string) =>
    navigator.clipboard.writeText(text).then(
      () => toast("success", "Copied"),
      () => toast("danger", "Can't copy", "Select the text and copy it by hand."),
    );
  return (
    <section className="stack" aria-labelledby="addon-title">
      <div className="section-head">
        <h2 className="title-2" id="addon-title">
          Blender add-on
        </h2>
      </div>
      <p className="body muted">
        Generate images and textured meshes from Blender&apos;s sidebar, with the same server and the same queue as
        this page.
      </p>
      {error ? <ErrorText>{error.message}</ErrorText> : null}
      {!data && !error ? <Spinner size="lg" /> : null}
      {data ? (
        <div className="addon-install">
          <DragInstallLink
            info={data}
            onClick={(e) => {
              e.preventDefault();
              saveFile(data.download, `${data.id}-${data.version}.zip`).catch((err: Error) =>
                toast("danger", "Download failed", err.message),
              );
            }}
          />
          <p className="footnote muted">Drag the button into a Blender window (4.2 or newer). Click it to download the zip.</p>
        </div>
      ) : null}
      <div className="card-grid">
        <Card title="Install by dragging">
          <ol className="steps callout">
            <li>In Blender, allow online access once: Edit, Preferences, System, Network, Allow Online Access.</li>
            <li>
              Drag the button above into any Blender window. The first time, Blender says the extension comes from an
              unknown repository: press Add Repository, confirm, and drag the button again.
            </li>
            <li>Confirm the install. Later versions show up as updates in Preferences, Get Extensions.</li>
          </ol>
          {data ? (
            <TextField
              label="Repository URL"
              readOnly
              value={dragInstallUrls(data).repository}
              trailing={
                <Button size="sm" variant="plain" onClick={() => void copy(dragInstallUrls(data).repository)}>
                  Copy
                </Button>
              }
            />
          ) : null}
        </Card>
        <Card title="Then">
          <ol className="steps callout">
            <li>
              In the add-on preferences set Server Log to{" "}
              <code className="code">~/.local-producer/server/server.log</code> (the server state directory) for live
              progress, and Server Token if the server uses one.
            </li>
            <li>Open the 3D Viewport sidebar (N), tab LocalProducer, and press Check Server (the Library panel imports finished 3D models).</li>
            <li>Without online access: download the zip and use Preferences, Add-ons, Install from Disk.</li>
          </ol>
        </Card>
      </div>
    </section>
  );
}
