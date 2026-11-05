#!/usr/bin/env python3
"""Check the documentation tree.

Runs in CI and from ``make docs-check``. It fails on the rot that reviews do not catch:

1. a page under ``docs/`` without the header table (``Status``, ``Owner``, ``Last verified``);
   archived pages only need ``Status: Superseded`` and a link to their replacement;
2. a page that cannot be reached from ``docs/README.md`` (an orphan);
3. a relative link whose path does not exist, or whose ``#anchor`` does not exist;
4. a missing or duplicated ``H1``, or two pages sharing the same ``H1``;
5. Vietnamese or CJK text in a project file (``AGENTS.md``: English only, except quoted
   video-language strings, which must be marked with ``docs-check: allow-non-english``);
6. an ADR file that is not listed in ``docs/adr/README.md``, or a numbering gap.

External links are deliberately not fetched: they rate-limit and rot, and a red build for
someone else's 404 teaches people to ignore CI.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ARCHIVE = DOCS / "archive"
ADR = DOCS / "adr"
INDEX = DOCS / "README.md"

HEADER_FIELDS = ("**Status**", "**Owner**", "**Last verified**")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
LINK_RE = re.compile(r"\[[^\]]*\]\(\s*(<[^>]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
ALLOW_MARKER = "docs-check: allow-non-english"

# Scripts that cannot be English prose. CJK, kana, hangul.
CJK_RANGES = (
    (0x2E80, 0x2EFF),  # CJK radicals
    (0x3000, 0x303F),  # CJK punctuation
    (0x3040, 0x30FF),  # hiragana + katakana
    (0x3400, 0x4DBF),  # CJK extension A
    (0x4E00, 0x9FFF),  # CJK unified ideographs
    (0xAC00, 0xD7AF),  # hangul syllables
    (0xF900, 0xFAFF),  # CJK compatibility ideographs
    (0xFF00, 0xFFEF),  # halfwidth/fullwidth forms
)
# Letters that exist for Vietnamese and are essentially absent from English words.
VIETNAMESE_CHARS = set("ăĂđĐơƠưƯ" + "".join(chr(cp) for cp in range(0x1EA0, 0x1EFA)))


class Problem:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, page: Path, message: str, line: int | None = None) -> None:
        where = page.relative_to(ROOT).as_posix()
        if line is not None:
            where = f"{where}:{line}"
        self.items.append(f"{where}: {message}")

    def report(self) -> int:
        if not self.items:
            print(f"docs-check: OK ({len(list(DOCS.rglob('*.md')))} pages)")
            return 0
        print("docs-check: FAILED", file=sys.stderr)
        for item in self.items:
            print(f"  {item}", file=sys.stderr)
        return 1


def read_page(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def without_fences(text: str) -> list[str]:
    """Return the lines, with fenced blocks blanked out (line numbers preserved)."""
    lines = text.splitlines()
    inside = False
    out: list[str] = []
    for line in lines:
        if FENCE_RE.match(line):
            inside = not inside
            out.append("")
            continue
        out.append("" if inside else line)
    return out


def slugify(title: str) -> str:
    """GitHub-style heading anchor, close enough for this tree."""
    slug = title.strip().lower()
    slug = re.sub(r"`|\*|_", "", slug)
    slug = re.sub(r"[^\w\- ]", "", slug, flags=re.UNICODE)
    return slug.replace(" ", "-")


def anchors(page: Path) -> set[str]:
    seen: dict[str, int] = {}
    result: set[str] = set()
    for line in without_fences(read_page(page)):
        match = HEADING_RE.match(line)
        if not match:
            continue
        base = slugify(match.group(2))
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.add(base if count == 0 else f"{base}-{count}")
    return result


def links(page: Path) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for number, line in enumerate(without_fences(read_page(page)), start=1):
        for match in LINK_RE.finditer(line):
            target = match.group(1)
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            found.append((number, target))
    return found


def check_header(problem: Problem, page: Path, text: str) -> None:
    head = "\n".join(text.splitlines()[:25])
    if page.parent == ARCHIVE:
        if "**Status**" not in head or "superseded" not in head.lower():
            problem.add(page, "archived page needs '**Status** | Superseded ...' in its header table")
        if not any(t.endswith(".md") and "://" not in t for _, t in links(page)):
            problem.add(page, "archived page needs a relative link to the page(s) that replaced it")
        return
    for field in HEADER_FIELDS:
        if field not in head:
            problem.add(page, f"header table is missing {field}")
    match = re.search(r"\*\*Last verified\*\*\s*\|\s*([^|]+)\|", head)
    if match and not DATE_RE.search(match.group(1)):
        problem.add(page, "**Last verified** must be a YYYY-MM-DD date")


def check_headings(problem: Problem, page: Path, titles: dict[str, list[Path]]) -> None:
    h1: list[str] = []
    for line in without_fences(read_page(page)):
        match = HEADING_RE.match(line)
        if not match:
            continue
        if len(match.group(1)) == 1:
            h1.append(match.group(2).strip())
    if not h1:
        problem.add(page, "no H1")
    elif len(h1) > 1:
        problem.add(page, f"{len(h1)} H1 headings; exactly one is allowed")
    titles.setdefault(h1[0], []).append(page)


def check_links(problem: Problem, page: Path) -> None:
    for line_number, target in links(page):
        if not target or target.startswith(("http://", "https://", "mailto:", "tel:")):
            continue
        path_part, _, fragment = target.partition("#")
        if not path_part:
            if fragment and fragment not in anchors(page):
                problem.add(page, f"anchor '#{fragment}' not found on this page", line_number)
            continue
        resolved = (page.parent / path_part).resolve()
        try:
            resolved.relative_to(ROOT)
        except ValueError:
            problem.add(page, f"link escapes the repository: {target}", line_number)
            continue
        if not resolved.exists():
            problem.add(page, f"link target does not exist: {target}", line_number)
            continue
        if fragment and resolved.suffix == ".md" and resolved.is_file() and fragment not in anchors(resolved):
            problem.add(page, f"anchor '#{fragment}' not found in {target}", line_number)


def reachable() -> set[Path]:
    """Pages reachable from docs/README.md by following relative links."""
    walked: set[Path] = {INDEX}
    queue = [INDEX]
    while queue:
        page = queue.pop()
        for _, target in links(page):
            if target.startswith(("http://", "https://", "mailto:", "tel:")):
                continue
            path_part = target.partition("#")[0]
            if not path_part:
                continue
            resolved = (page.parent / path_part).resolve()
            if resolved.is_dir():
                resolved = resolved / "README.md"
            if resolved.suffix != ".md" or not resolved.is_file():
                continue
            if DOCS not in resolved.parents or resolved in walked:
                continue
            walked.add(resolved)
            queue.append(resolved)
    return walked


def check_orphans(problem: Problem, pages: list[Path]) -> None:
    seen = reachable()
    for page in pages:
        if page not in seen:
            problem.add(page, "orphan: not linked from docs/README.md (directly or through another page)")


def check_english(problem: Problem, page: Path) -> None:
    for number, line in enumerate(without_fences(read_page(page)), start=1):
        if ALLOW_MARKER in line:
            continue
        for char in line:
            code = ord(char)
            if any(start <= code <= end for start, end in CJK_RANGES) or char in VIETNAMESE_CHARS:
                problem.add(
                    page,
                    f"non-English text (U+{code:04X}); mark a quoted video-language string with '{ALLOW_MARKER}'",
                    number,
                )
                break


def check_adr_index(problem: Problem) -> None:
    adr_pages = sorted(ADR.glob("[0-9][0-9][0-9][0-9]-*.md"))
    index_text = read_page(ADR / "README.md") if (ADR / "README.md").is_file() else ""
    numbers: list[int] = []
    for page in adr_pages:
        number = int(page.name[:4])
        numbers.append(number)
        if page.name not in index_text:
            problem.add(ADR / "README.md", f"ADR {page.name} is missing from the index table")
    for expected, actual in enumerate(numbers, start=1):
        if expected != actual:
            problem.add(ADR / "README.md", f"ADR numbering gap: expected {expected:04d}, found {actual:04d}")
            break


def main() -> int:
    if not INDEX.is_file():
        print(f"docs-check: {INDEX} is missing", file=sys.stderr)
        return 1
    problem = Problem()
    pages = sorted(DOCS.rglob("*.md"))
    titles: dict[str, list[Path]] = {}

    for page in pages:
        text = read_page(page)
        check_header(problem, page, text)
        check_headings(problem, page, titles)
        check_links(problem, page)
        check_english(problem, page)

    for title, owners in titles.items():
        if len(owners) > 1:
            listing = ", ".join(p.relative_to(ROOT).as_posix() for p in owners)
            problem.add(owners[0], f"duplicate H1 '{title}' also used by: {listing}")

    check_orphans(problem, pages)
    check_adr_index(problem)
    return problem.report()


if __name__ == "__main__":
    raise SystemExit(main())
