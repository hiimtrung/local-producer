"""Generate web/styles/tokens.css from the Lucent design system's tokens.json (web/vendor/lucent/tokens.json).

Every token becomes a CSS custom property named after it (--accent, --space-4, --radius-lg, --shadow-glass, ...);
themed values go under [data-theme="light"] / [data-theme="dark"] on <html>, the first theme also under :root. Type
styles become classes named after them (.headline, .body, ...) and --font-<family> properties.

usage: python scripts/gen_tokens_css.py [--check]   (--check: exit 1 when the file is out of date; CI runs it)
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "web/vendor/lucent/tokens.json"
OUT = ROOT / "web/styles/tokens.css"
FAMILIES = ("spacing", "radius", "shadow", "blur", "size", "zIndex")


def generate(tokens):
    themes = [t["id"] for t in tokens["color"]["themes"]]
    first = themes[0]
    per_theme = {t: [] for t in themes}
    plain = []

    def add(name, value):
        if isinstance(value, dict):
            for t in themes:
                per_theme[t].append(f"  --{name}: {value.get(t, value[first])};")
        else:
            plain.append(f"  --{name}: {value};")

    for tok in tokens["color"]["tokens"]:
        add(tok["name"], tok["value"])
    for fam in FAMILIES:
        for tok in tokens.get(fam, {}).get("tokens", []):
            add(tok["name"], tok["value"])
    for name, stack in tokens["type"]["families"].items():
        plain.append(f"  --font-{name}: {stack};")

    lines = [f"/* {tokens['name']} — generated from web/vendor/lucent/tokens.json by scripts/gen_tokens_css.py */", ""]
    lines += [":root {", *plain, "}", ""]
    for t in themes:
        sel = f':root, [data-theme="{t}"]' if t == first else f'[data-theme="{t}"]'
        lines += [f"{sel} {{", f"  color-scheme: {t if t in ('light', 'dark') else 'normal'};", *per_theme[t], "}", ""]
    for group in tokens["type"]["groups"]:
        fam = group["family"]
        for st in group["styles"]:
            lines.append(
                f".{st['name']} {{ font-family: var(--font-{fam}); font-size: {st['fontSize']}; "
                f"line-height: {st['lineHeight']}; font-weight: {st['fontWeight']}; "
                f"letter-spacing: {st.get('letterSpacing', '0px')}; }}"
            )
    return "\n".join(lines) + "\n"


def main(argv):
    css = generate(json.loads(SRC.read_text()))
    if "--check" in argv:
        if not OUT.exists() or OUT.read_text() != css:
            print(f"{OUT.relative_to(ROOT)} is out of date: run python scripts/gen_tokens_css.py", file=sys.stderr)
            return 1
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(css)
    print(OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
