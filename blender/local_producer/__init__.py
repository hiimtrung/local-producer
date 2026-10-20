"""LocalProducer, the Blender add-on of local-producer: generate a textured (PBR) mesh from an image or a prompt via
FLUX.2 + TRELLIS.2 on the local GPU server, and import the 3D models already in the server's Library.

The server is local-producer's GPU server (scripts/run-server.sh: FLUX.2 and TRELLIS.2 on ROCm, one process per
job) on http://127.0.0.1:13305 (POST /v1/3d/generations; the request format follows AMD Lemonade's API, which the
project used before 2026-10-14).

Server setup: the "Check Server" button shows whether the shared components and a model of each kind are installed;
"Download Models" makes the server fetch what is missing (SHA256-verified, POST /v1/setup/download: the components
plus the recommended model of a kind that has none) with progress in the panel. Other models: the web UI's Models page.
Install: drag the "Drag into Blender to install" button of the web UI (Server > Blender add-on) into Blender 4.2+
(the server is an extension repository, /blender/index.json), or run blender/build_addon.sh and use
Edit > Preferences > Add-ons > (menu) Install from Disk... > the zip.
Panels: 3D Viewport > Sidebar (N) > LocalProducer: "Image to Textured Mesh" and "Library" (the server's finished 3D
models with their input image as preview; Import downloads the GLB, GET /v1/jobs/<id>/files/model.glb).
Renamed from "TRELLIS.2 Image to Textured Mesh" (id trellis_addon) in 0.14.0: remove the old add-on first.
Live progress: set "Server Log" in the add-on preferences to ~/.local-producer/server/server.log; the panel tails it
(stage and flow step).
Background removal: images without an alpha mask are cut out first by the local matting server (rembg on the
CPU, ~0.6 s); trellis.cpp's own BiRefNet gave wrong masks on the Radeon 780M (Vulkan, pixal3d.cpp fork; not checked
with the HIP build).
Prompt mode: text -> image with FLUX.2-klein-4B on the same server (POST /v1/images/generations);
the image is previewed in the panel and only turned into a mesh when "Generate Textured Mesh" is pressed.
Subject: "Character" (full body, arms away from the body) or "Object" (one prop/machine/part, seen slightly from
above; Make A-pose hidden), Style: "Stylized" or "Realistic"; they choose the framing text appended to the prompt.
A-pose: "Make A-pose" edits the current image with FLUX.2 (POST /v1/images/edits) so the arms stand away from the
body and the character can be rigged without armpit artefacts (CHANGELOG 2026-10-13); the edited image replaces
the current one and is previewed.
Headless use (e.g. over MCP): import this module and call start_image(prompt, ...), start_apose(image_path) or
start_generation(image_path, ...); the result is handled by a timer on the main thread, exactly like pressing the
button.
"""

import os
import re
import tempfile
import threading
import time
import uuid

import bmesh
import bpy
import numpy as np
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from . import client
from .client import DEFAULT_IMAGE_MODEL, DEFAULT_MODEL, matte_image, request_edit, request_glb, request_image
from .prompts import APOSE_EDIT, EDIT_BACKGROUND, FRAMING_TAIL, full_prompt, read_progress

