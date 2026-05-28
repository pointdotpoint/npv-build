"""Blender headless bake: apply V's CC face morphs to the head mesh.

Run via:
  blender --background --python bake_head.py -- <in.glb> <out.glb> <job.json>

job.json: {"morphs": {"eyes":"h091","nose":"h042","mouth":"h013","jaw":"h114","ear":"h035"}}

The input .glb (a WolvenKit export of h0_*__morphs.morphtarget) carries the
base head mesh plus ~105 shapekeys named "<morph>_<region>" (e.g. h114_jaw).
We set the shapekeys matching V's selections to 1.0, bake them into the base
mesh (apply as basis), strip all shapekeys, and export a clean .glb that
WolvenKit re-imports into a .mesh.

Pure bpy, no addons. Tested against Blender 5.x.
"""
import bpy
import json
import sys


def argv_after_dashes():
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1:]
    return []


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_glb(path):
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def bake_morphs(obj, morph_region_pairs):
    """Set the named shapekeys to 1.0 then bake to a new basis.

    morph_region_pairs: list of (morph, region) -> shapekey name "<morph>_<region>".
    """
    me = obj.data
    if not me.shape_keys:
        print(f"[bake] WARNING: {obj.name} has no shape keys; skipping")
        return 0
    kb = me.shape_keys.key_blocks
    applied = 0
    wanted = {f"{m}_{r}" for (m, r) in morph_region_pairs}
    # also accept bare morph names just in case
    wanted |= {m for (m, r) in morph_region_pairs}
    for key in kb:
        if key.name in wanted:
            key.value = 1.0
            applied += 1
            print(f"[bake]   set {key.name} = 1.0")
    if applied == 0:
        print(f"[bake] WARNING: none of {sorted(wanted)} matched shapekeys on {obj.name}")
        return 0
    # Bake current shapekey mix into a new shape key, make it the basis, then
    # remove all shape keys so the mesh geometry IS the morphed result.
    obj.shape_key_add(name="__baked__", from_mix=True)
    # Move baked key to be applied: easiest is to remove all others, keep baked,
    # then 'apply' by setting mesh vertices. We delete all keys except baked,
    # then remove the remaining (single) key which leaves geometry at its values
    # only if it's the active basis. Safer: copy baked coords into mesh, drop keys.
    baked = obj.data.shape_keys.key_blocks["__baked__"]
    coords = [v.co.copy() for v in baked.data]  # baked key positions
    # Remove all shape keys
    while obj.data.shape_keys:
        obj.shape_key_remove(obj.data.shape_keys.key_blocks[0])
    # Write baked coordinates into the base mesh
    for v, co in zip(obj.data.vertices, coords):
        v.co = co
    obj.data.update()
    return applied


def triangulate(obj):
    import bmesh
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    me.update()


def export_glb(path, mesh_objs):
    # WolvenKit mesh import requires triangulated geometry WITH tangents.
    for obj in mesh_objs:
        triangulate(obj)
        # Ensure a UV layer exists (tangents need UVs) and compute tangents on export.
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=False,
        export_yup=True,
        export_skins=True,
        export_morph=False,        # morphs are baked in; export none
        export_apply=False,
        export_tangents=True,      # WolvenKit requires tangents
        export_normals=True,
    )


def main():
    args = argv_after_dashes()
    if len(args) < 3:
        print("usage: blender --background --python bake_head.py -- <in.glb> <out.glb> <job.json>")
        sys.exit(2)
    in_glb, out_glb, job_path = args[0], args[1], args[2]
    with open(job_path) as f:
        job = json.load(f)
    morphs = job.get("morphs", {})
    pairs = [(m, r) for (r, m) in morphs.items()]  # (morph, region)
    print(f"[bake] morphs: {morphs}")

    reset_scene()
    meshes = import_glb(in_glb)
    print(f"[bake] imported {len(meshes)} mesh object(s)")
    # Drop any mesh without shape keys (e.g. a stray default Icosphere) so only
    # the real head mesh is exported.
    head_meshes = [m for m in meshes if m.data.shape_keys]
    for m in meshes:
        if m not in head_meshes:
            bpy.data.objects.remove(m, do_unlink=True)
    meshes = head_meshes
    print(f"[bake] {len(meshes)} head mesh(es) after pruning")
    total = 0
    for obj in meshes:
        total += bake_morphs(obj, pairs)
    print(f"[bake] applied {total} shapekey(s) total")
    export_glb(out_glb, meshes)
    print(f"[bake] wrote {out_glb}")


if __name__ == "__main__":
    main()
