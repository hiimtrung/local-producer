"""Prompt framing and server-log parsing for the TRELLIS.2 add-on. No bpy: unit-tested outside Blender."""

import os

# Appended to the prompt so the image suits image-to-3D: whole object, plain background, no shadow.
# The background is mid grey, not white: on white, the matting cut white parts out (a white cat belly became a hole
# that TRELLIS filled with a made-up camouflage texture, CHANGELOG 2026-10-13).
# The "three_quarter" text + FRAMING_TAIL is the prompt scripts/make_sample.py uses for the default sample image.
FRAMING = {
    "front": "Full body, standing upright, front view, symmetrical pose, arms slightly away from the body",
    "three_quarter": "Full body, standing upright, three-quarter view from the front left, body turned about "
    "45 degrees so the front and one side are both visible, arms slightly away from the body",
}
# Objects (props, machines, parts): no body/pose words; seen a little from above so TRELLIS.2 also gets the top.
FRAMING_OBJECT = {
    "front": "A single object on its own, front view from slightly above",
    "three_quarter": "A single object on its own, three-quarter view from the front left and slightly above, so the "
    "front, one side and the top are all visible",
}
# Image edit for rigging: arms (and legs) apart in the rest pose. Editing the existing image keeps the character;
# a new text-to-image A-pose prompt gave a different, slimmer character (CHANGELOG 2026-10-13).
APOSE_EDIT = (
    "Change only the pose of this character: both arms stretched down and out to the sides at about 45 "
    "degrees (A-pose), hands or paws far from the body with clear empty space between each arm and the "
    "torso, legs slightly apart. Keep exactly the same character: same body shape and proportions, same "
    "head, same limbs, same colours and markings, same view, same framing."
)
EDIT_BACKGROUND = (0.53, 0.54, 0.54)  # matted inputs are flattened onto mid grey before the edit
FRAMING_TAIL = (
    "the whole character inside the frame and centered. Stylized 3D cartoon toy figure, soft even "
    "studio lighting, plain uniform medium grey background, no shadow, no text, no logo."
)
# Tail per (subject, style); ("character", "stylized") is FRAMING_TAIL, the text the sample image was made with.
TAILS = {
    ("character", "stylized"): FRAMING_TAIL,
    ("character", "realistic"): "the whole character inside the frame and centered. Realistic 3D render, detailed "
    "physically based materials, soft even studio lighting, plain uniform medium grey "
    "background, no shadow, no text, no logo.",
    ("object", "stylized"): "the whole object inside the frame and centered with some margin, nothing else in the "
    "scene. Stylized 3D model with clean simple shapes and clear colours, soft even studio "
    "lighting, plain uniform medium grey background, no shadow, no text, no logo.",
    ("object", "realistic"): "the whole object inside the frame and centered with some margin, nothing else in the "
    "scene. Realistic 3D product render, accurate proportions, detailed physically based "
    "materials, soft even studio lighting, plain uniform medium grey background, no shadow, "
    "no text, no logo.",
}


def full_prompt(
    prompt: str, view: str = "front", framing: bool = True, subject: str = "character", style: str = "stylized"
) -> str:
    """The prompt sent to the image model: the user's text plus, optionally, the image-to-3D framing.

    subject "character" (people, animals, creatures: full body, arms away from the body for rigging) or "object"
    (props, machines, parts: one object, seen slightly from above); style "stylized" or "realistic".
    """
    prompt = prompt.strip().rstrip(".")
    if not framing:
        return prompt
    frame = (FRAMING if subject == "character" else FRAMING_OBJECT)[view]
    return f"{prompt}. {frame}, {TAILS[(subject, style)]}"


def read_progress(log_path: str, offset: int) -> str:
    """Return 'stage | flow step' from the server log written after byte `offset`, or ''."""
    try:
        with open(log_path, "rb") as f:
            size = f.seek(0, os.SEEK_END)
            f.seek(max(offset, size - 65536))
            text = f.read().decode(errors="replace")
    except OSError:
        return ""
    stage, flow = "", ""
    for ln in text.replace("\r", "\n").split("\n"):
        if " (Process) " in ln:  # forwarded backend output: "<time> [Info] (Process) <line>"
            ln = ln.split(" (Process) ", 1)[1]
        ln = ln.strip()
        if ln.startswith("[") and "/" in ln[:6]:  # "[3/7] shape SLAT flow (512)"
            stage, flow = ln, ""  # a new stage resets the flow progress
        elif ln.startswith("[flow] ["):  # "[flow] [####....]  5/12   69.9s  ~98s left"
            flow = " ".join(ln.split()[2:5])
    return f"{stage}  {flow}".strip()
