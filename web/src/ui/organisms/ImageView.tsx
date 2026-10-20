// A zoomable, pannable image preview. It fits the stage by default; scroll or pinch zooms at the pointer, dragging
// pans, a double click toggles fit / 100 %, and when focused + - 0 1 and the arrow keys do the same. Fitting keeps
// clear of a bar the stage lays over its bottom.
import { type KeyboardEvent, type PointerEvent, useEffect, useRef, useState } from "react";
import { useFileUrl } from "../../hooks/useFileUrl";
import { useFullscreen } from "../../hooks/useFullscreen";
import { useStageInset } from "../../hooks/useStageInset";
import { Spinner } from "../atoms";
import { ViewerToolbar } from "../molecules";

const MIN_SCALE = 0.05;
const MAX_SCALE = 16;
const STEP = 1.25;
/** Space kept around the image when it is fitted. */
const FIT_PADDING = 40;
/** Extra room at the top for the toolbar (its offset and height). */
const TOOLBAR_SPACE = 28;
const PAN_STEP = 48;

/** Scale and the offset of the image centre from the viewport centre, in screen pixels. */
interface View {
  scale: number;
  x: number;
  y: number;
}
interface Point {
  x: number;
  y: number;
}

const clampScale = (s: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));

export interface ImageViewProps {
  url: string | null;
  alt: string;
}

