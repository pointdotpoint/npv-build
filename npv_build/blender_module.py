"""Bake V's CC face morphs into a head mesh via Blender, headless.

Pipeline (all proven working):
  1. extract the head morphtarget (.morphtarget) + the head .mesh CR2W skeleton
  2. WolvenKit export the .morphtarget -> .glb (105 named shapekeys)
  3. blender --background bake_head.py: set V's shapekeys to 1.0, bake, export glb
  4. WolvenKit import --keep: rebuild a .mesh from the baked glb, reusing the
     original head .mesh as the CR2W skeleton (keeps rig/skinning/materials)

Produces a mod-scoped baked head .mesh placed into the build dir. The caller
points the NPV head part .ent's mesh component at it.

Flatpak Blender note: the sandbox cannot read /tmp; we stage under $HOME and
require `flatpak override --user --filesystem=host org.blender.Blender` (done
once at setup).
"""
import json
import os
import shutil
import subprocess
from pathlib import Path


class BlenderError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.module_name = "Blender Bake"


CLI_BINARY = "WolvenKit.CLI"
BAKE_SCRIPT = Path(__file__).parent / "data" / "blender" / "bake_head.py"

# Head morphtarget + face mesh per rig (preset 0 / basehead). Other presets
# would extend this; basehead covers the common case.
HEAD_MORPHTARGET = {
    "pwa": "base\\characters\\head\\player_base_heads\\player_female_average\\h0_000_pwa__morphs.morphtarget",
    "pma": "base\\characters\\head\\player_base_heads\\player_man_average\\h0_000_pma__morphs.morphtarget",
}
# Use the canonical player_base_heads mesh — the SAME mesh the morphtarget's
# baseMesh points at (the glb is exported from that morphtarget). The legacy
# base\characters\head\{pwa,pma}\ variant shares the basename but is a stale
# revision with only 7 materials, h0_001 texture refs, and no _dXX detail
# entries, and skin mods don't override its texture tree. Using the canonical
# mesh as the import --keep CR2W skeleton makes the baked head inherit the full
# 60+ material set with player_*_average texture paths that skin mods override.
HEAD_FACE_MESH = {
    "pwa": "base\\characters\\head\\player_base_heads\\player_female_average\\h0_000_pwa_c__basehead\\h0_000_pwa_c__basehead.mesh",
    "pma": "base\\characters\\head\\player_base_heads\\player_man_average\\h0_000_pma_c__basehead\\h0_000_pma_c__basehead.mesh",
}

# heb_ is a SECOND full-face skin-detail layer sharing the exact same 105 face
# morphs as h0_. It must be baked with V's morphs too, or it renders at the
# neutral shape and overlaps the morphed h0_ head -> doubled jaw/mouth.
HEB_MORPHTARGET = {
    "pwa": "base\\characters\\head\\player_base_heads\\player_female_average\\heb_000_pwa__morphs.morphtarget",
    "pma": "base\\characters\\head\\player_base_heads\\player_man_average\\heb_000_pma__morphs.morphtarget",
}
HEB_FACE_MESH = {
    "pwa": "base\\characters\\head\\player_base_heads\\player_female_average\\h0_000_pwa_c__basehead\\heb_000_pwa_c__basehead.mesh",
    "pma": "base\\characters\\head\\player_base_heads\\player_man_average\\h0_000_pma_c__basehead\\heb_000_pma_c__basehead.mesh",
}

APPEARANCE_ARCHIVE = "basegame_4_appearance.archive"
ANIM_ARCHIVE = "basegame_4_animation.archive"


def _blender_cmd():
    """Return the argv prefix to invoke Blender headless."""
    if shutil.which("blender"):
        return ["blender"]
    # flatpak fallback
    return ["flatpak", "run", "org.blender.Blender"]


def _depot_to_rel(depot: str) -> str:
    return depot.replace("\\", "/")


