// Icons the Lucent set does not have, drawn to its rules: 24 px grid, 2 px stroke, round caps and joins,
// currentColor. Lucent's own names still go through <Icon>.
const PATHS = {
  image: ["M4 5h16v14H4z", "M4 16l5-5 4 4 3-3 4 4", "M15.5 8.5h.01"],
  cube: ["M12 3l8 4.5v9L12 21l-8-4.5v-9z", "M4 7.5l8 4.5 8-4.5", "M12 12v9"],
  library: ["M4 4h7v7H4z", "M13 4h7v7h-7z", "M4 13h7v7H4z", "M13 13h7v7h-7z"],
  tools: ["M14.5 5.5l4 4", "M4 20l9.5-9.5", "M16 3l5 5-3 3-5-5z"],
  download: ["M12 4v11", "M7 10l5 5 5-5", "M5 20h14"],
  models: [
    "M5 6c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3z",
    "M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6",
    "M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3",
  ],
  blender: ["M9 4h6v4h4v6h-4v6H9v-6H5V8h4z"],
  server: ["M4 4h16v6H4z", "M4 14h16v6H4z", "M8 7h.01", "M8 17h.01"],
  settings: ["M4 7h10", "M18 7h2", "M4 17h4", "M12 17h8", "M16 5v4", "M10 15v4"],
  drag: ["M9 5h.01", "M15 5h.01", "M9 12h.01", "M15 12h.01", "M9 19h.01", "M15 19h.01"],
  "zoom-in": ["M4 11a7 7 0 1 0 14 0a7 7 0 1 0-14 0", "M20 20l-4-4", "M8 11h6", "M11 8v6"],
  "zoom-out": ["M4 11a7 7 0 1 0 14 0a7 7 0 1 0-14 0", "M20 20l-4-4", "M8 11h6"],
  fit: ["M4 9V4h5", "M15 4h5v5", "M20 15v5h-5", "M9 20H4v-5"],
  "actual-size": ["M6 9l2-1v8", "M16 9l2-1v8", "M12 10.5h.01", "M12 14h.01"],
  "orbit-left": ["M4 12a8 8 0 1 0 2.34-5.66", "M4 4v4h4"],
  "orbit-right": ["M20 12a8 8 0 1 1-2.34-5.66", "M20 4v4h-4"],
  play: ["M8 5l11 7-11 7z"],
  pause: ["M9 5v14", "M15 5v14"],
  fullscreen: ["M14 4h6v6", "M20 4l-6 6", "M10 20H4v-6", "M4 20l6-6"],
  "fullscreen-exit": ["M20 4l-6 6", "M14 5v5h5", "M4 20l6-6", "M10 19v-5H5"],
} as const satisfies Record<string, readonly string[]>;

export type AppIconName = keyof typeof PATHS;

export interface AppIconProps {
  name: AppIconName;
  size?: number;
  /** Accessible name; without it the icon is decorative. */
  label?: string;
}

export function AppIcon({ name, size = 20, label }: AppIconProps) {
  return (
    <svg
      className="app-icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
