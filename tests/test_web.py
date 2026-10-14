"""Web UI static checks (no Node needed): vendored files match their pins, npm dependencies are pinned with
integrity hashes and no install scripts, the page loads nothing remote, generated files are current.
Type checking and the build itself run with `make typecheck` / `make web-build` (CI job "web")."""

import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_vendored_files_match_vendor_json():
    vendor = json.loads((WEB / "vendor/VENDOR.json").read_text())
    for entry in vendor["files"]:
        data = (WEB / "vendor" / entry["path"]).read_bytes()
        assert len(data) == entry["size"], entry["path"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["path"]
        assert entry["license"]


def test_npm_dependencies_are_exact_and_locked_with_integrity():
    package = json.loads((WEB / "package.json").read_text())
    for group in ("dependencies", "devDependencies"):
        for name, version in package[group].items():
            assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"{name}@{version} is not an exact version"
    lock = json.loads((WEB / "package-lock.json").read_text())
    for path, pkg in lock["packages"].items():
        if not path:
            continue
        assert pkg["resolved"].startswith("https://registry.npmjs.org/"), path
        assert pkg["integrity"].startswith("sha512-"), path
    assert "ignore-scripts=true" in (WEB / ".npmrc").read_text().splitlines()


def test_index_loads_only_local_files():
    html = (WEB / "index.html").read_text()
    refs = re.findall(r'(?:src|href)="([^"]+)"', html)
    assert {"app.js", "app.css", "favicon.svg"} <= set(refs)
    for ref in refs:
        assert not re.match(r"^(https?:)?//", ref), f"remote reference {ref}"


def test_tokens_css_is_generated_from_the_design_system():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/gen_tokens_css.py"), "--check"], capture_output=True)
    assert r.returncode == 0, r.stderr.decode()


def test_api_types_are_generated_from_the_server_models():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/gen_api_types.py"), "--check"], capture_output=True)
    assert r.returncode == 0, r.stderr.decode()
