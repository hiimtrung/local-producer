// The live part of the app bar: the job running now (or "Idle") in the middle, the server's vitals on the right.
// Returns two cells for the bar's grid.
import { useServerActivity } from "../../hooks/useServerActivity";
import { ActiveJobChip, ServerVitals } from "../molecules";

export function HeaderActivity() {
  const { system, error, active } = useServerActivity();
  const [first, ...rest] = active;
  return (
    <>
      <div className="app__activity" aria-live="polite">
        {first ? (
          <ActiveJobChip key={first.id} job={first} waiting={rest.length} />
        ) : system ? (
          <span className="footnote muted">Idle, no job running</span>
        ) : null}
      </div>
      <ServerVitals system={system} error={error} />
    </>
  );
}
