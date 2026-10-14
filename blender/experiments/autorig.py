"""Experiment: auto-rig an upright cartoon character from TRELLIS.2 over MCP (CHANGELOG 2026-10-13).

Runs inside a live Blender over the MCP add-on (tools/blmcp). For mesh OBJ (TRELLIS canonical pose: faces -Y,
Z up, standing upright, arms away from the body) it finds joints from the vertex cloud with simple geometric
rules, builds an armature (spine, neck, head, arms, legs, feet, tail chain), computes skin weights with Blender's
automatic (bone heat) weights on a closed voxel-remeshed proxy, and copies them to the original mesh with a Data
Transfer modifier (TRELLIS meshes have inner shells and loose pieces that make bone heat fail on the original).

usage: tools/blmcp/.venv/bin/python blender/experiments/autorig.py OBJ
"""

import sys

from blmcp.tools_helpers.connection import send_code

obj_name = sys.argv[1]
code = r"""
import bpy, numpy as np, time
from mathutils import Vector
T0 = time.time(); log = {}
obj = bpy.data.objects[__OBJ__]
me = obj.data
v = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("co", v); v = v.reshape(-1, 3)
Mw = np.array(obj.matrix_world); v = v @ Mw[:3, :3].T + Mw[:3, 3]
lo, hi = v.min(0), v.max(0); H = hi[2] - lo[2]
cx = float(np.median(v[:, 0]))

# ---- tail: what sticks out behind the upper body, below mid height ----
zmid = lo[2] + 0.5 * H
back_upper = np.percentile(v[v[:, 2] > zmid, 1], 99.5)
tail_mask = (v[:, 1] > back_upper + 0.08 * H) & (v[:, 2] < zmid)  # 0.08 H: the husky's rump sticks out 0.07 H
body = v[~tail_mask]
log["tail_verts"] = int(tail_mask.sum())

# ---- front silhouette (XZ) of the body without the tail: width per row ----
R = 200
zs = np.linspace(hi[2], lo[2], R)
rows = np.clip(((hi[2] - body[:, 2]) / H * (R - 1)).astype(int), 0, R - 1)
xmin = np.full(R, np.nan); xmax = np.full(R, np.nan)
for r in range(R):
    m = rows == r
    if m.any():
        xmin[r] = body[m, 0].min(); xmax[r] = body[m, 0].max()
width = xmax - xmin
# neck: narrowest row between 25 % and 60 % of the height from the top
a, b = int(0.25 * R), int(0.60 * R)
neck_r = a + int(np.nanargmin(width[a:b]))
z_neck = float(zs[neck_r])
z_top = float(hi[2])

def band(z0, z1, pts=body):
    return pts[(pts[:, 2] >= min(z0, z1)) & (pts[:, 2] <= max(z0, z1))]

def ycenter(x, z, r=0.04 * H):
    near = body[(np.abs(body[:, 0] - x) < r) & (np.abs(body[:, 2] - z) < r)]
    # midpoint of the front and back surface; a mean is pulled toward densely tessellated details (husky belly patch)
    return float(np.percentile(near[:, 1], [2, 98]).mean()) if len(near) else float(np.median(body[:, 1]))

# ---- hands: extreme x below the neck; feet: lowest points per side ----
below = body[body[:, 2] < z_neck - 0.02 * H]
hand_L = below[np.argmax(below[:, 0])]; hand_R = below[np.argmin(below[:, 0])]
floor = body[body[:, 2] < lo[2] + 0.04 * H]
foot_L = floor[floor[:, 0] > cx].mean(0); foot_R = floor[floor[:, 0] <= cx].mean(0)
toe_L = floor[floor[:, 0] > cx]; toe_L = toe_L[np.argmin(toe_L[:, 1])]
toe_R = floor[floor[:, 0] <= cx]; toe_R = toe_R[np.argmin(toe_R[:, 1])]

# torso half width just below the neck, before the arms leave the body (arms hang away from the body)
r_sh = min(neck_r + int(0.03 * R), R - 1)
half_w = float(np.nanmax(np.abs([xmin[r_sh] - cx, xmax[r_sh] - cx])))
z_hip = float(lo[2] + 0.32 * H)
z_chest = float(z_neck - 0.15 * H)
z_shoulder = float(z_neck - 0.05 * H)
log["landmarks"] = {k: [round(float(x), 3) for x in val] for k, val in
                    dict(hand_L=hand_L, hand_R=hand_R, foot_L=foot_L, foot_R=foot_R).items()}
log["z"] = dict(neck=round(z_neck, 3), chest=round(z_chest, 3), hip=round(z_hip, 3), top=round(z_top, 3),
                half_w=round(half_w, 3))

def P(x, z, y=None):
    return Vector((x, ycenter(x, z) if y is None else y, z))

# ---- armature ----
old = bpy.data.objects.get(__OBJ__ + "_rig")
if old:
    bpy.data.armatures.remove(old.data)
arm = bpy.data.armatures.new(__OBJ__ + "_rig")
rig = bpy.data.objects.new(__OBJ__ + "_rig", arm)
bpy.context.scene.collection.objects.link(rig)
rig.show_in_front = True
for o in bpy.context.view_layer.objects: o.select_set(False)
bpy.context.view_layer.objects.active = rig; rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
eb = arm.edit_bones
def bone(name, head, tail, parent=None, connect=False):
    b = eb.new(name); b.head = head; b.tail = tail
    if parent: b.parent = eb[parent]; b.use_connect = connect
    return b
hips = P(cx, z_hip); chest = P(cx, z_chest); neck0 = P(cx, z_neck - 0.03 * H); head0 = P(cx, z_neck + 0.02 * H)
bone("root", Vector((cx, hips.y, lo[2])), Vector((cx, hips.y - 0.15 * H, lo[2])))
bone("hips", hips, chest, "root")
bone("chest", chest, neck0, "hips", True)
bone("neck", neck0, head0, "chest", True)
bone("head", head0, Vector((cx, head0.y, z_top)), "neck", True)
for side, hand, sgn in (("L", hand_L, 1), ("R", hand_R, -1)):
    sh = P(cx + sgn * 0.7 * half_w, z_shoulder)
    hand_v = Vector((float(hand[0]), ycenter(float(hand[0]) - sgn * 0.03 * H, float(hand[2])), float(hand[2])))
    wrist = sh.lerp(hand_v, 0.85); elbow = sh.lerp(hand_v, 0.45)
    bone("upper_arm." + side, sh, elbow, "chest")
    bone("forearm." + side, elbow, wrist, "upper_arm." + side, True)
    bone("hand." + side, wrist, hand_v, "forearm." + side, True)
for side, foot, toe in (("L", foot_L, toe_L), ("R", foot_R, toe_R)):
    fx = float(foot[0])
    hip_j = P(fx, z_hip - 0.02 * H); ankle = P(fx, lo[2] + 0.06 * H)
    knee = hip_j.lerp(ankle, 0.5); knee.y -= 0.01 * H
    bone("thigh." + side, hip_j, knee, "hips")
    bone("shin." + side, knee, ankle, "thigh." + side, True)
    bone("foot." + side, ankle, Vector((fx, float(toe[1]), lo[2] + 0.03 * H)), "shin." + side, True)
tail_pts = v[tail_mask]
if len(tail_pts) > 50:
    order = np.argsort(tail_pts[:, 1]); tp = tail_pts[order]
    chunks = np.array_split(tp, 4)
    joints = [Vector(c.mean(0)) for c in chunks]
    base = Vector(tp[: max(len(tp) // 20, 5)].mean(0)); base.y -= 0.05 * H
    pts = [base] + joints[1:] + [Vector(tp[-max(len(tp) // 50, 3):].mean(0))]
    parent = "hips"
    for i in range(len(pts) - 1):
        bone("tail.%d" % i, pts[i], pts[i + 1], parent, i > 0); parent = "tail.%d" % i
bpy.ops.object.mode_set(mode="OBJECT")
log["bones"] = len(arm.bones)

# ---- skin weights: bone heat on a closed voxel proxy, then transfer to the original ----
t = time.time()
proxy = obj.copy(); proxy.data = obj.data.copy(); proxy.name = __OBJ__ + "_proxy"
bpy.context.scene.collection.objects.link(proxy)
proxy.modifiers.clear(); proxy.vertex_groups.clear(); proxy.parent = None
proxy.data.remesh_voxel_size = 0.012 * H
win = bpy.context.window_manager.windows[0]
area = next(a for a in win.screen.areas if a.type == "VIEW_3D")
with bpy.context.temp_override(window=win, area=area, active_object=proxy, object=proxy, selected_objects=[proxy]):
    bpy.ops.object.voxel_remesh()
log["proxy_faces"] = len(proxy.data.polygons)
for o in bpy.context.view_layer.objects: o.select_set(False)
proxy.select_set(True); rig.select_set(True); bpy.context.view_layer.objects.active = rig
with bpy.context.temp_override(window=win, area=area, active_object=rig, object=rig, selected_objects=[proxy, rig],
                               selected_editable_objects=[proxy, rig]):
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
pw = np.zeros(len(proxy.data.vertices))
for vv in proxy.data.vertices:
    pw[vv.index] = sum(g.weight for g in vv.groups)
log["proxy_unweighted_share"] = round(float((pw < 1e-3).mean()), 4)
log["bone_heat_s"] = round(time.time() - t, 1)

obj.vertex_groups.clear()
for o in list(obj.modifiers):
    if o.type in ("ARMATURE", "DATA_TRANSFER"): obj.modifiers.remove(o)
for g in proxy.vertex_groups: obj.vertex_groups.new(name=g.name)
dt = obj.modifiers.new("weights", "DATA_TRANSFER")
dt.object = proxy; dt.use_vert_data = True; dt.data_types_verts = {"VGROUP_WEIGHTS"}
dt.vert_mapping = "POLYINTERP_NEAREST"; dt.layers_vgroup_select_src = "ALL"; dt.layers_vgroup_select_dst = "NAME"
with bpy.context.temp_override(window=win, area=area, active_object=obj, object=obj, selected_objects=[obj]):
    bpy.ops.object.modifier_apply(modifier=dt.name)
bpy.data.objects.remove(proxy)
am = obj.modifiers.new("rig", "ARMATURE"); am.object = rig
obj.parent = rig; obj.matrix_parent_inverse = rig.matrix_world.inverted()
ow = np.zeros(len(me.vertices))
for vv in me.vertices:
    ow[vv.index] = sum(g.weight for g in vv.groups)
log["unweighted_share"] = round(float((ow < 1e-3).mean()), 4)
log["total_s"] = round(time.time() - T0, 1)
result = log
""".replace("__OBJ__", repr(obj_name))
r = send_code(code, True)
print(r.get("result", r))
