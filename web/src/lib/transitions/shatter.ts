// The shatter: the old page, on its wallpaper, breaks like a pane of glass from where the user pressed. Rays and
// rings around that point cut it into shards (each a clipped copy of the page), which crack apart, spin in 3D and
// fall away while the new page fades in underneath.
import type { Point } from "./index";

const RAYS = 9;
const RINGS = [0.16, 0.42, 1.6]; // fractions of the screen diagonal; the last reaches past every corner
const DURATION = 900;

interface Shard {
  points: Point[];
  centre: Point;
}

function cut(at: Point, w: number, h: number): Shard[] {
  const diag = Math.hypot(w, h);
  const angles = Array.from({ length: RAYS }, (_, i) => ((i + 0.3 + Math.random() * 0.4) / RAYS) * 2 * Math.PI);
  // Each ring's radius wobbles per ray, so the cracks are not perfect circles.
  const radius = RINGS.map((r) => angles.map(() => r * diag * (0.8 + Math.random() * 0.4)));
  const pt = (ring: number, ray: number): Point => {
    const a = angles[ray % RAYS] ?? 0;
    const r = radius[ring]?.[ray % RAYS] ?? 0;
    return { x: at.x + Math.cos(a) * r, y: at.y + Math.sin(a) * r };
  };
  const shards: Shard[] = [];
  for (let j = 0; j < RAYS; j++) shards.push(shardOf([at, pt(0, j), pt(0, j + 1)]));
  for (let ring = 1; ring < RINGS.length; ring++) {
    for (let j = 0; j < RAYS; j++) {
      shards.push(shardOf([pt(ring - 1, j), pt(ring, j), pt(ring, j + 1), pt(ring - 1, j + 1)]));
    }
  }
  return shards;
}

function shardOf(points: Point[]): Shard {
  const centre = {
    x: points.reduce((s, p) => s + p.x, 0) / points.length,
    y: points.reduce((s, p) => s + p.y, 0) / points.length,
  };
  return { points, centre };
}

/** A static copy of the page: canvases (the 3D viewer's WebGL) become images, glass loses its live blur. */
function copyOf(page: HTMLElement): HTMLElement {
  const copy = page.cloneNode(true) as HTMLElement;
  const live = page.querySelectorAll("model-viewer");
  copy.querySelectorAll("model-viewer").forEach((el, i) => {
    const viewer = live[i] as (Element & { toDataURL?: (type?: string) => string }) | undefined;
    const img = document.createElement("img");
    try {
      img.src = viewer?.toDataURL?.("image/png") ?? "";
    } catch {
      /* an unloaded viewer: leave the area empty */
    }
    img.className = el.className;
    img.style.objectFit = "contain";
    el.replaceWith(img);
  });
  copy.removeAttribute("id");
  copy.setAttribute("aria-hidden", "true");
  copy.style.viewTransitionName = "none";
  return copy;
}

export function shatter(page: HTMLElement, at: Point, update: () => void): void {
  const w = window.innerWidth;
  const h = window.innerHeight;
  const box = page.getBoundingClientRect();
  const wall = getComputedStyle(document.body);
  const copy = copyOf(page);

  const layer = document.createElement("div");
  layer.className = "vt-shatter";
  layer.setAttribute("aria-hidden", "true");
  const flash = document.createElement("div");
  flash.className = "vt-shatter__flash";
  flash.style.background = `radial-gradient(circle at ${at.x}px ${at.y}px, rgba(255,255,255,.75), rgba(255,255,255,0) 35%)`;

  const shards = cut(at, w, h);
  const maxDist = Math.max(...shards.map((s) => Math.hypot(s.centre.x - at.x, s.centre.y - at.y)));
  const animations: Animation[] = [];
  for (const s of shards) {
    const el = document.createElement("div");
    el.className = "vt-shatter__shard";
    el.style.backgroundColor = wall.backgroundColor;
    el.style.backgroundImage = wall.backgroundImage;
    el.style.clipPath = `polygon(${s.points.map((p) => `${p.x}px ${p.y}px`).join(",")})`;
    el.style.transformOrigin = `${s.centre.x}px ${s.centre.y}px`;
    const content = copy.cloneNode(true) as HTMLElement;
    Object.assign(content.style, {
      position: "absolute",
      left: `${box.left}px`,
      top: `${box.top}px`,
      width: `${box.width}px`,
    });
    el.append(content);
    layer.append(el);

    const dx = s.centre.x - at.x;
    const dy = s.centre.y - at.y;
    const dist = Math.hypot(dx, dy) || 1;
    const near = 1 - dist / (maxDist || 1);
    const speed = 220 + near * 520 + Math.random() * 200;
    const tx = (dx / dist) * speed;
    const ty = (dy / dist) * speed + 380 + Math.random() * 260; // gravity
    const spin = (Math.random() - 0.5) * 2;
    animations.push(
      el.animate(
        [
          { transform: "none", opacity: 1, filter: "brightness(1)" },
          {
            // the crack: shards part a few pixels and catch the light
            offset: 0.14,
            transform: `translate(${(dx / dist) * 6}px, ${(dy / dist) * 6}px)`,
            opacity: 1,
            filter: "brightness(1.12)",
          },
          {
            transform:
              `translate3d(${tx}px, ${ty}px, ${80 + near * 220}px) ` +
              `rotateX(${spin * 70}deg) rotateY(${-spin * 55}deg) rotateZ(${spin * 40}deg) scale(${0.85 + Math.random() * 0.2})`,
            opacity: 0,
            filter: "brightness(0.9)",
          },
        ],
        {
          duration: DURATION * (0.8 + Math.random() * 0.3),
          delay: (1 - near) * 110,
          easing: "cubic-bezier(.45,.05,.75,.4)",
          fill: "forwards",
        },
      ),
    );
  }
  layer.append(flash);
  document.body.append(layer);
  flash.animate([{ opacity: 0 }, { opacity: 1, offset: 0.2 }, { opacity: 0 }], { duration: 420, easing: "ease-out" });

  update();
  window.scrollTo(0, 0);
  page.animate(
    [
      { opacity: 0, transform: "scale(0.97)", filter: "blur(8px)" },
      { opacity: 1, transform: "none", filter: "none" },
    ],
    { duration: 650, delay: 180, easing: "cubic-bezier(.2,.8,.2,1)", fill: "backwards" },
  );
  void Promise.allSettled(animations.map((a) => a.finished)).then(() => layer.remove());
}
