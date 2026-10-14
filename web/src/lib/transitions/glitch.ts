// SVG filters for the glitch (turbulence in horizontal streaks tears the old page apart and the new one back
// together) and the liquid melt (slow, round turbulence makes both pages ripple like water), their strength animated
// with SMIL when the transition starts.
const NS = "http://www.w3.org/2000/svg";
let svg: SVGSVGElement | null = null;

const filter = (id: string, values: string, frequency = "0.0015 0.28", dur = "0.6s") => `
  <filter id="${id}" x="-5%" y="-5%" width="110%" height="110%" color-interpolation-filters="sRGB">
    <feTurbulence type="fractalNoise" baseFrequency="${frequency}" numOctaves="2" seed="3" result="noise">
      <animate attributeName="seed" values="3;9;14;21;5" dur="${dur}" begin="indefinite" fill="freeze" />
    </feTurbulence>
    <feDisplacementMap in="SourceGraphic" in2="noise" scale="0" xChannelSelector="R" yChannelSelector="B">
      <animate attributeName="scale" values="${values}" dur="${dur}" begin="indefinite" fill="freeze" />
    </feDisplacementMap>
  </filter>`;

export function ensureGlitchFilter(): void {
  if (svg) return;
  svg = document.createElementNS(NS, "svg");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("width", "0");
  svg.setAttribute("height", "0");
  svg.style.position = "absolute";
  svg.innerHTML =
    filter("vt-noise-out", "0;60;20;140;260") +
    filter("vt-noise-in", "220;90;150;30;0") +
    filter("vt-liquid-out", "0;40;110;200", "0.008 0.012", "0.8s") +
    filter("vt-liquid-in", "200;110;40;0", "0.008 0.012", "0.8s");
  // the liquid's turbulence flows rather than flickers: no seed jumps
  svg.querySelectorAll('[id^="vt-liquid"] feTurbulence animate').forEach((a) => a.remove());
  document.body.append(svg);
}

export function startGlitch(effect: "glitch" | "liquid"): void {
  const ids = effect === "glitch" ? "#vt-noise-out, #vt-noise-in" : "#vt-liquid-out, #vt-liquid-in";
  svg?.querySelectorAll(`:is(${ids}) animate`).forEach((a) => (a as SVGAnimationElement).beginElement());
}