bl_info = {
    "name": "LocalProducer",
    "author": "hiimtrung",
    "version": (0, 15, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > LocalProducer",
    "description": "Generate a PBR-textured mesh from an image or a text prompt (FLUX.2 + TRELLIS.2 on the local "
    "GPU server), and import the 3D models of the server's Library",
    "doc_url": "https://github.com/hiimtrung/local-producer#readme",
    "tracker_url": "https://github.com/hiimtrung/local-producer/issues",
    "category": "3D View",
}

DEFAULT_URL = "http://127.0.0.1:13305"
# Default input: a cute cat, 3/4 view, grey background (FLUX.2-klein-4B bf16 via Lemonade on 2026-10-13, matted;
# regenerate with scripts/make_sample.py),
# shipped inside the add-on package so every test uses the same image.
DEFAULT_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", "cat.png")
DEFAULT_MATTE_URL = "http://127.0.0.1:8083"  # local-producer/scripts/run-server.sh (rembg, CPU, same container)
PREVIEW_IMAGE = "LocalProducer Prompt Image"  # bpy image datablock shown in the panel
LIBRARY_PREVIEW = "LocalProducer Library Preview"  # the selected Library model's input image
PROMPT_DIR = os.path.join(tempfile.gettempdir(), "local_producer")  # generated prompt images
# Result handed from the worker thread to the main-thread timer. kind: "image" (FLUX) or "mesh" (TRELLIS).
_job = {
    "thread": None,
    "result": None,
    "error": None,
    "started": 0.0,
    "name": "",
    "log_offset": 0,
    "phase": "",
    "kind": "",
}


def flatten_png(image_path, background=EDIT_BACKGROUND):
    """Return the image as opaque PNG bytes, transparent parts over `background` (main thread only)."""
    img = bpy.data.images.load(image_path, check_existing=False)
    try:
        w, h, c = img.size[0], img.size[1], img.channels
        px = np.empty(w * h * c, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(-1, c)
        if c == 4:
            a = px[:, 3:4]
            px[:, :3] = px[:, :3] * a + np.array(background, np.float32) * (1 - a)
            px[:, 3] = 1.0
        img.pixels.foreach_set(px.ravel())
        out = os.path.join(tempfile.gettempdir(), f"trellis_{uuid.uuid4().hex}_flat.png")
        img.filepath_raw = out
        img.file_format = "PNG"
        img.save()
        with open(out, "rb") as f:
            data = f.read()
        os.unlink(out)
        return data
    finally:
        bpy.data.images.remove(img)


def to_png(image_path):
    """Return (png_path, has_alpha_mask) for the image (main thread only).

    The server decodes PNG only; Blender reads WebP, JPEG, TIFF, ... A non-PNG file is written to a temporary
    RGBA PNG. has_alpha_mask is False when every pixel is opaque: such an image still needs background removal.
    """
    img = bpy.data.images.load(image_path, check_existing=False)
    try:
        pixels = np.empty(img.size[0] * img.size[1] * img.channels, dtype=np.float32)  # also forces the load
        img.pixels.foreach_get(pixels)
        has_alpha_mask = img.channels == 4 and float(pixels[3::4].min()) < 0.999
        with open(image_path, "rb") as f:
            is_png = f.read(8) == b"\x89PNG\r\n\x1a\n"
        if is_png:
            return image_path, has_alpha_mask
        out = os.path.join(tempfile.gettempdir(), f"trellis_{uuid.uuid4().hex}.png")
        img.filepath_raw = out
        img.file_format = "PNG"
        img.save()
        return out, has_alpha_mask
    finally:
        bpy.data.images.remove(img)


def import_glb(glb_bytes, name):
    """Import GLB bytes into the current scene; return the new objects (main thread only)."""
    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as f:
        f.write(glb_bytes)
        path = f.name
    try:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=path)
    finally:
        os.unlink(path)
    new_objects = [o for o in bpy.data.objects if o not in before]
    for obj in new_objects:
        if obj.type == "MESH":
            obj.name = name
            obj.data.name = name
    return new_objects


def remove_ground_slab(obj, min_span=0.95, max_thickness=0.02, edge=0.45):
    """Delete the flat "floor" the model sometimes emits across the whole generation box.

    TRELLIS meshes live in a unit box (-0.5..0.5). A connected piece covering >= min_span of both horizontal
    axes while thinner than max_thickness is never part of the object; UV seams split its rim into further thin
    pieces, so flat pieces in the same height band that reach the box edge (|x| or |y| > edge) go too.
    Returns the number of removed vertices.
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    seen, pieces = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, piece = [v], []
        seen.add(v.index)
        while stack:
            x = stack.pop()
            piece.append(x)
            for e in x.link_edges:
                y = e.other_vert(x)
                if y.index not in seen:
                    seen.add(y.index)
                    stack.append(y)
        lo = [min(p.co[k] for p in piece) for k in range(3)]
        hi = [max(p.co[k] for p in piece) for k in range(3)]
        pieces.append((piece, lo, hi))
    slabs = [
        (lo[2], hi[2])
        for _, lo, hi in pieces
        if hi[0] - lo[0] >= min_span and hi[1] - lo[1] >= min_span and hi[2] - lo[2] < max_thickness
    ]
    remove = []
    if slabs:
        z_lo = min(z for z, _ in slabs) - max_thickness
        z_hi = max(z for _, z in slabs) + max_thickness
        for piece, lo, hi in pieces:
            flat_in_band = lo[2] >= z_lo and hi[2] <= z_hi
            at_edge = max(abs(lo[0]), abs(hi[0]), abs(lo[1]), abs(hi[1])) > edge
            if flat_in_band and at_edge:
                remove.extend(piece)
    if remove:
        bmesh.ops.delete(bm, geom=remove, context="VERTS")
        bm.to_mesh(obj.data)
        obj.data.update()
    bm.free()
    return len(remove)


def _show(objects, textured):
    """Select the new objects, frame them in every 3D view and optionally switch to Material Preview."""
    meshes = [o for o in objects if o.type == "MESH"]
    if not meshes:
        return
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            if textured:
                area.spaces.active.shading.type = "MATERIAL"
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region:
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.view3d.view_selected()


def _redraw_sidebars():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _apply_speed(props):
    if props.speed == "quality":
        props.image_steps, props.mesh_steps, props.resolution = 4, 8, "512"
    elif props.speed == "fast":
        props.image_steps, props.mesh_steps, props.resolution = 3, 6, "512"
    elif props.speed == "hard_surface":
        props.image_steps, props.mesh_steps, props.resolution = 4, 8, "1024"


def _prefs():
    return bpy.context.preferences.addons[__package__].preferences


def _poll_job():
    props = bpy.context.scene.local_producer
    log_path = bpy.path.abspath(_prefs().log_path) if _prefs().log_path else ""
    elapsed = time.time() - _job["started"]
    if _job["thread"].is_alive():
        progress = read_progress(log_path, _job["log_offset"]) if log_path else ""
        if _job["phase"] == "matte":
            progress = "Removing background (local matting server)..."
        elif _job["kind"] == "image":
            progress = "FLUX.2 text-to-image (no step progress)"
        elif _job["kind"] == "apose":
            progress = "FLUX.2 image edit to an A-pose (no step progress, ~4 min)"
        elif _job["kind"] == "import":
            progress = "Downloading the model from the server's Library"
        props.status = f"Generating {_job['kind']}... {elapsed:.0f} s"
        props.progress = progress
        _redraw_sidebars()
        return 1.0
    if _job["error"]:
        props.status = f"Failed after {elapsed:.0f} s: {_job['error']}"
    elif _job["kind"] in ("image", "apose"):
        props.prompt_image = _job["result"]
        if props.source == "image":
            props.image_path = _job["result"]  # the edited image replaces the input
        _load_preview(_job["result"])
        what = "A-pose image" if _job["kind"] == "apose" else "Image"
        props.status = f"{what} ready in {elapsed:.0f} s; check it, then Generate Textured Mesh"
    else:
        objects = import_glb(_job["result"], _job["name"])
        removed = sum(remove_ground_slab(o) for o in objects if o.type == "MESH") if props.remove_slab else 0
        _show(objects, props.material_preview)
        faces = sum(len(o.data.polygons) for o in objects if o.type == "MESH")
        what = "Imported" if _job["kind"] == "import" else "Done"
        props.status = f"{what} in {elapsed:.0f} s, {faces:,} faces" + (" (floor slab removed)" if removed else "")
    props.progress = ""
    props.busy = False
    _job["thread"] = None
    _redraw_sidebars()
    return None


def _load_preview(path):
    """Show the image file in the panel's preview (main thread only); returns the bpy image."""
    img = bpy.data.images.get(PREVIEW_IMAGE)
    if img is None:
        img = bpy.data.images.load(path, check_existing=False)
        img.name = PREVIEW_IMAGE
    else:
        img.filepath = path
        img.reload()
    img.preview_ensure()
    img.preview.reload()
    return img


def _slug(text, words=4):
    return "_".join(re.findall(r"[a-z0-9]+", text.lower())[:words]) or "prompt"


def start_image(prompt, seed=None, view=None, api_url=None, subject=None, style=None):
    """Start a FLUX.2 text-to-image job in the background (main thread); returns an error string or ''.

    The PNG goes to PROMPT_DIR, its path to scene.local_producer.prompt_image, and it is shown in the panel preview.
    """
    props = bpy.context.scene.local_producer
    if _job["thread"] is not None:
        return "a job is already running"
    if not prompt.strip():
        return "the prompt is empty"
    props.prompt = prompt
    if seed is not None:
        props.image_seed = seed
    if view is not None:
        props.view = view
    if subject is not None:
        props.subject = subject
    if style is not None:
        props.style = style
    if api_url:
        props.api_url = api_url
    text = full_prompt(prompt, props.view, props.framing, props.subject, props.style)
    name = f"{_slug(prompt)}_{props.subject}_{props.view}_s{props.image_seed}_{uuid.uuid4().hex[:6]}.png"
    out = os.path.join(PROMPT_DIR, name)
    url, model, seed_, steps = props.api_url, props.image_model, props.image_seed, props.image_steps
    _sync_auth()

    def work():
        try:
            png = request_image(url, text, model, seed_, steps)
            os.makedirs(PROMPT_DIR, exist_ok=True)
            with open(out, "wb") as f:
                f.write(png)
            _job["result"] = out
        except Exception as e:  # reported in the panel by _poll_job
            _job["error"] = str(e)

    _job.update(result=None, error=None, started=time.time(), phase="", kind="image", name="", log_offset=0)
    _job["thread"] = threading.Thread(target=work, daemon=True)
    _job["thread"].start()
    props.busy = True
    props.status = "Generating image..."
    bpy.app.timers.register(_poll_job, first_interval=1.0)
    return ""


def start_apose(image_path=None, seed=None, api_url=None):
    """Start a FLUX.2 edit of the current image into an A-pose (main thread); returns an error string or ''.

    image_path defaults to the image the panel would turn into a mesh. The result is written to PROMPT_DIR,
    previewed, and becomes the current image (image_path in Image mode, prompt_image in Prompt mode).
    """
    props = bpy.context.scene.local_producer
    if _job["thread"] is not None:
        return "a job is already running"
    if props.subject == "object":
        return "Make A-pose is for characters (Subject: Character)"
    if image_path is None:
        image_path = props.image_path if props.source == "image" else props.prompt_image
    image_path = bpy.path.abspath(image_path)
    if not os.path.isfile(image_path):
        return f"image not found: {image_path}"
    if seed is not None:
        props.image_seed = seed
    if api_url:
        props.api_url = api_url
    try:
        png = flatten_png(image_path)
    except Exception as e:
        return f"cannot read image {image_path}: {e}"
    stem = os.path.splitext(os.path.basename(image_path))[0]
    out = os.path.join(PROMPT_DIR, f"{stem}_apose_s{props.image_seed}_{uuid.uuid4().hex[:6]}.png")
    url, model, seed_, steps = props.api_url, props.image_model, props.image_seed, props.image_steps
    _sync_auth()
    prompt = f"{APOSE_EDIT} {FRAMING_TAIL[0].upper()}{FRAMING_TAIL[1:]}"

    def work():
        try:
            result = request_edit(url, png, prompt, model, seed_, steps)
            os.makedirs(PROMPT_DIR, exist_ok=True)
            with open(out, "wb") as f:
                f.write(result)
            _job["result"] = out
        except Exception as e:  # reported in the panel by _poll_job
            _job["error"] = str(e)

    _job.update(result=None, error=None, started=time.time(), phase="", kind="apose", name="", log_offset=0)
    _job["thread"] = threading.Thread(target=work, daemon=True)
    _job["thread"].start()
    props.busy = True
    props.status = "Editing the image into an A-pose..."
    bpy.app.timers.register(_poll_job, first_interval=1.0)
    return ""


def start_generation(image_path, seed=None, resolution=None, api_url=None):
    """Start a generation in the background (main thread); returns an error string or ''."""
    props = bpy.context.scene.local_producer
    if _job["thread"] is not None:
        return "a job is already running"
    image_path = bpy.path.abspath(image_path)
    if not os.path.isfile(image_path):
        return f"image not found: {image_path}"
    props.image_path = image_path
    if seed is not None:
        props.seed = seed
    if resolution is not None:
        props.resolution = str(resolution)
    if api_url:
        props.api_url = api_url
    try:
        png_path, has_alpha_mask = to_png(image_path)
    except Exception as e:
        return f"cannot read image {image_path}: {e}"
    mode = props.bg_removal
    use_matte = mode == "matte" and not has_alpha_mask
    if mode == "matte":
        bg_removal = "auto"  # the server keeps a real alpha mask (ours or the image's own)
    elif mode == "server" and not has_alpha_mask:
        bg_removal = "birefnet"  # an opaque PNG would otherwise be taken as already matted
    else:
        bg_removal = "auto" if mode == "server" else mode
    params = dict(
        model=props.model,
        seed=props.seed,
        resolution=int(props.resolution),
        bg_removal=bg_removal,
        steps=props.mesh_steps,
    )
    url, matte_url, matte_model = props.api_url, props.matte_url, props.matte_model
    _sync_auth()

    def work():
        temp_files = [png_path] if png_path != image_path else []
        try:
            send_path = png_path
            if use_matte:
                _job["phase"] = "matte"
                cut = matte_image(matte_url, image_path, matte_model)
                send_path = os.path.join(tempfile.gettempdir(), f"trellis_{uuid.uuid4().hex}_cut.png")
                with open(send_path, "wb") as f:
                    f.write(cut)
                temp_files.append(send_path)
            _job["phase"] = "generate"
            _job["result"] = request_glb(url, send_path, **params)
        except Exception as e:  # reported in the panel by _poll_job
            _job["error"] = str(e)
        finally:
            for path in temp_files:
                os.unlink(path)

    log = bpy.path.abspath(_prefs().log_path) if _prefs().log_path else ""
    _job.update(
        result=None,
        error=None,
        started=time.time(),
        phase="",
        kind="mesh",
        name=os.path.splitext(os.path.basename(image_path))[0],
        log_offset=os.path.getsize(log) if log and os.path.isfile(log) else 0,
    )
    _job["thread"] = threading.Thread(target=work, daemon=True)
    _job["thread"].start()
    props.busy = True
    props.status = "Generating..."
    bpy.app.timers.register(_poll_job, first_interval=1.0)
    return ""


def refresh_library():
    """Read the server's finished 3D models into the Library list (main thread); returns an error string or ''."""
    props = bpy.context.scene.local_producer
    _sync_auth()
    try:
        models = client.library_models(props.api_url)
    except RuntimeError as e:
        props.library_info = str(e)[:160]
        return str(e)
    props.library.clear()
    for m in models:
        item = props.library.add()
        item.job_id, item.created, item.faces = m["id"], m["created"], m["faces"]
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(m["created"]))
        item.label = m["prompt"] or f"3D model {m['id'][:8]}"
        item.detail = f"{when} · res {m['resolution']} · {m['faces']:,} faces"
    props.library_info = f"{len(models)} 3D model(s) on the server" if models else "No 3D models on the server yet"
    props.library_index = 0 if models else -1
    _redraw_sidebars()
    return ""


