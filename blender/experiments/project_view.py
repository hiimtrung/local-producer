"""Experiment: sharpen a TRELLIS.2 texture by projecting the input image onto the mesh (CHANGELOG 2026-10-16).

TRELLIS.2 sometimes keeps the input view (a jet: seen as in the image from -Y at some elevation) and sometimes turns
the object to an axis (cars, motorcycles). This script fits the camera (azimuth over the full circle, elevation, field
of view, then a 2D scale + offset) to the input silhouette, bakes the
object-space position and normal of every texel, and gives every texel the camera sees (facing + ray-cast occlusion
test) the image colour. For left-right symmetric objects (cars, motorcycles) it also finds the vertical symmetry
plane and fills hidden texels from their mirror image when that is seen. What is left keeps the TRELLIS colour,
mapped towards the image's colours (per-channel mean/std learned on the seen texels).

usage: blender -b --python blender/experiments/project_view.py -- IN.glb INPUT.png OUT.glb [--no-mirror]
       (INPUT.png = the matted RGBA input of the mesh job; writes OUT.glb and OUT.json with the numbers)
"""

import json
import math
import sys
import time

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1 :]
GLB_IN, IMAGE, GLB_OUT = argv[0], argv[1], argv[2]
MIRROR = "--no-mirror" not in argv
T0 = time.time()
report: dict[str, object] = {}


def lap(name: str) -> None:
    report[f"t_{name}"] = round(time.time() - T0, 1)


# ------------------------------------------------------------------ load
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB_IN)
obj = next(o for o in bpy.context.scene.objects if o.type == "MESH")
mesh = obj.data
M = obj.matrix_world
verts = np.array([tuple(M @ v.co) for v in mesh.vertices], np.float64)
mat = obj.material_slots[0].material
nt = mat.node_tree
base_node = next(
    n for n in nt.nodes if n.bl_idname == "ShaderNodeTexImage" and n.image.colorspace_settings.name == "sRGB"
)
base = base_node.image
W, H = base.size
trellis_rgba = np.array(base.pixels[:], np.float32).reshape(H, W, 4)  # Blender keeps sRGB bytes as 0..1 here

img = bpy.data.images.load(IMAGE)
IW, IH = img.size
inp = np.array(img.pixels[:], np.float32).reshape(IH, IW, 4)[::-1]  # top row first
alpha = inp[..., 3] > 0.5
report.update(atlas=W, faces=len(mesh.polygons), input=[IW, IH])
lap("load")


# ------------------------------------------------------------------ camera fit (silhouette IoU)
def look_at(az: float, el: float, dist: float, centre: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a, e = math.radians(az), math.radians(el)
    eye = centre + dist * np.array([math.cos(e) * math.sin(a), -math.cos(e) * math.cos(a), math.sin(e)])
    fwd = centre - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    return eye, np.stack([right, up, fwd])  # rows: camera x, y, z (z forward)


def project(p: np.ndarray, eye: np.ndarray, R: np.ndarray, f: float) -> tuple[np.ndarray, np.ndarray]:
    c = (p - eye) @ R.T
    return np.stack([f * c[:, 0] / c[:, 2], -f * c[:, 1] / c[:, 2]], 1), c[:, 2]  # image-style y down


def bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def splat(uv: np.ndarray, n: int) -> np.ndarray:
    m = np.zeros((n, n), bool)
    ij = np.clip(uv.astype(int), 0, n - 1)
    m[ij[:, 1], ij[:, 0]] = True
    for _ in range(2):  # close the gaps between projected vertices
        m = m | np.roll(m, 1, 0) | np.roll(m, -1, 0) | np.roll(m, 1, 1) | np.roll(m, -1, 1)
    for _ in range(1):
        m = m & np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1)
    return m


x0, y0, x1, y1 = bbox(alpha)
N = 192
pad = 0.1
side = max(x1 - x0, y1 - y0) * (1 + 2 * pad)
cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
ys, xs = np.mgrid[0:N, 0:N]
tgt = alpha[
    np.clip((cy - side / 2 + (ys + 0.5) * side / N).astype(int), 0, IH - 1),
    np.clip((cx - side / 2 + (xs + 0.5) * side / N).astype(int), 0, IW - 1),
]
centre = (verts.min(0) + verts.max(0)) / 2
sample = verts[np.random.default_rng(0).choice(len(verts), min(len(verts), 120_000), replace=False)]


