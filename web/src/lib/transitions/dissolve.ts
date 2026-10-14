// The noise dissolve's mask: frames of smooth value noise thresholded at rising levels, with a soft edge, so the
// new page burns in through organic blobs plus a fine grain. Generated once (~20 small PNGs) into a @keyframes rule
// that steps the mask of ::view-transition-new(page) through them.
const FRAMES = 20;
const SIZE = 192;
const CELLS = 12;
const EDGE = 0.06;

let done = false;

export function ensureDissolveFrames(): void {
  if (done) return;
  done = true;
  // Coarse random grid, smoothed by drawing it up-scaled, plus per-pixel grain.
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
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(coarse, 0, 0, SIZE, SIZE);
  const base = ctx.getImageData(0, 0, SIZE, SIZE);
  const noise = new Float32Array(SIZE * SIZE);
  for (let p = 0; p < noise.length; p++) noise[p] = 0.82 * ((base.data[p * 4] ?? 0) / 255) + 0.18 * Math.random();

  const steps: string[] = [];
  for (let f = 0; f <= FRAMES; f++) {
    const level = -EDGE + (f / FRAMES) * (1 + 2 * EDGE);
    const img = ctx.createImageData(SIZE, SIZE);
    for (let p = 0; p < noise.length; p++) {
      const a = Math.min(1, Math.max(0, (level - (noise[p] ?? 0)) / EDGE + 0.5));
      img.data.set([0, 0, 0, Math.round(a * 255)], p * 4);
    }
    ctx.putImageData(img, 0, 0);
    steps.push(`${((f / FRAMES) * 100).toFixed(2)}% { mask-image: url(${canvas.toDataURL()}); }`);
  }
  const style = document.createElement("style");
  style.id = "vt-dissolve-frames";
  style.textContent = `@keyframes vt-dissolve { ${steps.join(" ")} }`;
  document.head.append(style);
}
