// Choose an input image: drop or paste a file, browse, or pick a result from the library.
import { useState } from "react";
import { api, refUrl } from "../../api/client";
import { Button, SegmentedControl } from "../atoms";
import { DropZone, MediaRow } from "../molecules";
import { LibraryPicker, type PickedImage } from "./LibraryPicker";
import { useToast } from "./Toaster";

export type { PickedImage };

type Source = "upload" | "library";
const SOURCES = [
  { value: "upload", label: "Upload" },
  { value: "library", label: "From library" },
] as const;

export interface ImagePickerProps {
  value: PickedImage | null;
  onChange: (value: PickedImage | null) => void;
}

export function ImagePicker({ value, onChange }: ImagePickerProps) {
  const [tab, setTab] = useState<Source>("upload");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const onFile = async (file: File) => {
    setBusy(true);
    try {
      const meta = await api.upload(file);
      onChange({ ref: { upload: meta.id }, label: file.name });
    } catch (e) {
      toast("danger", "Upload failed", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  if (value) {
    return (
      <MediaRow
        url={refUrl(value.ref)}
        label={value.label || "Selected image"}
        action={
          <Button size="sm" variant="plain" onClick={() => onChange(null)}>
            Change
          </Button>
        }
      />
    );
  }
  return (
    <div className="image-picker">
      <SegmentedControl size="sm" aria-label="Image source" value={tab} onChange={setTab} options={SOURCES} />
      {tab === "upload" ? (
        <DropZone onFile={(f) => void onFile(f)} busy={busy} />
      ) : (
        <LibraryPicker value={undefined} onPick={onChange} />
      )}
    </div>
  );
}
