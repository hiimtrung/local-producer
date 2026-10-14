"""Experiment: fix TRELLIS.2 texture colours by reprojecting the input image (CHANGELOG 2026-10-13).

Runs inside a live Blender over the MCP add-on (tools/blmcp). Copies mesh SRC to DST, bakes per-texel object-space
position and normal (Cycles, CPU), fits the matted input image to the mesh's front silhouette (scale + offset,
max IoU) and finds the texels seen from the front (normal and depth test). From those it learns a per-colour-cluster
offset in Lab (chroma always, lightness only when the seen texels agree).
  recolour (default): apply that offset to every texel; TRELLIS's own layout is kept, so part edges stay clean.
  project: seen texels take the image colour directly (rejected: colours spill across part edges, blotchy).
Assumes the input is a front view and the mesh faces -Y (TRELLIS canonical pose).

usage: tools/blmcp/.venv/bin/python blender/experiments/reproject.py SRC DST /abs/path/input.png [recolour|project]
"""

import sys

from blmcp.tools_helpers.connection import send_code

src, dst, image = sys.argv[1], sys.argv[2], sys.argv[3]
mode = sys.argv[4] if len(sys.argv) > 4 else "recolour"
code = (
    r"""
import bpy, numpy as np, time
from mathutils.bvhtree import BVHTree
T0 = time.time(); log = {}
sc = bpy.context.scene
src = bpy.data.objects[SRC]
# duplicate object, mesh and material so the original stays untouched
old = bpy.data.objects.get(DST)
if old: bpy.data.objects.remove(old)
obj = src.copy(); obj.data = src.data.copy(); obj.name = DST
sc.collection.objects.link(obj)
obj.location.x = src.location.x + 0.8
mat = src.material_slots[0].material.copy(); obj.material_slots[0].material = mat
nt = mat.node_tree
base_node = next(n for n in nt.nodes
                 if n.bl_idname == "ShaderNodeTexImage" and n.image.colorspace_settings.name == "sRGB")
base = base_node.image
W, H = base.size
outn = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
surf_from = outn.inputs["Surface"].links[0].from_socket

# ---- 1. bake object-space position and normal per texel (Cycles, CPU) ----
def new_float(name):
    im = bpy.data.images.get(name)
    if im: bpy.data.images.remove(im)
    im = bpy.data.images.new(name, W, H, alpha=True, float_buffer=True)
    im.colorspace_settings.name = "Non-Color"
    im.pixels.foreach_set(np.zeros(W * H * 4, np.float32))
    return im
pos_img, nrm_img = new_float("_bake_pos"), new_float("_bake_nrm")
tgt = nt.nodes.new("ShaderNodeTexImage")
tc = nt.nodes.new("ShaderNodeTexCoord")
vm = nt.nodes.new("ShaderNodeVectorMath"); vm.operation = "MULTIPLY_ADD"
vm.inputs[1].default_value = (0.5, 0.5, 0.5); vm.inputs[2].default_value = (0.5, 0.5, 0.5)
em = nt.nodes.new("ShaderNodeEmission")
nt.links.new(tc.outputs["Object"], vm.inputs[0]); nt.links.new(vm.outputs[0], em.inputs[0])
nt.links.new(em.outputs[0], outn.inputs["Surface"])
old_engine = sc.render.engine
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 1
for o in bpy.context.view_layer.objects: o.select_set(False)
obj.select_set(True); bpy.context.view_layer.objects.active = obj
nt.nodes.active = tgt
t = time.time()
tgt.image = pos_img
bpy.ops.object.bake(type="EMIT", margin=2, use_clear=False)
tgt.image = nrm_img
bpy.ops.object.bake(type="NORMAL", normal_space="OBJECT", margin=2, use_clear=False)
log["bake_s"] = round(time.time() - t, 1)
nt.links.new(surf_from, outn.inputs["Surface"])
for n in (tgt, tc, vm, em): nt.nodes.remove(n)
sc.render.engine = old_engine

def px(im):
    a = np.empty(im.size[0] * im.size[1] * 4, np.float32); im.pixels.foreach_get(a)
    return a.reshape(im.size[1], im.size[0], 4)
P = px(pos_img); N = px(nrm_img)
covered = P[..., 3] > 0.5
pos = (P[..., :3] - 0.5) * 2.0
nrm = N[..., :3] * 2.0 - 1.0
tex = px(base)[..., :3]
log["covered_texels"] = int(covered.sum())

# ---- 2. front depth map by ray casting along +Y (object space) ----
me = obj.data
verts = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("co", verts); verts = verts.reshape(-1, 3)
bvh = BVHTree.FromPolygons([tuple(v) for v in verts], [tuple(p.vertices) for p in me.polygons])
lo, hi = verts.min(0), verts.max(0)
R = 384
xs = np.linspace(lo[0], hi[0], R); zs = np.linspace(hi[2], lo[2], R)
depth = np.full((R, R), np.inf, np.float32)
t = time.time()
from mathutils import Vector
d = Vector((0, 1, 0)); y0 = float(lo[1]) - 1.0
for i, z in enumerate(zs):
    for j, x in enumerate(xs):
        hit = bvh.ray_cast(Vector((x, y0, z)), d)
        if hit[0] is not None: depth[i, j] = hit[0][1]
log["raycast_s"] = round(time.time() - t, 1)
sil = np.isfinite(depth)

# ---- 3. align the image to the silhouette (scale + offset, maximise IoU) ----
im = bpy.data.images.load(IMAGE, check_existing=False)
I = px(im)[::-1].copy()  # row 0 = top
bpy.data.images.remove(im)
IH, IW = I.shape[:2]
alpha = I[..., 3]
rows = np.where(alpha.max(1) > 0.5)[0]; cols = np.where(alpha.max(0) > 0.5)[0]
s0 = (hi[2] - lo[2]) / (rows[-1] - rows[0] + 1)          # mesh units per image pixel
cx0 = (cols[0] + cols[-1]) / 2; cz0 = (rows[0] + rows[-1]) / 2
mx = (lo[0] + hi[0]) / 2; mz = (lo[2] + hi[2]) / 2
def to_img(x, z, s, dx, dz):
    u = (x - mx - dx) / s + cx0; v = -(z - mz - dz) / s + cz0
    return u, v
X, Z = np.meshgrid(xs, zs)
def iou(s, dx, dz):
    u, v = to_img(X, Z, s, dx, dz)
    ui = np.clip(np.round(u).astype(int), 0, IW - 1); vi = np.clip(np.round(v).astype(int), 0, IH - 1)
    inside = (u >= 0) & (u < IW) & (v >= 0) & (v < IH)
    a = inside & (alpha[vi, ui] > 0.5)
    return (a & sil).sum() / max((a | sil).sum(), 1)
best = (iou(s0, 0, 0), s0, 0.0, 0.0); log["iou_bbox_fit"] = round(float(best[0]), 4)
step = (hi[2] - lo[2]) * 0.01
for rnd in range(3):
    _, s1, dx1, dz1 = best
    for ks in (-2, -1, 0, 1, 2):
        for kx in (-2, -1, 0, 1, 2):
            for kz in (-2, -1, 0, 1, 2):
                c = (s1 * (1 + 0.01 * ks / (rnd + 1)), dx1 + step * kx / (rnd + 1), dz1 + step * kz / (rnd + 1))
                v = iou(*c)
                if v > best[0]: best = (v,) + c
log["iou_refined"] = round(float(best[0]), 4)
_, s, dx, dz = best

# ---- 4. per texel: visible from the front? then take the image colour ----
x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
jj = np.clip(np.round((x - lo[0]) / (hi[0] - lo[0]) * (R - 1)).astype(int), 0, R - 1)
ii = np.clip(np.round((hi[2] - z) / (hi[2] - lo[2]) * (R - 1)).astype(int), 0, R - 1)
front_y = depth[ii, jj]
eps = (hi[1] - lo[1]) * 0.02
facing = -nrm[..., 1]                    # camera looks along +Y, so front faces have normal -Y
visible = covered & (y <= front_y + eps)
u, v = to_img(x, z, s, dx, dz)
ui = np.clip(np.round(u).astype(int), 0, IW - 1); vi = np.clip(np.round(v).astype(int), 0, IH - 1)
proj = I[vi, ui, :3]; pa = I[vi, ui, 3]
w = np.clip((facing - 0.15) / 0.35, 0, 1) * visible * (pa > 0.5)
log["texels_from_image"] = int((w > 0.99).sum()); log["texels_blended"] = int(((w > 0) & (w <= 0.99)).sum())

# ---- 5. hidden texels: k-means the TRELLIS colours, learn a per-cluster offset from texels seen head-on ----
rng = np.random.default_rng(0)
flat = tex[covered]
K = 10
C = flat[rng.choice(len(flat), K, replace=False)]
sub = flat[rng.choice(len(flat), min(len(flat), 60000), replace=False)]
for _ in range(25):
    lab = ((sub[:, None] - C[None]) ** 2).sum(-1).argmin(1)
    C = np.stack([sub[lab == k].mean(0) if (lab == k).any() else C[k] for k in range(K)])
train = (w > 0.99) & (facing > 0.8)
def to_lab(rgb):
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)
def from_lab(lab):
    fy = (lab[..., 0] + 16) / 116; fx = fy + lab[..., 1] / 500; fz = fy - lab[..., 2] / 200
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f > 0.2069, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.9505, 1.0, 1.089])
    M = np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]])
    c = np.clip(xyz @ M.T, 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)
tex_lab = np.zeros_like(tex); tex_lab[covered] = to_lab(tex[covered])
proj_lab = np.zeros_like(proj); proj_lab[train] = to_lab(proj[train])
d2 = ((tex[..., None, :] - C) ** 2).sum(-1)           # H, W, K (clusters found in RGB)
lab_all = d2.argmin(-1)
off = np.zeros((K, 3)); info = []
for k in range(K):
    m = train & (lab_all == k)
    if m.sum() < 200:
        info.append([[round(float(c), 2) for c in C[k]], int(m.sum()), "no data"]); continue
    dlt = proj_lab[m] - tex_lab[m]; med = np.median(dlt, axis=0)
    madL = float(np.median(np.abs(dlt[:, 0] - med[0])))
    off[k, 1:] = med[1:]                         # chroma (a, b): always
    if madL < 8: off[k, 0] = med[0]              # lightness: only when the seen texels agree
    info.append([[round(float(c), 2) for c in C[k]], int(m.sum()), round(madL, 1),
                 [round(float(o), 1) for o in off[k]]])
log["clusters"] = info
sig2 = 0.01
sw = np.exp(-(d2 - d2.min(-1, keepdims=True)) / sig2)
sw /= sw.sum(-1, keepdims=True)
corrected = tex.copy()
corrected[covered] = from_lab(tex_lab[covered] + (sw[covered][..., None] * off).sum(-2))
# MODE "project": seen texels take the image colour (exact colours, but part edges spill where the mesh and the
# image disagree); MODE "recolour": the image only teaches the per-cluster correction, every texel keeps TRELLIS's
# own layout and gets the corrected colour.
final = corrected if MODE == "recolour" else w[..., None] * proj + (1 - w[..., None]) * corrected

out = bpy.data.images.get(DST + "_base")
if out: bpy.data.images.remove(out)
out = bpy.data.images.new(DST + "_base", W, H, alpha=True)
rgba = np.concatenate([final, np.ones((H, W, 1), np.float32)], -1).astype(np.float32)
out.pixels.foreach_set(rgba.ravel())
out.pack()
base_node.image = out
for n in (pos_img, nrm_img): bpy.data.images.remove(n)
log["params"] = [round(float(s), 6), round(float(dx), 4), round(float(dz), 4)]
log["total_s"] = round(time.time() - T0, 1)
result = log
""".replace("SRC", repr(src))
    .replace("DST", repr(dst))
    .replace("IMAGE", repr(image))
    .replace("MODE", repr(mode))
)
print(send_code(code, True))