def _show_library_preview(props):
    """Download the selected model's input image and show it (main thread; the server is local, ~1 MB)."""
    if not 0 <= props.library_index < len(props.library):
        return
    item = props.library[props.library_index]
    path = os.path.join(PROMPT_DIR, "library", f"{item.job_id}.png")
    try:
        if not os.path.isfile(path):
            data = client.job_file(props.api_url, item.job_id, "input.png", timeout=10)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        img = bpy.data.images.get(LIBRARY_PREVIEW)
        if img is None:
            img = bpy.data.images.load(path, check_existing=False)
            img.name = LIBRARY_PREVIEW
        else:
            img.filepath = path
            img.reload()
        img.preview_ensure()
        img.preview.reload()
    except (RuntimeError, OSError):
        pass  # no preview: the import still works


def start_library_import(job_id=None, api_url=None):
    """Download a Library model's GLB and import it like a generated one (main thread); returns an error or ''."""
    props = bpy.context.scene.local_producer
    if _job["thread"] is not None:
        return "a job is already running"
    if api_url:
        props.api_url = api_url
    if job_id is None:
        if not 0 <= props.library_index < len(props.library):
            return "select a model in the Library list"
        item = props.library[props.library_index]
        job_id, name = item.job_id, _slug(item.label)
    else:
        name = f"model_{job_id[:8]}"
    url = props.api_url
    _sync_auth()

    def work():
        try:
            _job["result"] = client.job_file(url, job_id, "model.glb")
        except Exception as e:  # reported in the panel by _poll_job
            _job["error"] = str(e)

    _job.update(result=None, error=None, started=time.time(), phase="", kind="import", name=name, log_offset=0)
    _job["thread"] = threading.Thread(target=work, daemon=True)
    _job["thread"].start()
    props.busy = True
    props.status = "Importing from the Library..."
    bpy.app.timers.register(_poll_job, first_interval=0.5)
    return ""


