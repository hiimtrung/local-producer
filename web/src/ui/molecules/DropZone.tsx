// Drop an image here, paste one anywhere on the page, or choose a file.
import { type DragEvent, useEffect, useRef, useState } from "react";
import { Button, Spinner } from "../atoms";

const ACCEPT = "image/png,image/jpeg,image/webp";
const firstImage = (files: FileList | null | undefined) => [...(files ?? [])].find((f) => f.type.startsWith("image/"));

export interface DropZoneProps {
  onFile: (file: File) => void;
  busy?: boolean;
}

export function DropZone({ onFile, busy }: DropZoneProps) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const file = firstImage(e.clipboardData?.files);
      if (file) onFile(file);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [onFile]);
  const drop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const file = firstImage(e.dataTransfer.files);
    if (file) onFile(file);
  };
  return (
    <div
      className={`dropzone${over ? " dropzone--over" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
    >
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
        }}
      />
      {busy ? (
        <Spinner label="Uploading" />
      ) : (
        <>
          <p className="callout">Drop an image here or paste it</p>
          <p className="footnote muted">PNG, JPEG or WebP, up to 32 MB</p>
          <Button size="sm" onClick={() => input.current?.click()}>
            Choose file
          </Button>
        </>
      )}
    </div>
  );
}
