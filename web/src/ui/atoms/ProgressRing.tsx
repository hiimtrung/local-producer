// A small circular progress: a ring filled to `value` (0..1), or a spinning arc while the value is unknown.
export interface ProgressRingProps {
  value: number | null;
  size?: number;
  label: string;
}

export function ProgressRing({ value, size = 22, label }: ProgressRingProps) {
  const r = 9;
  const c = 2 * Math.PI * r;
  const known = value != null;
  return (
    <svg
      className={`progress-ring${known ? "" : " progress-ring--spin"}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={known ? Math.round(value * 100) : undefined}
    >
      <circle className="progress-ring__track" cx="12" cy="12" r={r} />
      <circle
        className="progress-ring__fill"
        cx="12"
        cy="12"
        r={r}
        strokeDasharray={c}
        strokeDashoffset={known ? c * (1 - Math.min(1, Math.max(0, value))) : c * 0.7}
      />
    </svg>
  );
}