class LocalProducerLibraryItem(bpy.types.PropertyGroup):
    job_id: StringProperty()
    label: StringProperty()
    detail: StringProperty()
    created: FloatProperty()
    faces: IntProperty()


class LocalProducerPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    log_path: StringProperty(
        name="Server Log",
        subtype="FILE_PATH",
        default="",
        description="Log of the GPU server (~/.local-producer/server/server.log); read for live progress. Optional",
    )

    server_token: StringProperty(
        name="Server Token",
        subtype="PASSWORD",
        default="",
        description="Only if the server was started with SERVER_TOKEN; sent as a Bearer token",
    )

    def draw(self, context):
        self.layout.prop(self, "log_path")
        self.layout.prop(self, "server_token")


class LocalProducerProps(bpy.types.PropertyGroup):
    api_url: StringProperty(name="Server", default=DEFAULT_URL)
    source: EnumProperty(
        name="Source",
        items=[
            ("image", "Image", "Start from an image file"),
            (
                "prompt",
                "Prompt",
                "Generate the image from text with FLUX.2-klein-4B first, preview it, then turn it into a mesh",
            ),
        ],
        default="image",
    )
    prompt: StringProperty(name="Prompt", default="", description="What to make, e.g. 'a cute cat'")
    subject: EnumProperty(
        name="Subject",
        items=[
            (
                "character",
                "Character",
                "People, animals, creatures: full body, upright, arms away from the body "
                "(ready for Make A-pose and rigging)",
            ),
            (
                "object",
                "Object",
                "Props, machines, parts, buildings: one object on its own, seen slightly from "
                "above so the top is visible too; no pose words, no A-pose",
            ),
        ],
        default="character",
    )
    style: EnumProperty(
        name="Style",
        items=[
            ("stylized", "Stylized", "Stylized 3D (cartoon toy figure / clean simple shapes)"),
            ("realistic", "Realistic", "Realistic 3D render with detailed physically based materials"),
        ],
        default="stylized",
    )
    view: EnumProperty(
        name="View",
        items=[
            ("front", "Front", "Front view (characters: symmetrical pose)"),
            (
                "three_quarter",
                "3/4",
                "Three-quarter view: shows the front and one side, so less of the object has to be guessed",
            ),
        ],
        default="front",
    )
    framing: BoolProperty(
        name="Image-to-3D framing",
        default=True,
        description="Append the image-to-3D framing for the chosen Subject, Style and View: "
        "whole subject centered, plain grey background, no shadow (FRAMING, "
        "FRAMING_OBJECT and TAILS in prompts.py)",
    )
    image_seed: IntProperty(name="Image Seed", default=7, min=0)
    speed: EnumProperty(
        name="Speed",
        items=[
            ("quality", "Quality", "FLUX.2 4 steps, TRELLIS.2 8 steps (default)"),
            (
                "fast",
                "Fast",
                "FLUX.2 3 steps (~10 s faster per image), TRELLIS.2 6 steps (~14 % faster mesh); "
                "small changes in pose and detail (CHANGELOG 2026-10-14)",
            ),
            (
                "hard_surface",
                "Hard Surface",
                "Quality steps at resolution 1024 for vehicles and machines: thin panel lines and crisp edges, "
                "~2.75x the mesh time (605 s vs 220 s for a fighter jet; CHANGELOG 2026-10-16)",
            ),
            ("custom", "Custom", "Set Image Steps, Mesh Steps and Resolution by hand"),
        ],
        default="quality",
        update=lambda self, ctx: _apply_speed(self),
    )
    image_steps: IntProperty(
        name="Image Steps",
        default=4,
        min=1,
        max=8,
        description="FLUX.2-klein denoising steps for text-to-image and Make A-pose (4 = default)",
    )
    mesh_steps: IntProperty(
        name="Mesh Steps", default=8, min=2, max=16, description="TRELLIS.2 flow steps per stage (8 = default)"
    )
    image_model: StringProperty(name="Image Model", default=DEFAULT_IMAGE_MODEL)
    prompt_image: StringProperty(
        name="Prompt Image",
        subtype="FILE_PATH",
        default="",
        description="The last image generated from the prompt; used for the mesh",
    )
    model: StringProperty(name="Model", default=DEFAULT_MODEL)
    image_path: StringProperty(
        name="Image",
        subtype="FILE_PATH",
        default=DEFAULT_IMAGE,
        description="PNG, WebP, JPEG, ...; a transparent background (alpha) is used as the "
        "object mask, "
        "otherwise the background is removed first (see Background)",
    )
    seed: IntProperty(name="Seed", default=1234, min=0)
    resolution: EnumProperty(
        name="Resolution",
        items=[
            ("512", "512 (fast)", "Lowest resolution TRELLIS.2 supports (its structure grid and decoders are fixed)"),
            ("1024", "1024 (slow)", "Sharper; ~19 min for the cat sample on the ROCm server"),
            ("1536", "1536 (very slow)", "~53 min for the cat sample; from the front about as sharp as 1024"),
        ],
        default="512",
    )
    bg_removal: EnumProperty(
        name="Background",
        items=[
            (
                "matte",
                "Local matting",
                "Keep the image's alpha mask if it has one, else cut it out with the "
                "local matting server (rembg on the CPU, ~0.6 s)",
            ),
            (
                "server",
                "Server BiRefNet",
                "trellis.cpp's BiRefNet (gave wrong masks on the Radeon 780M in the "
                "Vulkan pixal3d.cpp fork; not checked with the HIP build)",
            ),
            ("threshold", "Threshold", "Server-side simple keyer for plain white backgrounds"),
        ],
        default="matte",
    )
    matte_model: EnumProperty(
        name="Matting Model",
        items=[
            ("isnet-general-use", "ISNet (0.6 s)", "Default; keeps fine details such as whiskers"),
            ("u2net", "U2Net (0.2 s)", "Fastest, loses thin details"),
            ("birefnet-general-lite", "BiRefNet lite (6 s)", "Slower"),
            ("birefnet-general", "BiRefNet (10 s)", "Slowest"),
        ],
        default="isnet-general-use",
    )
    matte_url: StringProperty(name="Matting Server", default=DEFAULT_MATTE_URL)
    remove_slab: BoolProperty(
        name="Remove floor slab",
        default=True,
        description="Delete flat pieces spanning the whole generation box (a model artifact)",
    )
    show_advanced: BoolProperty(name="Advanced", default=False)
    material_preview: BoolProperty(
        name="Switch to Material Preview", default=True, description="Show the imported textures in the 3D viewport"
    )
    busy: BoolProperty(default=False)
    status: StringProperty(default="")
    progress: StringProperty(default="")
    server_info: StringProperty(default="")  # model setup state, filled by Check / Download Models
    library: CollectionProperty(type=LocalProducerLibraryItem)
    library_index: IntProperty(default=-1, update=lambda self, ctx: _show_library_preview(self))
    library_info: StringProperty(default="")
    models_ready: BoolProperty(default=False)
    setup_running: BoolProperty(default=False)


