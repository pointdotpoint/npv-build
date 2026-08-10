"""Blender headless render of an assembled NPV: manifest in, PNGs out.

Run via:
  blender --background --python render_npv.py -- <manifest.json>

Pure bpy baseline ("clay" materials). Imports every glb listed in the
manifest, hides submeshes masked out by the component's chunkMask, keeps
only LOD 1 geometry, then renders each requested view with a fixed
camera/light rig. Deterministic by construction.
WolvenKit glb naming convention: objects are "submesh_NN_LOD_M".
"""

import json
import math
import re
import sys

import bpy
import mathutils

_SUBMESH_RE = re.compile(r"submesh_(\d+)_LOD_(\d+)", re.IGNORECASE)


def _manifest():
    argv = sys.argv
    idx = argv.index("--")
    with open(argv[idx + 1], encoding="utf-8") as f:
        return json.load(f)


def _apply_chunk_mask(imported_objects, chunk_mask):
    """Hide submeshes whose bit is cleared; drop every LOD but 1."""
    try:
        mask = int(chunk_mask) if chunk_mask else -1
    except ValueError:
        mask = -1
    kept = []
    for obj in imported_objects:
        if obj.type != "MESH":
            continue
        m = _SUBMESH_RE.search(obj.name)
        if m:
            index, lod = int(m.group(1)), int(m.group(2))
            if lod != 1 or (mask >= 0 and not (mask >> index) & 1):
                obj.hide_render = True
                obj.hide_set(True)
                continue
        kept.append(obj)
    return kept


def _clay_material():
    """Flat, non-metallic light-grey material for the whole scene.

    WolvenKit's materials-off glb export emits a stub material
    (`pbrMetallicRoughness: {}`), which glTF defaults to fully metallic +
    fully rough with no base color texture. A metallic material has no
    diffuse response and only shows specular highlights, so with just 3 area
    lights and no environment/IBL it rendered near-black. A plain diffuse
    Principled BSDF (metallic=0) makes the clay tier actually legible.
    """
    mat = bpy.data.materials.new("npv_clay")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (0.72, 0.72, 0.75, 1.0)
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Roughness"].default_value = 0.6
    return mat


def _apply_clay_material(objects, mat):
    for obj in objects:
        obj.data.materials.clear()
        obj.data.materials.append(mat)


def _scene_bounds(objs):
    points = []
    for obj in objs:
        points.extend(obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box)
    lo = mathutils.Vector(
        (min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))
    )
    hi = mathutils.Vector(
        (max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))
    )
    return lo, hi


def _add_camera(name, location, look_at):
    cam_data = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = location
    direction = look_at - location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam


def _add_lights(center, dist):
    # Camera sits on the +Y side (see main(): glb convention is character
    # faces +Y). Key/fill must be on the same +Y side as the camera to light
    # the face the camera sees; rim stays behind (-Y) for edge separation.
    for name, offset, energy in (
        ("key", (dist, dist, dist), 1200),
        ("fill", (-dist, dist, 0), 450),
        ("rim", (0, -dist, dist), 600),
    ):
        light = bpy.data.lights.new(name, "AREA")
        light.energy = energy
        light.size = dist
        obj = bpy.data.objects.new(name, light)
        obj.location = center + mathutils.Vector(offset)
        bpy.context.scene.collection.objects.link(obj)


def _pick_engine():
    try:
        engines = {
            e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
        }
    except (KeyError, AttributeError, TypeError):
        engines = set()
    return "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"


def main():
    manifest = _manifest()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    visible = []
    for entry in manifest["meshes"]:
        before = set(bpy.context.scene.objects)
        bpy.ops.import_scene.gltf(filepath=entry["glb"])
        imported = [o for o in bpy.context.scene.objects if o not in before]
        kept = _apply_chunk_mask(imported, entry.get("chunk_mask", ""))
        print(
            f"render_npv: {entry['name']} chunk_mask={entry.get('chunk_mask', '')} "
            f"imported={[o.name for o in imported]} kept={[o.name for o in kept]}",
            file=sys.stderr,
        )
        visible.extend(kept)
    if not visible:
        raise SystemExit("render_npv: no visible mesh after import/masking")

    if manifest.get("materials", "clay") == "clay":
        _apply_clay_material(visible, _clay_material())

    lo, hi = _scene_bounds(visible)
    center = (lo + hi) / 2.0
    height = hi.z - lo.z
    # Face region: top ~15% of the character's height.
    face_center = mathutils.Vector((center.x, center.y, lo.z + height * 0.925))

    _add_lights(center, height * 1.5)

    scene = bpy.context.scene
    scene.render.engine = _pick_engine()
    scene.render.resolution_x, scene.render.resolution_y = manifest["resolution"]
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"

    for view in manifest["views"]:
        framing = view["framing"]
        target = face_center if framing == "face" else center
        dist = height * (0.55 if framing == "face" else 1.8)
        yaw = math.radians(view.get("yaw_deg", 0))
        # Camera on +Y side (glb convention, verified against a real WolvenKit
        # export: character faces +Y, not -Y); yaw orbits it.
        offset = mathutils.Vector((math.sin(yaw) * dist, math.cos(yaw) * dist, 0))
        cam = _add_camera(f"cam_{view['name']}", target + offset, target)
        scene.camera = cam
        scene.render.filepath = f"{manifest['out_dir']}/{view['name']}.png"
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