def _run(cmd, verbosity, error_prefix):
    stream = verbosity >= 2
    try:
        res = subprocess.run(
            cmd,
            stdout=None if stream else subprocess.PIPE,
            stderr=None if stream else subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as e:
        raise BlenderError(f"{error_prefix}: command not found: {e}")
    if res.returncode != 0:
        tail = ""
        if not stream:
            tail = "\n" + ((res.stderr or "") + (res.stdout or ""))[-1500:]
        raise BlenderError(f"{error_prefix}: exit {res.returncode}.{tail}")
    return res


def bake_face_mesh(game_dir: Path, body_rig: str, face_morphs: dict, out_mesh_path: Path,
                   verbosity: int = 0, wk=None, mt_depot: str = None, mesh_depot: str = None,
                   stage_name: str = "bake"):
    """Run the full bake chain. Returns the path to the baked .mesh (out_mesh_path)
    on success, or None if morphs/assets are unavailable (caller falls back to
    the stock head mesh).

    mt_depot / mesh_depot default to the main head (h0_) morphtarget+mesh, but can
    be overridden to bake any other part that shares V's 105 face morphs (e.g. the
    heb_ skin-detail layer). stage_name isolates the staging dir per part so
    concurrent/sequential bakes don't clobber each other.
    """
    if not game_dir or not face_morphs:
        return None
    if body_rig not in HEAD_MORPHTARGET:
        if verbosity > 0:
            print(f"[Blender] no morphtarget mapping for rig {body_rig}; skipping bake")
        return None

    content = game_dir / "archive" / "pc" / "content"
    appearance_arch = content / APPEARANCE_ARCHIVE
    if not appearance_arch.exists():
        return None

    # Stage under $HOME so flatpak Blender can read it.
    stage = Path(os.path.expanduser("~")) / ".cache" / "npv" / stage_name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True, exist_ok=True)

    mt_depot = mt_depot or HEAD_MORPHTARGET[body_rig]
    mesh_depot = mesh_depot or HEAD_FACE_MESH[body_rig]
    mt_basename = mt_depot.replace("\\", "/").rsplit("/", 1)[-1]   # h0_000_pwa__morphs.morphtarget
    mesh_basename = mesh_depot.replace("\\", "/").rsplit("/", 1)[-1]

    # 1. extract morphtarget + face mesh (CR2W skeletons) into a depot tree.
    extract_dir = stage / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    import re as _re
    rgx = r"(" + _re.escape(mt_basename) + r"|" + _re.escape(mesh_basename) + r")$"
    if wk:
        wk.extract(rgx, archive=appearance_arch, dest=extract_dir)
    else:
        _run([CLI_BINARY, "extract", str(appearance_arch), "-o", str(extract_dir), "-r", rgx],
             verbosity, "ExtractFailed")

    mt_fs = extract_dir / _depot_to_rel(mt_depot)
    mesh_fs = extract_dir / _depot_to_rel(mesh_depot)
    if not mt_fs.exists() or not mesh_fs.exists():
        if verbosity > 0:
            print(f"[Blender] extract missing files (mt={mt_fs.exists()}, mesh={mesh_fs.exists()}); skip bake")
        return None

    # 2. export morphtarget -> glb
    glb_dir = stage / "glb"
    glb_dir.mkdir(parents=True, exist_ok=True)
    if wk:
        in_glb = wk.export(mt_fs, dest=glb_dir)
    else:
        _run([CLI_BINARY, "export", str(mt_fs), "-o", str(glb_dir), "-gp", str(game_dir)],
             verbosity, "ExportFailed")
        in_glb = glb_dir / (mt_basename + ".glb")
        if not in_glb.exists():
            cands = list(glb_dir.glob("*.glb"))
            if not cands:
                raise BlenderError("ExportFailed: no .glb produced from morphtarget")
            in_glb = cands[0]

    # 3. blender bake
    job = {"morphs": face_morphs}
    job_path = stage / "job.json"
    with open(job_path, "w") as f:
        json.dump(job, f)
    baked_glb = stage / "baked.glb"
    # bake script must be readable by flatpak: copy it under $HOME stage.
    local_script = stage / "bake_head.py"
    shutil.copy2(BAKE_SCRIPT, local_script)
    if verbosity > 0:
        print(f"[Blender] baking morphs {face_morphs} ...")
    _run(_blender_cmd() + ["--background", "--python", str(local_script), "--",
                           str(in_glb), str(baked_glb), str(job_path)],
         verbosity, "BakeFailed")
    if not baked_glb.exists():
        raise BlenderError("BakeFailed: no baked .glb produced")

    # 4. import --keep: rebuild a .mesh from baked glb using original mesh CR2W.
    # Place baked glb next to the original mesh (same stem) so --keep matches it.
    # Import ONLY the mesh's own directory; also tolerate WolvenKit's exit code
    # 3 when the actual mesh import succeeded (it returns non-zero for any
    # peripheral file warning even though "Imported 1/1 file(s)" succeeded).
    glb_for_import = mesh_fs.parent / (mesh_fs.stem + ".glb")
    shutil.copy2(baked_glb, glb_for_import)
    if verbosity > 0:
        print(f"[Blender] importing baked glb: {glb_for_import}")
    mesh_mtime_before = mesh_fs.stat().st_mtime if mesh_fs.exists() else 0
    if wk:
        from .wk_cli import WolvenKitError
        try:
            wk.import_mesh(mesh_fs.parent, dest=mesh_fs.parent, allow_exit_codes=(3,))
        except WolvenKitError:
            if not mesh_fs.exists() or mesh_fs.stat().st_mtime <= mesh_mtime_before:
                raise
    else:
        try:
            _run([CLI_BINARY, "import", str(mesh_fs.parent), "-o", str(mesh_fs.parent),
                  "--keep", "-gp", str(game_dir)],
                 verbosity, "ImportFailed")
        except BlenderError:
            if not mesh_fs.exists() or mesh_fs.stat().st_mtime <= mesh_mtime_before:
                raise

    # mesh_fs is now rebuilt with baked geometry.
    out_mesh_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mesh_fs, out_mesh_path)
    if verbosity > 0:
        print(f"[Blender] baked head mesh -> {out_mesh_path}")
    return out_mesh_path