def fit_2d(uv: np.ndarray) -> tuple[float, np.ndarray]:
    """Scale + offset that map projected coords onto the input bbox (both normalised to the N grid)."""
    lo, hi = uv.min(0), uv.max(0)
    s = max((x1 - x0) / (hi[0] - lo[0]), (y1 - y0) / (hi[1] - lo[1])) * N / side
    off = np.array([(x0 + x1) / 2 - cx + side / 2, (y0 + y1) / 2 - cy + side / 2]) * N / side - s * (lo + hi) / 2
    return s, off


def score(az: float, el: float, fov: float) -> tuple[float, dict]:
    f = 1 / math.tan(math.radians(fov) / 2)
    eye, R = look_at(az, el, 1.6 * f, centre)
    uv, _ = project(sample, eye, R, f)
    s, off = fit_2d(uv)
    m = splat(uv * s + off, N)
    iou = float((m & tgt).sum() / (m | tgt).sum())
    return iou, {"az": az, "el": el, "fov": fov, "f": f, "dist": 1.6 * f, "s": s, "off": off}


coarse = []
for az in np.arange(-180, 180, 10):  # TRELLIS keeps the view for some inputs, turns others (cars) to an axis
    for el in np.arange(0, 60.1, 5):
        for fov in (15, 30, 45):
            coarse.append(score(az, el, fov))
coarse.sort(key=lambda t: -t[0])
# A symmetric box-like object looks almost the same from front-left and rear-right, so keep the best few distinct
# azimuths; the colour check after the bake picks between them.
seeds: list[dict] = []
for iou, p in coarse:
    if len(seeds) == 4 or iou < coarse[0][0] - 0.08:
        break
    if all(abs((p["az"] - q["az"] + 180) % 360 - 180) > 30 for q in seeds):
        seeds.append(p)
candidates = []
for p0 in seeds:
    best = (0.0, {})
    for az in np.arange(p0["az"] - 4, p0["az"] + 4.1, 1):
        for el in np.arange(p0["el"] - 4, p0["el"] + 4.1, 1):
            for fov in np.arange(max(5, p0["fov"] - 10), p0["fov"] + 10.1, 5):
                best = max(best, score(az, el, fov), key=lambda t: t[0])
    candidates.append(best)
lap("camera")
eye, R, cam = np.zeros(3), np.eye(3), candidates[0][1]


def use_camera(c: dict) -> None:
    global eye, R, cam
    cam = c
    eye, R = look_at(c["az"], c["el"], c["dist"], centre)