class LP_OT_generate(bpy.types.Operator):
    bl_idname = "local_producer.generate"
    bl_label = "Generate Textured Mesh"
    bl_description = "Send the image to the TRELLIS.2 server and import the resulting textured mesh"

    @classmethod
    def poll(cls, context):
        props = context.scene.local_producer
        return props.source == "image" or os.path.isfile(props.prompt_image)

    def execute(self, context):
        props = context.scene.local_producer
        error = start_generation(props.image_path if props.source == "image" else props.prompt_image)
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}
        return {"FINISHED"}


class LP_OT_generate_image(bpy.types.Operator):
    bl_idname = "local_producer.generate_image"
    bl_label = "Generate Image"
    bl_description = "Generate an image from the prompt with FLUX.2-klein-4B and show it for review"

    def execute(self, context):
        error = start_image(context.scene.local_producer.prompt)
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}
        return {"FINISHED"}


class LP_OT_apose(bpy.types.Operator):
    bl_idname = "local_producer.apose"
    bl_label = "Make A-pose"
    bl_description = (
        "Edit the current image with FLUX.2 so the arms stand away from the body (for rigging); "
        "keeps the character. The edited image replaces the current one (~4 min)"
    )

    @classmethod
    def poll(cls, context):
        props = context.scene.local_producer
        path = props.image_path if props.source == "image" else props.prompt_image
        return not props.busy and props.subject == "character" and os.path.isfile(bpy.path.abspath(path))

    def execute(self, context):
        error = start_apose()
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}
        return {"FINISHED"}


