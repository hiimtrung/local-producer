"""Prompt framing and log parsing of the Blender add-on (blender/local_producer/prompts.py, no bpy needed)."""

import ast
import pathlib

import prompts

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _make_sample_prompt():
    """PROMPT from scripts/make_sample.py, read without running the script (it calls the server)."""
    tree = ast.parse((ROOT / "scripts/make_sample.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "PROMPT" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("PROMPT not found")


def test_character_stylized_three_quarter_reproduces_the_sample_prompt():
    assert prompts.full_prompt("a cute cat", "three_quarter") == _make_sample_prompt()


def test_object_framing_has_no_body_or_pose_words():
    for style in ("stylized", "realistic"):
        for view in ("front", "three_quarter"):
            text = prompts.full_prompt("a red retro toaster", view, True, "object", style).lower()
            assert "full body" not in text and "arms" not in text and "character" not in text
            assert "single object" in text and "grey background" in text


def test_realistic_style_changes_only_the_tail():
    stylized = prompts.full_prompt("a fox", "front", True, "character", "stylized")
    realistic = prompts.full_prompt("a fox", "front", True, "character", "realistic")
    assert "cartoon" in stylized and "cartoon" not in realistic
    assert "Realistic 3D render" in realistic


def test_framing_off_returns_the_bare_prompt():
    assert prompts.full_prompt("  a cat.  ", framing=False) == "a cat"


def test_every_subject_style_pair_has_a_tail():
    for subject in ("character", "object"):
        for style in ("stylized", "realistic"):
            assert prompts.TAILS[(subject, style)].endswith("no logo.")


def test_read_progress_takes_the_last_stage_and_flow_step(tmp_path):
    log = tmp_path / "server.log"
    log.write_text(
        "2026-10-14 10:00:00 == job 1 trellis-512 start\n"
        "2026-10-14 10:00:01 [Info] (Process) [3/6] sparse-structure flow + decode\n"
        "2026-10-14 10:00:09 [Info] (Process)       [flow] [##......]  1/8   7.7s  ~54s left\n"
        "2026-10-14 10:01:00 [Info] (Process) [4/7] shape SLAT flow (512)\n"
        "2026-10-14 10:01:05 [Info] (Process)       [flow] [#.......]  1/8   4.3s  ~30s left\n"
    )
    assert prompts.read_progress(str(log), 0) == "[4/7] shape SLAT flow (512)  1/8 4.3s ~30s"


def test_read_progress_missing_file_is_empty(tmp_path):
    assert prompts.read_progress(str(tmp_path / "nope.log"), 0) == ""
