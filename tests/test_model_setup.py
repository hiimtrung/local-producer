"""Model download/installation (server/model_setup.py): manifest rules, verification, resume, safe extraction."""

import hashlib
import io
import json
import stat
import tarfile
import zipfile

import pytest

from app import model_setup
from app.model_setup import SetupError

DOMAINS = ["huggingface.co", "hf.co", "github.com", "githubusercontent.com"]


def sha(b):
    return hashlib.sha256(b).hexdigest()


class FakeResponse(io.BytesIO):
    def __init__(self, data, status=200):
        super().__init__(data)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeOpener:
    """Serves bytes per URL, honours Range like a real server, records requests."""

    def __init__(self, files):
        self.files, self.requests = files, []

    def open(self, req, timeout=None):
        self.requests.append(req)
        data = self.files[req.full_url]
        rng = req.get_header("Range")
        if rng:
            start = int(rng.split("=")[1].rstrip("-"))
            return FakeResponse(data[start:], 206)
        return FakeResponse(data)


# ---------------------------------------------------------------- manifest rules


def test_the_shipped_manifest_is_valid_and_pinned():
    m = model_setup.load_manifest()
    for it in m["items"]:
        src = it["source"] if it["kind"] == "convert" else it
        assert "/resolve/main/" not in src["url"], "Hugging Face URLs must pin a revision"
        assert src["url"].startswith("https://")
    assert len({it["dest"] for it in m["items"]}) == len(m["items"])


@pytest.mark.parametrize(
    "url",
    [
        "http://huggingface.co/x",
        "https://evilhuggingface.co/x",
        "https://huggingface.co.evil.com/x",
        "https://example.com/x",
        "file:///etc/passwd",
    ],
)
def test_check_url_rejects(url):
    with pytest.raises(SetupError):
        model_setup.check_url(url, DOMAINS)


def test_check_url_accepts_cdn_subdomains():
    model_setup.check_url("https://us.aws.cdn.hf.co/xet/abc", DOMAINS)
    model_setup.check_url("https://release-assets.githubusercontent.com/a", DOMAINS)


@pytest.mark.parametrize("rel", ["../etc/passwd", "/abs", "a/../../b", ".", ""])
def test_safe_relpath_rejects(rel):
    with pytest.raises(SetupError):
        model_setup.safe_relpath(rel)


def test_manifest_with_an_escaping_dest_is_rejected():
    m = {
        "version": 1,
        "allowed_domains": DOMAINS,
        "items": [{"id": "x", "kind": "file", "url": "https://hf.co/a", "size": 1, "sha256": "0" * 64, "dest": "../x"}],
    }
    with pytest.raises(SetupError):
        model_setup.validate_manifest(m)


# ---------------------------------------------------------------- fetch


def test_fetch_verifies_and_renames(tmp_path):
    data = b"weights" * 1000
    url = "https://huggingface.co/r/resolve/abc/w.gguf"
    out = tmp_path / "w.gguf"
    model_setup.fetch(url, len(data), sha(data), str(out), DOMAINS, opener=FakeOpener({url: data}))
    assert out.read_bytes() == data and not (tmp_path / "w.gguf.part").exists()


def test_fetch_hash_mismatch_deletes_the_partial_file(tmp_path):
    url = "https://huggingface.co/r/resolve/abc/w.gguf"
    out = tmp_path / "w.gguf"
    with pytest.raises(SetupError, match="verification failed"):
        model_setup.fetch(url, 4, sha(b"good"), str(out), DOMAINS, opener=FakeOpener({url: b"evil"}))
    assert not out.exists() and not (tmp_path / "w.gguf.part").exists()


def test_fetch_resumes_from_the_part_file(tmp_path):
    data = bytes(range(256)) * 100
    url = "https://huggingface.co/r/resolve/abc/w.gguf"
    out = tmp_path / "w.gguf"
    (tmp_path / "w.gguf.part").write_bytes(data[:1000])
    opener = FakeOpener({url: data})
    model_setup.fetch(url, len(data), sha(data), str(out), DOMAINS, opener=opener)
    assert opener.requests[0].get_header("Range") == "bytes=1000-"
    assert out.read_bytes() == data


# ---------------------------------------------------------------- extraction


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data, mode in entries:
            info = zipfile.ZipInfo(name)
            info.external_attr = mode << 16
            z.writestr(info, data)
    return buf.getvalue()