def to_pixels(p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Object-space points -> input image pixel coords (x, y) and camera depth."""
    uv, depth = project(p, eye, R, cam["f"])
    g = uv * cam["s"] + cam["off"]  # N grid
    return np.stack([cx - side / 2 + g[:, 0] * side / N, cy - side / 2 + g[:, 1] * side / N], 1), depth


# ------------------------------------------------------------------ bake position + normal per texel (Cycles CPU)
def new_float(name: str) -> bpy.types.Image:
    im = bpy.data.images.new(name, W, H, alpha=True, float_buffer=True)
    im.colorspace_settings.name = "Non-Color"
    im.pixels.foreach_set(np.zeros(W * H * 4, np.float32))
    return im


sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 1
sc.render.bake.margin = 4
outn = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
surf = outn.inputs["Surface"].links[0].from_socket
tgt_node = nt.nodes.new("ShaderNodeTexImage")
tc = nt.nodes.new("ShaderNodeTexCoord")
em = nt.nodes.new("ShaderNodeEmission")
bpy.context.view_layer.objects.active = obj
obj.select_set(True)


def bake(kind: str, image: bpy.types.Image) -> np.ndarray:
    tgt_node.image = image
    nt.nodes.active = tgt_node
    if kind == "POS":
        nt.links.new(tc.outputs["Object"], em.inputs[0])
        nt.links.new(em.outputs[0], outn.inputs["Surface"])
        bpy.ops.object.bake(type="EMIT")
    elif kind == "MASK":
        em.inputs[0].default_value = (1, 1, 1, 1)
        for link in list(em.inputs[0].links):
            nt.links.remove(link)
        sc.render.bake.margin = 0
        bpy.ops.object.bake(type="EMIT")
        sc.render.bake.margin = 4
    else:
        nt.links.new(surf, outn.inputs["Surface"])
        bpy.ops.object.bake(type="NORMAL", normal_space="OBJECT")
    return np.array(image.pixels[:], np.float32).reshape(H, W, 4)


pos = bake("POS", new_float("_pos"))[..., :3].astype(np.float64)
mask = bake("MASK", new_float("_mask"))[..., 0] > 0.5
nrm = bake("NRM", new_float("_nrm"))[..., :3].astype(np.float64) * 2 - 1
nt.links.new(surf, outn.inputs["Surface"])
covered = np.linalg.norm(nrm, axis=-1) > 0.5  # margin texels too, so the seams have colour
nrm /= np.maximum(np.linalg.norm(nrm, axis=-1, keepdims=True), 1e-6)
pos = pos @ np.array(M.to_3x3()).T + np.array(M.translation)  # object -> world (identity for a glTF import)
report["texels_covered"] = int(mask.sum())
lap("bake")

# ------------------------------------------------------------------ pick the camera: silhouette, then edge agreement
bvh = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
inp_rgb = inp[..., :3]
# erode the alpha so samples near the silhouette never pick up background
er = alpha.copy()
for _ in range(3):
    er = er & np.roll(er, 1, 0) & np.roll(er, -1, 0) & np.roll(er, 1, 1) & np.roll(er, -1, 1)
# Silhouettes of a symmetric box-like object (a car) seen front-left and rear-right are nearly the same, so render the
# TRELLIS mesh itself from each candidate and compare its edge structure with the input (texture colours alone are no
# help: TRELLIS calls car paint metallic and keeps its base colour dark).
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = 256
sc.render.film_transparent = True
world = bpy.data.worlds.new("_w")
sc.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.6, 0.6, 1)
sun = bpy.data.objects.new("_sun", bpy.data.lights.new("_sun", "SUN"))
sun.data.energy = 3
sun.rotation_euler = (0.6, 0.0, 0.0)
sc.collection.objects.link(sun)
camo = bpy.data.objects.new("_cam", bpy.data.cameras.new("_cam"))
sc.collection.objects.link(camo)
sc.camera = camo
lw = np.array([0.299, 0.587, 0.114])


def crop_square(grey: np.ndarray, m: np.ndarray, box: tuple[float, float, float, float], n: int = 128) -> np.ndarray:
    bx0, by0, bx1, by1 = box
    sd = max(bx1 - bx0, by1 - by0) * 1.1
    mx_, my_ = (bx0 + bx1) / 2, (by0 + by1) / 2
    yy, xx = np.mgrid[0:n, 0:n]
    yi = np.clip((my_ - sd / 2 + (yy + 0.5) * sd / n).astype(int), 0, grey.shape[0] - 1)
    xi = np.clip((mx_ - sd / 2 + (xx + 0.5) * sd / n).astype(int), 0, grey.shape[1] - 1)
    return np.where(m[yi, xi], grey[yi, xi], 0.0)


def edges(g: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(g)
    return np.hypot(gx, gy)


ref = edges(crop_square(inp_rgb @ lw, alpha, bbox(alpha)))
rng = np.random.default_rng(1)
tr, tcl = np.nonzero(mask)
pick = rng.choice(len(tr), min(len(tr), 80_000), replace=False)
Ps, Ns = pos[tr[pick], tcl[pick]], nrm[tr[pick], tcl[pick]]


def features(rgb: np.ndarray) -> np.ndarray:
    """log luminance plus two log-chroma axes: a red body and grey glass have the same luminance, not the same hue."""
    lg = np.log(rgb + 0.02)
    return np.stack([np.log(rgb @ lw + 0.02), lg[..., 0] - lg[..., 1], lg[..., 2] - lg[..., 1]], -1)


Ls = features(trellis_rgba[tr[pick], tcl[pick], :3].astype(np.float64))
inp_feat = features(inp_rgb.astype(np.float64))


def pooled_corr(c: dict, n: int) -> float:
    """Unlit TRELLIS base colour vs the input, both averaged over an n x n grid of the input's object box: where the
    dark parts (glass, tyres, grille) are, independent of the lighting and of a few pixels of misalignment."""
    use_camera(c)
    view = eye - Ps
    view /= np.linalg.norm(view, axis=1, keepdims=True)
    px, _ = to_pixels(Ps)
    ok = ((view * Ns).sum(1) > 0.3) & (px[:, 0] >= 0) & (px[:, 0] < IW) & (px[:, 1] >= 0) & (px[:, 1] < IH)
    ok[ok] &= alpha[px[ok, 1].astype(int), px[ok, 0].astype(int)]
    for i in np.nonzero(ok)[0]:  # inner shells: keep what the camera sees
        d = Vector(eye - Ps[i])
        if bvh.ray_cast(Vector(Ps[i] + Ns[i] * 2e-3), d.normalized(), d.length)[0] is not None:
            ok[i] = False
    bx0, by0, bx1, by1 = bbox(alpha)
    cell = lambda x, y: (np.clip(((y - by0) / (by1 - by0) * n).astype(int), 0, n - 1) * n  # noqa: E731
                         + np.clip(((x - bx0) / (bx1 - bx0) * n).astype(int), 0, n - 1))  # fmt: skip
    ct = cell(px[ok, 0], px[ok, 1])
    t_cnt = np.bincount(ct, None, n * n)
    yy, xx = np.nonzero(alpha)
    ci = cell(xx, yy)
    i_cnt = np.bincount(ci, None, n * n)
    k = (t_cnt >= 5) & (i_cnt >= 20)
    corrs = []
    for f in range(3):
        t = np.bincount(ct, Ls[ok, f], n * n)[k] / t_cnt[k]
        i = np.bincount(ci, inp_feat[yy, xx, f], n * n)[k] / i_cnt[k]
        corrs.append(np.corrcoef(t, i)[0, 1])
    return float(np.nanmean(corrs))


scored = []
for iou, c in candidates:
    pc8, pc16 = pooled_corr(c, 8), pooled_corr(c, 16)
    use_camera(c)
    camo.location = Vector(eye)
    camo.rotation_euler = Vector(centre - eye).to_track_quat("-Z", "Y").to_euler()
    camo.data.lens_unit = "FOV"
    camo.data.angle = 2 * math.atan(0.4 / c["f"])  # the object (~0.31 in projected units) fills the frame
    sc.render.filepath = GLB_OUT.rsplit(".", 1)[0] + f"_cand{len(scored)}.png"
    bpy.ops.render.render(write_still=True)
    rimg = bpy.data.images.load(sc.render.filepath)
    rp = np.array(rimg.pixels[:], np.float32).reshape(256, 256, 4)[::-1]
    rm = rp[..., 3] > 0.5
    corr = float(np.corrcoef(edges(crop_square(rp[..., :3] @ lw, rm, bbox(rm))).ravel(), ref.ravel())[0, 1])
    scored.append((corr, iou, c, pc8, pc16))
report["camera_candidates"] = [
    {"az": round(float(c["az"]), 1), "el": round(float(c["el"]), 1), "fov": round(float(c["fov"]), 1),
     "iou": round(iou, 4), "edge_corr": round(corr, 3), "pooled8": round(pc8, 3), "pooled16": round(pc16, 3)}
    for corr, iou, c, pc8, pc16 in scored
]  # fmt: skip
scored = [((pc8 + pc16) / 2, iou, c) for _, iou, c, pc8, pc16 in scored]  # edge agreement did not separate them
corr, iou, c = max(scored, key=lambda t: t[0])
use_camera(c)
report["camera"] = {k: round(float(v), 3) for k, v in cam.items() if k != "off"}
report["silhouette_iou"] = round(iou, 4)
report["pooled_corr"] = round(corr, 3)

# ------------------------------------------------------------------ visibility + sampling


def seen_colour(p: np.ndarray, n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Image colour and weight (0..1) for points p with normals n as seen by the fitted camera."""
    view = eye - p
    view /= np.linalg.norm(view, axis=1, keepdims=True)
    facing = (view * n).sum(1)
    w = np.clip((facing - 0.15) / 0.35, 0, 1)
    px, _ = to_pixels(p)
    inside = (px[:, 0] >= 0) & (px[:, 0] < IW - 1) & (px[:, 1] >= 0) & (px[:, 1] < IH - 1)
    w[~inside] = 0
    xi = np.clip(px[:, 0], 0, IW - 2)
    yi = np.clip(px[:, 1], 0, IH - 2)
    w *= er[yi.round().astype(int), xi.round().astype(int)]
    cand = np.nonzero(w > 0)[0]
    eps = 2e-3
    for i in cand:  # occlusion: anything between the point and the camera
        o = Vector(p[i] + n[i] * eps)
        d = Vector(eye - p[i])
        dist = d.length
        hit = bvh.ray_cast(o, d.normalized(), dist)
        if hit[0] is not None:
            w[i] = 0
    x_, y_ = np.floor(xi).astype(int), np.floor(yi).astype(int)
    fx, fy = (xi - x_)[:, None], (yi - y_)[:, None]
    c = (
        inp_rgb[y_, x_] * (1 - fx) * (1 - fy)
        + inp_rgb[y_, x_ + 1] * fx * (1 - fy)
        + inp_rgb[y_ + 1, x_] * (1 - fx) * fy
        + inp_rgb[y_ + 1, x_ + 1] * fx * fy
    )
    return c, w


rows, cols = np.nonzero(covered)
P, Nn = pos[rows, cols], nrm[rows, cols]
col_direct, w_direct = seen_colour(P, Nn)
report["texels_seen"] = int((w_direct > 0.5).sum())
lap("project")

# ------------------------------------------------------------------ mirror (vertical symmetry plane)
w_mirror = np.zeros_like(w_direct)
col_mirror = np.zeros_like(col_direct)
if MIRROR:
    G = 96
    lo, hi = verts.min(0) - 0.02, verts.max(0) + 0.02
    occ = np.zeros((G, G, G), bool)
    q = ((sample - lo) / (hi - lo) * (G - 1)).round().astype(int)
    occ[q[:, 0], q[:, 1], q[:, 2]] = True
    for ax in range(3):  # one voxel of tolerance: a reflected surface point rarely lands in the exact voxel
        occ = occ | np.roll(occ, 1, ax) | np.roll(occ, -1, ax)

    def sym_score(theta: float, off: float) -> float:
        nvec = np.array([math.cos(theta), math.sin(theta), 0.0])
        d = (sample - centre) @ nvec - off
        r = sample - 2 * d[:, None] * nvec
        qq = ((r - lo) / (hi - lo) * (G - 1)).round().astype(int)
        ok = np.all((qq >= 0) & (qq < G), 1)
        return float(occ[qq[ok, 0], qq[ok, 1], qq[ok, 2]].sum() / len(sample))

    sbest = (0.0, 0.0, 0.0)
    for th in np.radians(np.arange(0, 180, 2)):
        for off in np.arange(-0.1, 0.101, 0.02):
            sbest = max(sbest, (sym_score(th, off), th, off))
    _, th0, off0 = sbest
    for th in np.radians(np.arange(math.degrees(th0) - 2, math.degrees(th0) + 2.01, 0.25)):
        for off in np.arange(off0 - 0.02, off0 + 0.0201, 0.004):
            sbest = max(sbest, (sym_score(th, off), th, off))
    sym, th, off = sbest
    report["symmetry"] = {"score": round(sym, 4), "theta_deg": round(math.degrees(th), 2), "offset": round(off, 4)}
    if sym > 0.85:  # only clearly symmetric objects
        nvec = np.array([math.cos(th), math.sin(th), 0.0])
        need = np.nonzero(w_direct < 0.99)[0]
        d = (P[need] - centre) @ nvec - off
        Pm = P[need] - 2 * d[:, None] * nvec
        Nm = Nn[need] - 2 * (Nn[need] @ nvec)[:, None] * nvec
        c, w = seen_colour(Pm, Nm)
        col_mirror[need], w_mirror[need] = c, w
    report["texels_mirrored"] = int(((w_mirror > 0.5) & (w_direct <= 0.5)).sum())
lap("mirror")

# ------------------------------------------------------------------ colour mapping for the rest, then compose
T = trellis_rgba[rows, cols, :3].astype(np.float64)
fit = w_direct > 0.8
# per-channel mean/std transfer (a least-squares fit shrinks towards the mean and loses contrast)
# one gain for all channels (from luminance; per-channel gains blow up the noise of a channel with little spread, e.g.
# green and blue on a red car), clamped, plus a per-channel offset
gain = float(np.clip((col_direct[fit] @ lw).std() / max((T[fit] @ lw).std(), 1e-4), 0.7, 2.0))
T_mapped = np.clip((T - T[fit].mean(0)) * gain + col_direct[fit].mean(0), 0, 1)
report["colour_gain"] = round(gain, 3)
wd, wm = w_direct[:, None], w_mirror[:, None]
out = wd * col_direct + (1 - wd) * (wm * col_mirror + (1 - wm) * T_mapped)
res = trellis_rgba.copy()
res[rows, cols, :3] = out
base.pixels.foreach_set(res.astype(np.float32).ravel())
base.update()


def lum_stats(c: np.ndarray) -> dict:
    lum = c @ np.array([0.299, 0.587, 0.114]) * 255
    return {
        "std": round(float(lum.std()), 1),
        "p5": round(float(np.percentile(lum, 5))),
        "p95": round(float(np.percentile(lum, 95))),
    }


report["lum_input"] = lum_stats(inp_rgb[alpha])
report["lum_trellis"] = lum_stats(T[mask[rows, cols]])
report["lum_out"] = lum_stats(out[mask[rows, cols]])

# ------------------------------------------------------------------ export
for n in (tgt_node, tc, em):
    nt.nodes.remove(n)
bpy.ops.export_scene.gltf(filepath=GLB_OUT, export_format="GLB", use_selection=False, export_image_format="AUTO")
lap("total")
with open(GLB_OUT.rsplit(".", 1)[0] + ".json", "w") as f:
    json.dump(report, f, indent=1)
print("REPORT", json.dumps(report))
