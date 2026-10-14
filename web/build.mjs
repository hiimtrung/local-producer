// Build the web UI into dist/ (served by the GPU server): one ES module bundle (app.js, with model-viewer split into a
// chunk loaded on first use) and one stylesheet (app.css), plus index.html and the favicon.
//   node build.mjs           production build
//   node build.mjs --dev     unminified, development React (readable errors)
//   node build.mjs --watch   --dev and rebuild on change (with `make web-dev`)
import { copyFile, mkdir, rm } from "node:fs/promises";
import * as esbuild from "esbuild";

const watch = process.argv.includes("--watch");
const dev = watch || process.argv.includes("--dev"); // readable output, development React
const OUT = "dist";

async function copyStatic() {
  await copyFile("index.html", `${OUT}/index.html`);
  await copyFile("favicon.svg", `${OUT}/favicon.svg`);
}

/** @type {import("esbuild").BuildOptions} */
const options = {
  entryPoints: { app: "src/main.tsx" },
  outdir: OUT,
  bundle: true,
  format: "esm",
  splitting: true,
  chunkNames: "chunks/[name]-[hash]",
  target: "es2022",
  minify: !dev,
  sourcemap: "linked",
  legalComments: "linked",
  jsx: "automatic",
  define: { "process.env.NODE_ENV": JSON.stringify(dev ? "development" : "production") },
  logLevel: "info",
  plugins: [{ name: "static", setup: (b) => b.onEnd(copyStatic) }],
};

await rm(OUT, { recursive: true, force: true });
await mkdir(OUT, { recursive: true });
if (watch) {
  const ctx = await esbuild.context(options);
  await ctx.watch();
} else {
  await esbuild.build(options);
}