export function ImageView({ url, alt }: ImageViewProps) {
  const { bottom: reserveBottom } = useStageInset();
  const src = useFileUrl(url);
  const box = useRef<HTMLDivElement>(null);
  // The size belongs to the src it was measured from, so a new src is unmeasured without a reset effect: an effect
  // runs after a cached image's load event and would wipe the size for good (the image then stays hidden).
  const [measured, setMeasured] = useState<{ src: string; w: number; h: number } | null>(null);
  const natural = measured && measured.src === src ? measured : null;
  const measure = (img: HTMLImageElement | null) => {
    if (img?.complete && img.naturalWidth > 0 && src && measured?.src !== src) {
      setMeasured({ src, w: img.naturalWidth, h: img.naturalHeight });
    }
  };
  const [viewport, setViewport] = useState({ w: 0, h: 0 });
  /** null = fitted, which follows the viewport size. */
  const [view, setView] = useState<View | null>(null);
  const [dragging, setDragging] = useState(false);
  const pointers = useRef(new Map<number, Point>());
  const fullscreen = useFullscreen(box);

  useEffect(() => {
    setView(null);
  }, [src]);

  useEffect(() => {
    const el = box.current;
    if (!el) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setViewport({ w: entry.contentRect.width, h: entry.contentRect.height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const fitScale =
    natural && viewport.w > 0
      ? clampScale(
          Math.min(
            (viewport.w - 2 * FIT_PADDING) / natural.w,
            (viewport.h - 2 * FIT_PADDING - TOOLBAR_SPACE - reserveBottom) / natural.h,
          ),
        )
      : 1;
  const fit: View = { scale: fitScale, x: 0, y: (TOOLBAR_SPACE - reserveBottom) / 2 };
  const current: View = view ?? fit;

  /** Scale by `factor` keeping the point `at` (relative to the viewport centre) still. */
  const zoomBy = (factor: number, at: Point = { x: 0, y: 0 }) =>
    setView((v) => {
      const c = v ?? fit;
      const scale = clampScale(c.scale * factor);
      const k = scale / c.scale;
      return { scale, x: at.x - (at.x - c.x) * k, y: at.y - (at.y - c.y) * k };
    });
  const panBy = (dx: number, dy: number) =>
    setView((v) => {
      const c = v ?? fit;
      return { ...c, x: c.x + dx, y: c.y + dy };
    });
  const actualSize = (at?: Point) => zoomBy(1 / current.scale, at);

  const fromCentre = (clientX: number, clientY: number): Point => {
    const r = box.current?.getBoundingClientRect();
    return r ? { x: clientX - r.left - r.width / 2, y: clientY - r.top - r.height / 2 } : { x: 0, y: 0 };
  };

  // React registers wheel listeners as passive, so the page would scroll too; this one can cancel it.
  const zoomRef = useRef(zoomBy);
  zoomRef.current = zoomBy;
  useEffect(() => {
    const el = box.current;
    if (!el) return undefined;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      // Trackpads send many small deltas, mouse wheels a few large ones; both map to a smooth exponential zoom.
      const factor = Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.002));
      zoomRef.current(factor, { x: e.clientX - r.left - r.width / 2, y: e.clientY - r.top - r.height / 2 });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    setDragging(true);
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const ps = pointers.current;
    const prev = ps.get(e.pointerId);
    if (!prev) return;
    const next = { x: e.clientX, y: e.clientY };
    if (ps.size === 1) {
      panBy(next.x - prev.x, next.y - prev.y);
    } else if (ps.size === 2) {
      const [other] = [...ps.entries()].filter(([id]) => id !== e.pointerId).map(([, p]) => p);
      if (other) {
        const before = Math.hypot(prev.x - other.x, prev.y - other.y);
        const after = Math.hypot(next.x - other.x, next.y - other.y);
        if (before > 0) zoomBy(after / before, fromCentre((next.x + other.x) / 2, (next.y + other.y) / 2));
      }
    }
    ps.set(e.pointerId, next);
  };
  const onPointerUp = (e: PointerEvent<HTMLDivElement>) => {
    pointers.current.delete(e.pointerId);
    if (pointers.current.size === 0) setDragging(false);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const actions: Record<string, () => void> = {
      "+": () => zoomBy(STEP),
      "=": () => zoomBy(STEP),
      "-": () => zoomBy(1 / STEP),
      "0": () => setView(null),
      "1": () => actualSize(),
      ArrowLeft: () => panBy(PAN_STEP, 0),
      ArrowRight: () => panBy(-PAN_STEP, 0),
      ArrowUp: () => panBy(0, PAN_STEP),
      ArrowDown: () => panBy(0, -PAN_STEP),
    };
    const action = actions[e.key];
    if (action && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      action();
    }
  };

  const fitted = view === null;
  return (
    <div
      ref={box}
      className="viewer image-view"
      data-dragging={dragging || undefined}
      tabIndex={0}
      role="img"
      aria-label={`${alt}. Scroll to zoom, drag to pan, double-click for 100 %.`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onDoubleClick={(e) => (fitted ? actualSize(fromCentre(e.clientX, e.clientY)) : setView(null))}
      onKeyDown={onKeyDown}
    >
      {src ? (
        <img
          className="image-view__img"
          src={src}
          alt=""
          draggable={false}
          ref={measure}
          onLoad={(e) => measure(e.currentTarget)}
          style={{
            visibility: natural ? "visible" : "hidden",
            width: natural?.w,
            height: natural?.h,
            transform: `translate(-50%, -50%) translate(${current.x}px, ${current.y}px) scale(${current.scale})`,
            // Past 200 % show the real pixels instead of a blur, which is what zooming in is for.
            imageRendering: current.scale >= 2 ? "pixelated" : "auto",
          }}
        />
      ) : (
        <Spinner size="lg" />
      )}
      <div
        className="viewer__tools"
        onPointerDown={(e) => e.stopPropagation()}
        onDoubleClick={(e) => e.stopPropagation()}
      >
        <ViewerToolbar
          label="Image view"
          readout={`${Math.round(current.scale * 100)} %`}
          groups={[
            [
              { icon: "zoom-out", label: "Zoom out", shortcut: "−", onClick: () => zoomBy(1 / STEP) },
              { icon: "zoom-in", label: "Zoom in", shortcut: "+", onClick: () => zoomBy(STEP) },
            ],
            [
              { icon: "fit", label: "Fit to view", shortcut: "0", onClick: () => setView(null), pressed: fitted },
              { icon: "actual-size", label: "Actual size", shortcut: "1", onClick: () => actualSize() },
            ],
            ...(fullscreen.supported
              ? [
                  [
                    {
                      icon: fullscreen.active ? ("fullscreen-exit" as const) : ("fullscreen" as const),
                      label: fullscreen.active ? "Exit full screen" : "Full screen",
                      onClick: fullscreen.toggle,
                    },
                  ],
                ]
              : []),
          ]}
        />
      </div>
    </div>
  );
}
