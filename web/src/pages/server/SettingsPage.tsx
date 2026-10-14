// Server defaults (validated on the server, form generated from its schema), this browser's access token and theme.
import { useCallback, useEffect, useState } from "react";
import { api, type ApiError, type JsonSchema, type RuntimeConfig } from "../../api/client";
import { applyTheme, getTheme, type ThemeChoice } from "../../lib/theme";
import {
  EFFECT_LABELS,
  EFFECTS,
  getTransitionChoice,
  setTransitionChoice,
  type TransitionChoice,
  transitionPage,
} from "../../lib/transitions";
import { getToken, setToken } from "../../lib/token";
import { Button, Card, ErrorText, Hint, type Option, SegmentedControl, Select, TextField } from "../../ui/atoms";
import { type FormValues, SchemaForm, useToast } from "../../ui/organisms";
import { DocPage } from "../../ui/templates";
import { ServerNav } from "./ServerNav";

const THEMES = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
] as const;
const TRANSITIONS: Option<TransitionChoice>[] = (["random", ...EFFECTS, "off"] as const).map((value) => ({
  value,
  label: EFFECT_LABELS[value],
}));

export function SettingsPage() {
  const toast = useToast();
  const [schema, setSchema] = useState<JsonSchema | null>(null);
  const [values, setValues] = useState<RuntimeConfig | null>(null);
  const [saved, setSaved] = useState<RuntimeConfig | null>(null);
  const [token, setTokenValue] = useState(getToken);
  const [theme, setTheme] = useState<ThemeChoice>(getTheme);
  const [transition, setTransition] = useState<TransitionChoice>(getTransitionChoice);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(
    () =>
      Promise.all([api.configSchema(), api.config()]).then(
        ([s, c]) => {
          setSchema(s);
          setValues(c);
          setSaved(c);
          setError(null);
        },
        (e: ApiError) => setError(e),
      ),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    if (!values) return;
    try {
      const c = await api.saveConfig(values);
      setValues(c);
      setSaved(c);
      toast("success", "Settings saved");
    } catch (e) {
      toast("danger", "Can't save the settings", (e as Error).message);
    }
  };
  const dirty = values && saved && JSON.stringify(values) !== JSON.stringify(saved);

  return (
    <DocPage title="Settings" nav={<ServerNav current="settings" />}>
      <div className="card-grid">
        <Card
          title="Server defaults"
          subtitle="Used when a request leaves a value empty"
          footer={
            <Button variant="prominent" disabled={!dirty} onClick={() => void save()}>
              Save changes
            </Button>
          }
        >
          {error ? <ErrorText>{error.message}</ErrorText> : null}
          {schema && values ? (
            <SchemaForm
              schema={schema}
              value={values as unknown as FormValues}
              // the form edits the fields of this schema; the server validates the result on save
              onChange={(v) => setValues(v as unknown as RuntimeConfig)}
            />
          ) : null}
        </Card>
        <div className="stack">
          <Card
            title="Access token"
            subtitle="Only if the server was started with SERVER_TOKEN; kept in this browser"
            footer={
              <Button
                onClick={() => {
                  setToken(token.trim());
                  toast("success", token.trim() ? "Token saved" : "Token removed");
                  void load();
                }}
              >
                Save token
              </Button>
            }
          >
            <TextField label="Token" type="password" value={token} onChange={setTokenValue} autoComplete="off" />
          </Card>
          <Card title="Appearance">
            <SegmentedControl
              aria-label="Theme"
              value={theme}
              options={THEMES}
              onChange={(t) => {
                setTheme(t);
                applyTheme(t);
              }}
            />
            <Select
              label="Page transitions"
              options={TRANSITIONS}
              value={transition}
              onChange={(t) => {
                setTransition(t);
                setTransitionChoice(t);
                // a preview on this page: the same page in, through the chosen effect
                if (t !== "off") transitionPage(() => {}, document.querySelector<HTMLElement>(".app__page"), t);
              }}
            />
            <Hint>Off when the system asks for reduced motion.</Hint>
          </Card>
        </div>
      </div>
    </DocPage>
  );
}
