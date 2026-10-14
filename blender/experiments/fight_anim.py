"""Experiment: keyframe a short cartoon MMA exchange between two auto-rigged characters over MCP (CHANGELOG 2026-10-13).

Needs two meshes rigged by autorig.py (armatures <OBJ>_rig with the same 21 bone names). Each rig is parented to
an empty <OBJ>_ctrl at its feet; the empty carries travel, facing and the knockdown tilt. Poses are written as
target bone directions in the rig's canonical space (front -Y, up +Z, character left +X) plus an optional twist
around the bone; they are applied parent-first by setting pose matrices, then the root is shifted so the lowest
foot stays on the floor. Keys are quaternions with sign continuity, so interpolation never takes the long way.

usage: tools/blmcp/.venv/bin/python blender/experiments/fight_anim.py A_OBJ B_OBJ   (A wins)
"""

import sys

from blmcp.tools_helpers.connection import send_code

a_name, b_name = sys.argv[1], sys.argv[2]
code = r"""
import bpy, time
from bpy_extras import anim_utils
from math import radians
from mathutils import Vector, Matrix
T0 = time.time()
A, B = __A__, __B__
scene = bpy.context.scene
FPS, END = 24, 168
scene.render.fps = FPS; scene.frame_start = 1; scene.frame_end = END

# ---------- poses: {bone: (direction, twist_deg)}; .R is mirrored from .L ----------
def mir(d):
    out = dict(d)
    for k, (v, tw) in d.items():
        if k.endswith(".L"):
            out[k[:-2] + ".R"] = ((-v[0], v[1], v[2]), -tw)
    return out
def P(**kw):
    return {k.replace("__", "."): (v if isinstance(v[0], tuple) else (v, 0)) for k, v in kw.items()}
GUARD = mir(P(hips=(0, -0.05, 1), chest=(0, -0.1, 1), neck=(0, 0, 1), head=(0, 0.15, 1),
              upper_arm__L=(0.35, -0.55, -0.75), forearm__L=(-0.25, -0.45, 0.85), hand__L=(-0.1, -0.5, 0.85)))
GUARD.update(P(thigh__L=(0.1, -0.35, -0.93), shin__L=(0.05, 0.15, -0.99), foot__L=(0, -1, -0.25),
               thigh__R=(-0.1, 0.2, -0.98), shin__R=(-0.05, 0.4, -0.92), foot__R=(0, -1, -0.25),
               tail__0=(0, 1, 0.3)))
def G(base=GUARD, **kw):
    d = dict(base); d.update(P(**kw)); return d
GUARD_LOW = G(thigh__L=(0.12, -0.5, -0.86), shin__L=(0.05, 0.3, -0.95), thigh__R=(-0.12, 0.05, -0.99),
              shin__R=(-0.05, 0.55, -0.83), tail__0=(0.3, 1, 0.4))
JAB_L = G(upper_arm__L=(0.05, -1, 0.05), forearm__L=(-0.05, -1, 0.05), hand__L=(0, -1, 0),
          chest=((0, -0.25, 1), -25), hips=((0, -0.1, 1), -8))
CROSS_R = G(upper_arm__R=(0.1, -1, 0.05), forearm__R=(0.1, -1, 0.05), hand__R=(0.05, -1, 0),
            chest=((0, -0.3, 1), 35), hips=((0, -0.1, 1), 12), thigh__R=(-0.1, 0.3, -0.95))
HOOK_WIND_L = G(upper_arm__L=(0.8, -0.2, -0.2), forearm__L=(0.2, -0.9, 0.2), chest=((0, -0.2, 1), 25))
HOOK_L = G(upper_arm__L=(0.7, -0.6, 0.15), forearm__L=(-0.85, -0.5, 0.1), hand__L=(-0.85, -0.5, 0.1),
           chest=((0, -0.25, 1), -40), hips=((0, -0.1, 1), -12))
UPPER_WIND_L = G(GUARD_LOW, upper_arm__L=(0.3, -0.2, -0.95), forearm__L=(0, -0.7, 0.4), chest=((0.15, -0.3, 1), 15))
UPPER_L = G(upper_arm__L=(0.15, -0.75, -0.3), forearm__L=(-0.15, -0.25, 0.95), hand__L=(-0.1, -0.2, 1),
            chest=((0, -0.05, 1), -25), thigh__L=(0.08, -0.15, -0.98), shin__L=(0, 0, -1),
            thigh__R=(-0.08, 0.1, -0.99), shin__R=(0, 0.1, -1))
TEEP_R = G(thigh__R=(-0.05, -0.95, -0.05), shin__R=(0, -1, -0.05), foot__R=(0, -0.3, 0.95),
           thigh__L=(0.08, 0.05, -1), shin__L=(0, 0.05, -1), hips=(0, 0.25, 1), chest=(0, 0.2, 1))
KICK_WIND_R = G(thigh__R=(-0.45, -0.55, -0.6), shin__R=(-0.3, 0.6, -0.75), hips=((0, -0.1, 1), 35),
                chest=((0.25, 0, 1), 20), upper_arm__R=(-0.8, 0.3, -0.3))
KICK_R = G(thigh__R=(-0.35, -0.9, 0.15), shin__R=(0.15, -1, 0.3), foot__R=(0.3, -1, 0.1),
           hips=((0, -0.1, 1), 60), chest=((0.45, 0, 0.9), 30), head=(0.2, 0, 1),
           thigh__L=(0.1, 0, -1), shin__L=(0, 0, -1), upper_arm__R=(-0.9, 0.4, 0.1), forearm__R=(-0.7, 0.6, 0.2))
BLOCK = G(upper_arm__L=(0.2, -0.6, -0.75), forearm__L=(-0.1, -0.25, 0.96), hand__L=(-0.05, -0.2, 1),
          upper_arm__R=(-0.2, -0.6, -0.75), forearm__R=(0.1, -0.25, 0.96), hand__R=(0.05, -0.2, 1),
          chest=(0, -0.35, 1), neck=(0, -0.3, 1))
SLIP = G(chest=(-0.35, -0.15, 0.93), neck=(-0.4, -0.1, 0.9), head=(-0.3, 0, 1),
         thigh__L=(0.15, -0.45, -0.88), shin__L=(0.05, 0.3, -0.95))
HIT_HEAD = mir(P(chest=(0, 0.35, 0.94), neck=(0, 0.55, 0.85), head=(0, 0.75, 0.65),
                 upper_arm__L=(0.85, 0.1, -0.35), forearm__L=(0.6, 0.3, 0.45), hand__L=(0.5, 0.3, 0.6),
                 thigh__L=(0.1, -0.3, -0.95), shin__L=(0.05, 0.25, -0.97)))
HIT_HEAD["tail.0"] = ((0, 1, 0.6), 0)
HIT_SIDE = G(head=((-0.5, 0.1, 0.85), -35), neck=(-0.35, 0, 0.94), chest=((-0.15, 0.1, 1), -20),
             upper_arm__R=(-0.8, 0, -0.5))
HIT_BODY = G(GUARD_LOW, hips=((0.2, 0.1, 1), 25), chest=((0.35, -0.3, 0.9), 20), head=(0.2, -0.3, 1),
             upper_arm__R=(-0.3, -0.4, -0.85), forearm__R=(0.4, -0.5, 0.5))
FALLEN = mir(P(chest=(0, -0.2, 1), neck=(0, -0.4, 0.9), head=(0, -0.55, 0.85),
               upper_arm__L=(0.95, -0.1, 0.25), forearm__L=(0.9, 0.1, 0.4), hand__L=(0.8, 0.1, 0.6),
               thigh__L=(0.3, -0.15, -0.95), shin__L=(0.2, -0.1, -0.98), foot__L=(0, -0.3, 0.95)))
FALLEN["tail.0"] = ((1, 0, -0.2), 0)
VICTORY = mir(P(chest=(0, 0.1, 1), head=(0, 0.15, 1), upper_arm__L=(0.5, 0, 0.85), forearm__L=(0.3, 0, 0.95),
                hand__L=(0.2, 0, 1), thigh__L=(0.08, 0, -1), shin__L=(0, 0, -1)))
VICTORY["tail.0"] = ((0, 0.6, 1), 0)
VICTORY_PUMP = mir(P(chest=(0, 0.1, 1), head=(0, 0.25, 1), upper_arm__L=(0.75, 0, 0.6), forearm__L=(0.2, -0.3, 0.95),
                     hand__L=(0.1, -0.2, 1), thigh__L=(0.12, -0.3, -0.95), shin__L=(0.05, 0.3, -0.95)))
VICTORY_PUMP["tail.0"] = ((0.4, 0.6, 1), 0)

# ---------- setup: controller empties, camera, floor ----------
def ctrl_for(name):
    rig = bpy.data.objects[name + "_rig"]
    for c in list(rig.constraints): rig.constraints.remove(c)
    rig.animation_data_clear()
    if rig.parent: rig.parent = None
    rig.location = (0, 0, 0); rig.rotation_euler = (0, 0, 0); rig.scale = (1, 1, 1)
    old = bpy.data.objects.get(name + "_ctrl")
    if old: bpy.data.objects.remove(old)
    bpy.context.view_layer.update()
    feet = rig.matrix_world @ rig.data.bones["root"].head_local
    e = bpy.data.objects.new(name + "_ctrl", None); scene.collection.objects.link(e)
    e.empty_display_type = "CIRCLE"; e.empty_display_size = 0.3; e.location = feet
    bpy.context.view_layer.update()
    rig.parent = e; rig.matrix_parent_inverse = e.matrix_world.inverted()
    return rig, e, feet
rigA, ctrlA, feetA = ctrl_for(A)
rigB, ctrlB, feetB = ctrl_for(B)
floor_z = min(feetA.z, feetB.z)
if "fight_floor" not in bpy.data.objects:
    bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, floor_z)); bpy.context.object.name = "fight_floor"
    mat = bpy.data.materials.new("fight_floor"); mat.diffuse_color = (0.35, 0.36, 0.4, 1)
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.35, 0.36, 0.4, 1)
    bpy.context.object.data.materials.append(mat)
if "fight_cam" not in bpy.data.objects:
    cd = bpy.data.cameras.new("fight_cam"); cd.lens = 40
    cam = bpy.data.objects.new("fight_cam", cd); scene.collection.objects.link(cam)
    cam.location = (-0.15, -3.4, floor_z + 0.65); cam.rotation_euler = (radians(85), 0, 0)
    scene.camera = cam
if "fight_sun" not in bpy.data.objects:
    ld = bpy.data.lights.new("fight_sun", "SUN"); ld.energy = 3
    sun = bpy.data.objects.new("fight_sun", ld); scene.collection.objects.link(sun)
    sun.rotation_euler = (radians(40), radians(15), radians(-30))

# ---------- pose application ----------
def rest_floor(rig):
    return min(min(rig.data.bones[b].head_local.z, rig.data.bones[b].tail_local.z) for b in ("foot.L", "foot.R"))
REST = {rigA.name: rest_floor(rigA), rigB.name: rest_floor(rigB)}
prevq = {}
SPINE = {"hips", "chest", "neck", "head"}

def pose(rig, spec, frame, lift=0.0, ground=True):
    pbs = rig.pose.bones
    for pb in pbs:
        pb.rotation_mode = "QUATERNION"; pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)
    bpy.context.view_layer.update()
    for b in rig.data.bones:  # parents were created before children
        if b.name not in spec: continue
        d, tw = spec[b.name]; d = Vector(d).normalized()
        if b.name in SPINE:  # spine specs tilt the rest direction (rest heads lean differently per character)
            d = (Vector((0, 0, 1)).rotation_difference(d).to_matrix() @ b.matrix_local.col[1].xyz).normalized()
        pb = pbs[b.name]; M = pb.matrix.copy()
        R = M.col[1].xyz.normalized().rotation_difference(d).to_matrix()
        if tw: R = Matrix.Rotation(radians(tw), 3, d) @ R
        N = (R @ M.to_3x3()).to_4x4(); N.translation = M.translation
        pb.matrix = N
        bpy.context.view_layer.update()
    if ground:
        low = min(min(pbs[b].head.z, pbs[b].tail.z) for b in ("foot.L", "foot.R"))
        root = pbs["root"]; M = root.matrix.copy()
        M.translation.z += REST[rig.name] - low + lift
        root.matrix = M
        bpy.context.view_layer.update()
    for pb in pbs:
        q = pb.rotation_quaternion.copy(); key = (rig.name, pb.name)
        if key in prevq and prevq[key].dot(q) < 0:
            q.negate(); pb.rotation_quaternion = q
        prevq[key] = q
        pb.keyframe_insert("rotation_quaternion", frame=frame)
    pbs["root"].keyframe_insert("location", frame=frame)

A_face = {1: -90, 126: -90, 132: -25}  # the winner turns to the camera
def place(ctrl, frame, x, face_deg, tilt_deg=0.0, dz=0.0):
    ctrl.location = (x, ctrl.location.y, floor_z + dz)
    ctrl.rotation_euler = (radians(tilt_deg), 0, radians(face_deg))
    ctrl.keyframe_insert("location", frame=frame); ctrl.keyframe_insert("rotation_euler", frame=frame)

for r in (rigA, rigB):
    r.animation_data_clear()
    for pb in r.pose.bones: pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)
for c in (ctrlA, ctrlB): c.location.y = 0

# ---------- choreography: A faces -X from the right, B faces +X from the left ----------
FA, FB = -90, 90
A_keys = [  # frame, pose, x, extra
    (1, GUARD, 0.65), (7, GUARD_LOW, 0.6), (13, GUARD, 0.52), (19, GUARD_LOW, 0.44), (24, GUARD, 0.38),
    (28, JAB_L, 0.36), (32, GUARD, 0.38), (34, GUARD_LOW, 0.38), (38, CROSS_R, 0.35), (42, GUARD, 0.37),
    (46, HIT_SIDE, 0.39), (50, GUARD, 0.4), (56, BLOCK, 0.4), (60, BLOCK, 0.42), (64, GUARD, 0.42),
    (69, HIT_BODY, 0.56), (74, GUARD_LOW, 0.58), (80, GUARD, 0.52), (86, KICK_WIND_R, 0.42), (92, KICK_R, 0.38),
    (97, GUARD_LOW, 0.36), (100, UPPER_WIND_L, 0.32), (104, UPPER_L, 0.28), (110, GUARD, 0.3),
    (118, GUARD, 0.3), (124, GUARD_LOW, 0.32), (132, VICTORY, 0.36), (138, VICTORY_PUMP, 0.36, 0.08),
    (144, VICTORY, 0.36), (150, VICTORY_PUMP, 0.36, 0.08), (156, VICTORY, 0.36), (168, VICTORY, 0.36),
]
B_keys = [
    (1, GUARD, -0.65), (7, GUARD, -0.6), (13, GUARD_LOW, -0.52), (19, GUARD, -0.44), (24, GUARD, -0.38),
    (28, GUARD, -0.38), (30, HIT_HEAD, -0.44), (34, GUARD, -0.42), (38, SLIP, -0.4), (41, HOOK_WIND_L, -0.38),
    (45, HOOK_L, -0.34), (50, GUARD, -0.36), (54, CROSS_R, -0.34), (58, GUARD, -0.36), (62, GUARD_LOW, -0.38),
    (67, TEEP_R, -0.4), (72, GUARD, -0.44), (80, GUARD_LOW, -0.42), (86, GUARD, -0.42), (92, GUARD, -0.42),
    (95, HIT_BODY, -0.47), (100, GUARD_LOW, -0.42), (104, GUARD, -0.4), (106, HIT_HEAD, -0.46),
    (112, HIT_HEAD, -0.5), (122, FALLEN, -0.6), (168, FALLEN, -0.6),
]
B_fall = [(1, 0, 0), (106, 0, 0), (110, -12, 0), (116, -45, 0.04), (121, -84, 0.13), (124, -76, 0.15),
          (127, -84, 0.13), (168, -84, 0.13)]

def run(rig, ctrl, face, keys):
    xs = {}
    for k in keys:
        f, spec, x = k[:3]; lift = k[3] if len(k) > 3 else 0.0
        pose(rig, spec, f, lift=lift); xs[f] = x
    return xs
xa = run(rigA, ctrlA, FA, A_keys); xb = run(rigB, ctrlB, FB, B_keys)
for f, x in xa.items(): place(ctrlA, f, x, A_face[max(k for k in A_face if k <= f)])
for f in (126, 132): place(ctrlA, f, xa[max(k for k in xa if k <= f)], A_face[f])
fall = {f: (t, dz) for f, t, dz in B_fall}
for f in sorted(set(xb) | set(fall)):
    t, dz = fall.get(f, fall[max(k for k in fall if k <= f)])
    x = xb.get(f, xb[max(k for k in xb if k <= f)])
    place(ctrlB, f, x, FB, t, dz)
# the fallen pose lies on the back: no foot grounding there
for f in (122, 168):
    pose(rigB, FALLEN, f, ground=False)
# snappy strikes: no ease into the impact frame
IMPACT = {rigA.name: {28, 38, 92, 104}, rigB.name: {30, 45, 54, 67, 106}}
for r in (rigA, rigB):
    ad = r.animation_data  # Blender 5 layered actions: f-curves live in the slot's channelbag
    for fc in anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot).fcurves:
        for kp in fc.keyframe_points:
            if int(kp.co.x) in IMPACT[r.name]: kp.interpolation = "LINEAR"
scene.frame_set(1)
result = dict(frames=END, keysA=len(A_keys), keysB=len(B_keys), s=round(time.time() - T0, 1))
""".replace("__A__", repr(a_name)).replace("__B__", repr(b_name))
r = send_code(code, True)
print(r.get("result", r))