class LP_PT_panel(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LocalProducer"
    bl_label = "Image to Textured Mesh"

    def draw(self, context):
        props = context.scene.local_producer
        layout = self.layout
        box = layout.box()
        box.prop(props, "api_url")
        row = box.row(align=True)
        row.operator(LP_OT_check_server.bl_idname, icon="FILE_REFRESH")
        if not props.models_ready:
            row.operator(LP_OT_download_models.bl_idname, icon="IMPORT")
        if props.server_info:
            box.label(text=props.server_info)
        layout.row().prop(props, "source", expand=True)
        if props.source == "image":
            layout.prop(props, "image_path")
            img = bpy.data.images.get(PREVIEW_IMAGE)
            if img and img.preview and bpy.path.abspath(props.image_path) == props.prompt_image:
                layout.template_icon(icon_value=img.preview.icon_id, scale=10)
        else:
            layout.prop(props, "prompt", text="")
            layout.row(align=True).prop(props, "subject", expand=True)
            layout.row(align=True).prop(props, "style", expand=True)
            row = layout.row(align=True)
            row.prop(props, "view", expand=True)
            col = layout.column(align=True)
            col.prop(props, "image_seed")
            col.prop(props, "framing")
            row = layout.row()
            row.enabled = not props.busy
            row.operator(LP_OT_generate_image.bl_idname, icon="IMAGE_DATA")
            img = bpy.data.images.get(PREVIEW_IMAGE)
            if img and props.prompt_image and img.preview:
                layout.template_icon(icon_value=img.preview.icon_id, scale=10)
                layout.label(text=os.path.basename(props.prompt_image))
        if props.source == "image":
            layout.row(align=True).prop(props, "subject", expand=True)  # only gates Make A-pose in Image mode
        if props.subject == "character":
            layout.operator(LP_OT_apose.bl_idname, icon="ARMATURE_DATA")
        layout.row().prop(props, "speed", expand=True)
        if props.speed == "custom":
            col = layout.column(align=True)
            col.prop(props, "image_steps")
            col.prop(props, "mesh_steps")
        col = layout.column(align=True)
        col.prop(props, "resolution")
        col.prop(props, "bg_removal")
        if props.bg_removal == "matte":
            col.prop(props, "matte_model")
        col.prop(props, "seed")
        layout.prop(props, "material_preview")
        layout.prop(props, "remove_slab")
        layout.prop(props, "show_advanced", icon="TRIA_DOWN" if props.show_advanced else "TRIA_RIGHT", emboss=False)
        if props.show_advanced:
            layout.prop(props, "model")
            layout.prop(props, "image_model")
            layout.prop(props, "matte_url")
        row = layout.row()
        row.enabled = not props.busy
        row.operator(LP_OT_generate.bl_idname, icon="TEXTURE")
        if props.status:
            layout.label(text=props.status)
        if props.progress:
            layout.label(text=props.progress)


class LP_UL_library(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        col = layout.column(align=True)
        col.label(text=item.label, icon="MESH_DATA")
        col.label(text=item.detail)


class LP_OT_library_refresh(bpy.types.Operator):
    bl_idname = "local_producer.library_refresh"
    bl_label = "Refresh"
    bl_description = "List the finished 3D models in the server's Library"

    def execute(self, context):
        error = refresh_library()
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}
        return {"FINISHED"}


class LP_OT_library_import(bpy.types.Operator):
    bl_idname = "local_producer.library_import"
    bl_label = "Import"
    bl_description = "Download the selected 3D model (GLB with its textures) from the server and import it"

    @classmethod
    def poll(cls, context):
        props = context.scene.local_producer
        return not props.busy and 0 <= props.library_index < len(props.library)

    def execute(self, context):
        error = start_library_import()
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}
        return {"FINISHED"}


