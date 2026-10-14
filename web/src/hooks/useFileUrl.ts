// A URL the browser can load for a server file: the URL itself, or a blob: URL fetched with the token when the
// server needs one (<img> and <model-viewer> cannot send headers).
import { useEffect, useState } from "react";
import { authHeaders, getToken } from "../lib/token";

export function useFileUrl(url: string | null | undefined): string | null {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    if (!url) {
      setSrc(null);
      return undefined;
    }
    if (!getToken()) {
      setSrc(url);
      return undefined;
    }
    let objectUrl: string | null = null;
    let cancelled = false;
    fetch(url, { headers: authHeaders() })
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => {
        if (blob && !cancelled) {
          objectUrl = URL.createObjectURL(blob);
          setSrc(objectUrl);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);
  return src;
}
