// One labelled value on a status page; with a tone it is shown as a badge; detail is a smaller line under it.
import { Badge, type Tone } from "../atoms";

export function Fact({ label, value, tone, detail }: { label: string; value: string; tone?: Tone; detail?: string }) {
  return (
    <div className="fact">
      <span className="footnote muted">{label}</span>
      {tone ? (
        <Badge tone={tone} icon>
          {value}
        </Badge>
      ) : (
        <span className="title-3">{value}</span>
      )}
      {detail ? <span className="footnote muted">{detail}</span> : null}
    </div>
  );
}
