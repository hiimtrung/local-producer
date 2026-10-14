// The ink spread's mask: like the noise dissolve, but the threshold field is the distance from where the user
// pressed, roughened by smooth noise, so the new page floods out from that point in an organic blot. Made per
// transition (the origin moves); ~20 frames of 160 px, a few milliseconds.
const FRAMES = 20;
const SIZE = 160;
const CELLS = 10;
const EDGE = 0.05;
let style: HTMLStyleElement | null = null;

export function inkFrames(origin: { x: number; y: number }): void {
  const coarse = document.createElement("canvas");
  coarse.width = coarse.height = CELLS;
  const cctx = coarse.getContext("2d");
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = SIZE;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!cctx || !ctx) return;
  const grid = cctx.createImageData(CELLS, CELLS);
  for (let i = 0; i < grid.data.length; i += 4) {
    const v = Math.random() * 255;
    grid.data.set([v, v, v, 255], i);
  }
  cctx.putImageData(grid, 0, 0);
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(coarse, 0, 0, SIZE, SIZE);
  const base = ctx.getImageData(0, 0, SIZE, SIZE);
  const field = new Float32Array(SIZE * SIZE);
  let max = 0;
  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      const p = y * SIZE + x;
      const d = Math.hypot(x / SIZE - origin.x, y / SIZE - origin.y);
      const v = d + 0.35 * ((base.data[p * 4] ?? 0) / 255);
      field[p] = v;
      max = Math.max(max, v);
    }
  }
  const steps: string[] = [];
  for (let f = 0; f <= FRAMES; f++) {
    // ease-out: the blot spreads fast, then slows at the far corners
    const t = 1 - (1 - f / FRAMES) ** 2;
    const level = -EDGE + t * (max + 2 * EDGE);
    const img = ctx.createImageData(SIZE, SIZE);
    for (let p = 0; p < field.length; p++) {
      const a = Math.min(1, Math.max(0, (level - (field[p] ?? 0)) / EDGE + 0.5));
      img.data.set([0, 0, 0, Math.round(a * 255)], p * 4);
    }
    ctx.putImageData(img, 0, 0);
    steps.push(`${((f / FRAMES) * 100).toFixed(2)}% { mask-image: url(${canvas.toDataURL()}); }`);
  }
  style ??= document.head.appendChild(document.createElement("style"));
  style.id = "vt-ink-frames";
  style.textContent = `@keyframes vt-ink { ${steps.join(" ")} }`;
}
