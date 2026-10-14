// Page transitions: a random effect (or the one chosen in Settings) each time the page changes. Most run on the
// View Transitions API, which snapshots the old page (WebGL included) and animates it into the new one with CSS
// (styles/transitions.css); the shatter breaks a copy of the old page into glass shards instead.
// Off when the system asks for reduced motion.
import { ensureDissolveFrames } from "./dissolve";
import { ensureGlitchFilter, startGlitch } from "./glitch";
import { inkFrames } from "./ink";
import { shatter } from "./shatter";

export const EFFECTS = [
  "fade",
  "dissolve",
  "glitch",
  "shatter",
  "reveal",
  "depth",
  "push",
  "zoom",
  "flip",
  "cube",
  "blinds",
  "liquid",
  "diamond",
  "doors",
  "wipe",
  "halftone",
  "tv",
  "ink",
] as const;
export type Effect = (typeof EFFECTS)[number];
export type TransitionChoice = Effect | "random" | "off";

export const EFFECT_LABELS: Record<TransitionChoice, string> = {
  random: "Random",
  fade: "Fade and blur",
  dissolve: "Noise dissolve",
  glitch: "Glitch",
  shatter: "Shatter",
  reveal: "Circle reveal",
  depth: "Depth",
  push: "Push",
  zoom: "Zoom through",
  flip: "Card flip",
  cube: "Cube",
  blinds: "Blinds",
  liquid: "Liquid melt",
  diamond: "Diamond iris",
  doors: "Opening doors",
  wipe: "Soft wipe",
  halftone: "Halftone dots",
  tv: "Old TV",
  ink: "Ink spread",
  off: "Off",
};

const KEY = "local-producer.transition";
const isChoice = (v: string | null): v is TransitionChoice =>
  v === "random" || v === "off" || (EFFECTS as readonly string[]).includes(v ?? "");

export function getTransitionChoice(): TransitionChoice {
  try {
    const v = localStorage.getItem(KEY);
    return isChoice(v) ? v : "random";
  } catch {
    return "random";
  }
}

export function setTransitionChoice(choice: TransitionChoice): void {
  try {
    localStorage.setItem(KEY, choice);
  } catch {
    /* not persisted */
  }
}

export interface Point {
  x: number;
  y: number;
}

// Where the user last pressed (a tab, a button): effects with an origin start there.
let lastPress: (Point & { at: number }) | null = null;
window.addEventListener("pointerdown", (e) => (lastPress = { x: e.clientX, y: e.clientY, at: performance.now() }), {
  capture: true,
  passive: true,
});
const origin = (): Point =>
  lastPress && performance.now() - lastPress.at < 1500
    ? lastPress
    : { x: window.innerWidth / 2, y: window.innerHeight / 2 };

// Random without streaks: effects are dealt from a shuffled deck, so every effect plays once before any repeats and
// the same page is reached a different way each time. A new deck never starts with the effect that ended the last.
let deck: Effect[] = [];
let last: Effect | null = null;
function deal(): Effect {
  if (!deck.length) {
    deck = [...EFFECTS];
    for (let i = deck.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [deck[i], deck[j]] = [deck[j] as Effect, deck[i] as Effect];
    }
    if (deck[deck.length - 1] === last) deck.unshift(deck.pop() as Effect);
  }
  return deck.pop() ?? "fade";
}
function pick(choice: TransitionChoice): Effect | null {
  if (choice === "off" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return null;
  return choice === "random" ? deal() : choice;
}

/** Effects with a direction (push, wipe, cube) get a random one; flips and folds a random axis sign. */
const DIRECTIONS = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
] as const;

/** Run `update` (which must render the new page synchronously, e.g. inside flushSync) with a transition from the
 *  page currently in `page`. */
export function transitionPage(update: () => void, page: HTMLElement | null, choice = getTransitionChoice()): void {
  const effect = page ? pick(choice) : null;
  if (!effect || !page) {
    update();
    return;
  }
  last = effect;
  const at = origin();
  if (effect === "shatter") {
    shatter(page, at, update);
    return;
  }
  if (!document.startViewTransition) {
    update();
    return;
  }
  const root = document.documentElement;
  const box = page.getBoundingClientRect();
  root.style.setProperty("--vt-x", `${at.x - box.left}px`);
  root.style.setProperty("--vt-y", `${at.y - Math.max(box.top, 0)}px`);
  const [dx, dy] = DIRECTIONS[Math.floor(Math.random() * DIRECTIONS.length)] ?? [1, 0];
  // cube and flip turn around one axis; push and wipe may travel any way
  const horizontal = effect === "cube" || effect === "flip" ? true : dx !== 0;
  root.style.setProperty("--vt-dx", String(horizontal ? (dx || 1) : 0));
  root.style.setProperty("--vt-dy", String(horizontal ? 0 : dy));
  root.style.setProperty("--vt-sign", Math.random() < 0.5 ? "1" : "-1");
  root.style.setProperty("--vt-wipe", `${horizontal ? ((dx || 1) > 0 ? 90 : 270) : dy > 0 ? 180 : 0}deg`);
  if (effect === "dissolve") ensureDissolveFrames();
  if (effect === "glitch" || effect === "liquid") ensureGlitchFilter();
  if (effect === "ink") inkFrames({ x: (at.x - box.left) / box.width, y: (at.y - Math.max(box.top, 0)) / window.innerHeight });
  root.dataset.vt = effect;
  const vt = document.startViewTransition(update);
  if (effect === "glitch" || effect === "liquid") void vt.ready.then(() => startGlitch(effect), () => {});
  void vt.finished.finally(() => {
    if (root.dataset.vt === effect) delete root.dataset.vt;
  });
}
