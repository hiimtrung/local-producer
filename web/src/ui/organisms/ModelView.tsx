// An interactive GLB viewer (Google's <model-viewer>, loaded the first time a model is shown) with view controls:
// drag to orbit, right-drag or two fingers to pan, scroll or pinch to zoom, plus toolbar buttons for each.
import type { ModelViewerElement } from "@google/model-viewer";
import { type Ref, useEffect, useRef, useState } from "react";
import { useFileUrl } from "../../hooks/useFileUrl";
import { useFullscreen } from "../../hooks/useFullscreen";
import { Spinner } from "../atoms";
import { type ViewerTool, ViewerToolbar } from "../molecules";

declare module "react" {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      "model-viewer": {
        ref?: Ref<ModelViewerElement>;
        src: string;
        alt: string;
        "camera-controls"?: boolean;
        "auto-rotate"?: boolean;
        "camera-orbit"?: string;
        "min-camera-orbit"?: string;
        "shadow-intensity"?: string;
        exposure?: string;
        "interaction-prompt"?: "auto" | "none";
        class?: string;
      };
    }
  }
}

/** model-viewer's default framing. */
const HOME_ORBIT = "0deg 75deg 105%";
/** The same orbit spelt differently: setting a property to its current value is a no-op, and the user's dragging
 *  does not change the property, so reset alternates between the two spellings to always take effect. */
const HOME_ORBIT_ALT = "0deg 75deg 105.0001%";
const ORBIT_STEP = Math.PI / 6;
const ZOOM_STEP = 0.8;
/** How long model-viewer takes to glide to a new camera goal (interpolation-decay 50 ms, ~99 % after 1 s). */
const GLIDE_MS = 1000;

let loading: Promise<unknown> | null = null;
const loadViewer = () => (loading ??= import("@google/model-viewer"));

export function ModelView({ url, alt = "Generated 3D model" }: { url: string; alt?: string }) {
  const [ready, setReady] = useState(() => !!customElements.get("model-viewer"));
  const [spinning, setSpinning] = useState(true);
  const src = useFileUrl(url);
  const box = useRef<HTMLDivElement>(null);
  const viewer = useRef<ModelViewerElement>(null);
  const goal = useRef<{ theta: number; phi: number; radius: number; at: number } | null>(null);
  const fullscreen = useFullscreen(box);
  useEffect(() => {
    if (!ready) void loadViewer().then(() => setReady(true));
  }, [ready]);

  /** Move the camera relative to where it is heading: getCameraOrbit() returns the position mid-animation, so a
   *  second press within the glide would otherwise undo the first (zoom, then turn, lost the zoom). */
  const move = (dTheta: number, radiusFactor: number) => {
    const el = viewer.current;
    if (!el) return;
    const recent = goal.current && performance.now() - goal.current.at < GLIDE_MS ? goal.current : null;
    const o = recent ?? el.getCameraOrbit();
    const next = { theta: o.theta + dTheta, phi: o.phi, radius: o.radius * radiusFactor, at: performance.now() };
    goal.current = next;
    el.cameraOrbit = `${next.theta}rad ${next.phi}rad ${next.radius}m`;
  };
  const reset = () => {
    const el = viewer.current;
    if (!el) return;
    goal.current = null;
    el.resetTurntableRotation(0);
    el.cameraTarget = "auto auto auto";
    el.fieldOfView = "auto";
    el.cameraOrbit = el.cameraOrbit === HOME_ORBIT ? HOME_ORBIT_ALT : HOME_ORBIT;
  };

  const groups: ViewerTool[][] = [
    [
      { icon: "zoom-out", label: "Zoom out", shortcut: "−", onClick: () => move(0, 1 / ZOOM_STEP) },
      { icon: "zoom-in", label: "Zoom in", shortcut: "+", onClick: () => move(0, ZOOM_STEP) },
    ],
    [
      { icon: "orbit-left", label: "Turn left", shortcut: "←", onClick: () => move(ORBIT_STEP, 1) },
      { icon: "orbit-right", label: "Turn right", shortcut: "→", onClick: () => move(-ORBIT_STEP, 1) },
      {
        icon: spinning ? "pause" : "play",
        label: spinning ? "Stop turntable" : "Turntable",
        pressed: spinning,
        onClick: () => setSpinning((s) => !s),
      },
    ],
    [{ icon: "fit", label: "Reset view", onClick: reset }],
  ];
  if (fullscreen.supported) {
    groups.push([
      {
        icon: fullscreen.active ? "fullscreen-exit" : "fullscreen",
        label: fullscreen.active ? "Exit full screen" : "Full screen",
        onClick: fullscreen.toggle,
      },
    ]);
  }

  return (
    <div ref={box} className="viewer">
      {ready && src ? (
        <model-viewer
          ref={viewer}
          src={src}
          alt={`${alt}. Drag to orbit, right-drag to pan, scroll to zoom.`}
          camera-controls
          auto-rotate={spinning || undefined}
          camera-orbit={HOME_ORBIT}
          min-camera-orbit="auto auto 20%"
          shadow-intensity="0.8"
          exposure="1.05"
          interaction-prompt="none"
          class="model-view"
        />
      ) : (
        <Spinner size="lg" label="Loading the 3D viewer" />
      )}
      <div className="viewer__tools">
        <ViewerToolbar label="3D view" groups={groups} />
      </div>
    </div>
  );
}