class LP_PT_library(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LocalProducer"
    bl_label = "Library"

    def draw(self, context):
        props = context.scene.local_producer
        layout = self.layout
        layout.operator(LP_OT_library_refresh.bl_idname, icon="FILE_REFRESH")
        if props.library_info:
            layout.label(text=props.library_info)
        if not props.library:
            return
        layout.template_list("LP_UL_library", "", props, "library", props, "library_index", rows=5)
        img = bpy.data.images.get(LIBRARY_PREVIEW)
        if img and img.preview:
            layout.template_icon(icon_value=img.preview.icon_id, scale=8)
        row = layout.row()
        row.enabled = not props.busy
        row.operator(LP_OT_library_import.bl_idname, icon="IMPORT")
        if props.status and _job["kind"] == "import":
            layout.label(text=props.status)


def _sync_auth():
    client.auth["token"] = _prefs().server_token


def _describe_setup(s):
    d = s.get("download", {})
    if d.get("running"):
        size = max(d.get("item_size", 0), 1)
        return (
            f"Downloading {d.get('done_items', 0) + 1}/{d.get('total_items', 0)}: {d.get('item', '')} "
            f"{100 * d.get('item_done', 0) / size:.0f} %"
        )
    if d.get("error"):
        return f"Download failed: {d['error'][:120]}"
    if s.get("ready"):
        return "Models ready"
    missing = sum(1 for i in s.get("items", []) if i["state"] != "ok") + len(s.get("to_add", []))
    return f"{missing} component(s) or model(s) missing, {s.get('missing_bytes', 0) / 2**30:.1f} GB to download"


def refresh_setup():
    """Read the server's model setup state into the panel (main thread); returns an error string or ''."""
    props = bpy.context.scene.local_producer
    _sync_auth()
    try:
        s = client.setup_status(props.api_url)
    except RuntimeError as e:
        props.server_info, props.models_ready, props.setup_running = str(e)[:160], False, False
        return str(e)
    props.server_info = _describe_setup(s)
    props.models_ready = bool(s.get("ready"))
    props.setup_running = bool(s.get("download", {}).get("running"))
    _redraw_sidebars()
    return ""


def _poll_setup():
    refresh_setup()
    return 2.0 if bpy.context.scene.local_producer.setup_running else None


def start_model_download():
    """Ask the server to fetch the pinned models (main thread); returns an error string or ''."""
    props = bpy.context.scene.local_producer
    _sync_auth()
    try:
        client.start_setup_download(props.api_url)
    except RuntimeError as e:
        props.server_info = str(e)[:160]
        return str(e)
    props.setup_running = True
    props.server_info = "Download started..."
    bpy.app.timers.register(_poll_setup, first_interval=1.0)
    return ""


class LP_OT_check_server(bpy.types.Operator):
    bl_idname = "local_producer.check_server"
    bl_label = "Check Server"
    bl_description = "Ask the server whether the shared components and a model of each kind are installed"

    def execute(self, context):
        error = refresh_setup()
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}
        return {"FINISHED"}


class LP_OT_download_models(bpy.types.Operator):
    bl_idname = "local_producer.download_models"
    bl_label = "Download Models"
    bl_description = (
        "The server downloads the shared components and, for a kind with no model yet, the recommended one "
        "(~18 GB on disk, ~22 GB of downloads incl. the text encoder original converted to q8_0) and verifies "
        "every file's SHA256"
    )

    @classmethod
    def poll(cls, context):
        props = context.scene.local_producer
        return not props.setup_running and not props.busy

    def execute(self, context):
        error = start_model_download()
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}
        return {"FINISHED"}


classes = (
    LocalProducerLibraryItem,
    LocalProducerPreferences,
    LocalProducerProps,
    LP_OT_generate,
    LP_OT_generate_image,
    LP_OT_apose,
    LP_OT_check_server,
    LP_OT_download_models,
    LP_PT_panel,
    LP_UL_library,
    LP_OT_library_refresh,
    LP_OT_library_import,
    LP_PT_library,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.local_producer = PointerProperty(type=LocalProducerProps)


def unregister():
    del bpy.types.Scene.local_producer
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