def test_zip_extraction_strips_the_prefix_and_keeps_safe_symlinks(tmp_path):
    archive = tmp_path / "a.zip"
    archive.write_bytes(
        _zip(
            [
                ("build/bin/sd-cli", b"#!/bin/sh\n", stat.S_IFREG | 0o755),
                ("build/bin/libx.so.1.0", b"ELF", stat.S_IFREG | 0o644),
                ("build/bin/libx.so", b"libx.so.1.0", stat.S_IFLNK | 0o777),
                ("README.md", b"outside the prefix", stat.S_IFREG | 0o644),
            ]
        )
    )
    out = tmp_path / "out"
    out.mkdir()
    model_setup._extract_zip(str(archive), str(out), "build/bin/")
    assert (out / "sd-cli").stat().st_mode & 0o111
    assert (out / "libx.so").is_symlink() and (out / "libx.so").resolve().name == "libx.so.1.0"
    assert not (out / "README.md").exists()


@pytest.mark.parametrize(
    "name, data, mode",
    [
        ("build/bin/../../evil", b"x", stat.S_IFREG | 0o644),
        ("build/bin/link", b"../../etc/passwd", stat.S_IFLNK | 0o777),
    ],
)
def test_zip_extraction_rejects_escapes(tmp_path, name, data, mode):
    archive = tmp_path / "a.zip"
    archive.write_bytes(_zip([(name, data, mode)]))
    with pytest.raises(SetupError):
        model_setup._extract_zip(str(archive), str(tmp_path / "out"), "build/bin/")


def test_tar_extraction_rejects_path_traversal(tmp_path):
    archive = tmp_path / "a.tar.gz"
    with tarfile.open(archive, "w:gz") as t:
        info = tarfile.TarInfo("../evil")
        info.size = 1
        t.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(tarfile.TarError):
        model_setup._extract_tar(str(archive), str(tmp_path / "out"))


def test_text_symlinks_from_release_zips_become_links(tmp_path):
    (tmp_path / "libggml.so.0.25.3").write_bytes(b"ELF")
    (tmp_path / "libggml.so.0").write_text("libggml.so.0.25.3")
    model_setup._relink_text_symlinks(str(tmp_path))
    assert (tmp_path / "libggml.so.0").is_symlink()


# ---------------------------------------------------------------- end to end


def test_download_installs_files_and_archives_then_reports_ready(tmp_path, monkeypatch):
    weights = b"gguf-weights" * 50
    tgz = io.BytesIO()
    with tarfile.open(fileobj=tgz, mode="w:gz") as t:
        info = tarfile.TarInfo("trellis-cli")
        info.size, info.mode = 3, 0o755
        t.addfile(info, io.BytesIO(b"bin"))
    tgz = tgz.getvalue()
    urls = {
        "https://github.com/o/r/releases/download/v1/t.tar.gz": tgz,
        "https://huggingface.co/r/resolve/a/w": weights,
    }
    m = {
        "version": 1,
        "allowed_domains": DOMAINS,
        "items": [
            {
                "id": "weights",
                "kind": "file",
                "url": "https://huggingface.co/r/resolve/a/w",
                "size": len(weights),
                "sha256": sha(weights),
                "dest": "trellis2/w.gguf",
            },
            {
                "id": "cli",
                "kind": "archive",
                "format": "tar.gz",
                "url": "https://github.com/o/r/releases/download/v1/t.tar.gz",
                "size": len(tgz),
                "sha256": sha(tgz),
                "dest": "trellis-bin",
                "check": "trellis-cli",
            },
        ],
    }
    model_setup.validate_manifest(m)
    monkeypatch.setattr(model_setup, "MODELS", str(tmp_path))
    assert not model_setup.status(m).ready
    progress = model_setup.Progress()
    model_setup.download(m, progress, opener=FakeOpener(urls))
    assert model_setup.status(m).ready
    assert (tmp_path / "trellis2/w.gguf").read_bytes() == weights
    assert (tmp_path / "trellis-bin/trellis-cli").stat().st_mode & 0o111
    snap = progress.snapshot()
    assert not snap.running and snap.error == "" and snap.done_items == 2
    assert model_setup.verify(m, log=lambda *_: None) == []
    json.loads(snap.model_dump_json())  # the server returns it as JSON
