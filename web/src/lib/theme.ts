// Light / dark / follow the system, stored in this browser. Lucent reads data-theme on <html>.
export type ThemeChoice = "system" | "light" | "dark";
const KEY = "local-producer.theme";
const media = window.matchMedia("(prefers-color-scheme: dark)");

export function getTheme(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(choice: ThemeChoice): void {
  try {
    localStorage.setItem(KEY, choice);
  } catch {
    /* not persisted */
  }
  const dark = choice === "dark" || (choice === "system" && media.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

media.addEventListener("change", () => {
  if (getTheme() === "system") applyTheme("system");
});
