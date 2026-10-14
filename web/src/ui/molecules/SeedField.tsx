// The random seed: a switch for "random" (-1) and the number otherwise.
import { Switch } from "../atoms";
import { NumberField } from "./NumberField";

export interface SeedFieldProps {
  seed: number;
  onChange: (seed: number) => void;
  /** The seed the switch restores when random is turned off. */
  fixed?: number;
}

export function SeedField({ seed, onChange, fixed = 7 }: SeedFieldProps) {
  const random = seed < 0;
  return (
    <div className="field">
      <Switch label="Random seed" checked={random} onChange={(on) => onChange(on ? -1 : fixed)} />
      {random ? null : (
        <NumberField
          label="Seed"
          min={0}
          max={2147483647}
          hint="The same seed and settings give the same result"
          value={seed}
          onChange={onChange}
        />
      )}
    </div>
  );
}
