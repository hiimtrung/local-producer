// Full screen for one element (a preview), tracking changes made outside the app (Esc, the browser's own UI).
import { type RefObject, useCallback, useEffect, useState } from "react";

export function useFullscreen(ref: RefObject<HTMLElement | null>) {
  const [active, setActive] = useState(false);
  useEffect(() => {
    const update = () => setActive(!!ref.current && document.fullscreenElement === ref.current);
    document.addEventListener("fullscreenchange", update);
    return () => document.removeEventListener("fullscreenchange", update);
  }, [ref]);
  const toggle = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void ref.current?.requestFullscreen();
  }, [ref]);
  return { active, toggle, supported: document.fullscreenEnabled };
}
