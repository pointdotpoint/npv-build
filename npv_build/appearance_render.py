"""Render an assembled NPV appearance to preview PNGs via headless Blender.

Pipeline: read the build's `npv_components.json`, locate each mesh component's
CR2W file (mod-scoped meshes live under the build's own `source/archive/`;
everything else is extracted from the game archives), export each to .glb via
WolvenKit, write a manifest, then hand off to `data/blender/render_npv.py`
(Task 2) which imports the glbs and renders the requested views.

Flatpak Blender cannot read /tmp, so all staging happens under
`~/.cache/npv/render_stage/` (same constraint as `blender_module.py`).
"""

import json
import logging
import re
import shutil
import tempfile
from pathlib import Path

from .blender_module import _blender_cmd, _run
from .core.errors import NpvError

logger = logging.getLogger(__name__)

DEFAULT_VIEWS = (
    {"name": "full_front", "framing": "body", "yaw_deg": 0},
    {"name": "face_front", "framing": "face", "yaw_deg": 0},
    {"name": "face_34", "framing": "face", "yaw_deg": 35},
)

RENDER_SCRIPT = Path(__file__).parent / "data" / "blender" / "render_npv.py"

_MOD_SCOPED_PREFIX = "base\\npv-build\\"


def _mesh_components(build_dir: Path) -> list[dict]:
    manifest_path = build_dir / "npv_components.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    components = manifest.get("components", [])

    seen_depots: set[str] = set()
    result = []
    for comp in components:
        depot = comp.get("mesh", "")
        if not (depot.endswith(".mesh") or depot.endswith(".morphtarget")):
            continue
        if depot in seen_depots:
            continue
        seen_depots.add(depot)
        result.append(comp)
    return result


def _locate_cr2w(wk, depot: str, stage: Path, build_dir: Path) -> Path:
    if depot.startswith(_MOD_SCOPED_PREFIX):
        local = build_dir / "source" / "archive" / Path(*depot.split("\\"))
        if not local.exists():
            raise NpvError(
                f"RenderFailed: mod-scoped mesh not found: {depot}",
                remediation="Rebuild the mod before rendering a preview.",
                module_name="Appearance Render",
            )
        return local

    extract_dir = stage / "extract"
    wk.extract(re.escape(depot), dest=extract_dir)
    extracted = extract_dir / Path(*depot.split("\\"))
    if not extracted.exists():
        raise NpvError(
            f"RenderFailed: could not extract mesh from game archives: {depot}",
            remediation="Verify the game install is intact and matches the mapped patch.",
            module_name="Appearance Render",
        )
    return extracted


def _gather_meshes(wk, build_dir: Path, stage: Path, cancel) -> list[dict]:
    meshes = []
    for i, comp in enumerate(_mesh_components(build_dir)):
        if cancel is not None:
            cancel.raise_if_cancelled()

        depot = comp["mesh"]
        cr2w = _locate_cr2w(wk, depot, stage, build_dir)

        glb_dir = stage / "glb" / str(i)
        glb_dir.mkdir(parents=True, exist_ok=True)
        glb = wk.export(cr2w, dest=glb_dir)

        meshes.append(
            {
                "glb": str(glb),
                "name": comp["name"],
                "appearance": comp.get("meshAppearance", ""),
                "chunk_mask": comp.get("chunkMask", ""),
            }
        )
    return meshes


def _run_blender(manifest_path: Path, stage: Path, verbosity: int) -> None:
    local_script = stage / "render_npv.py"
    shutil.copy2(RENDER_SCRIPT, local_script)
    _run(
        _blender_cmd() + ["--background", "--python", str(local_script), "--", str(manifest_path)],
        verbosity,
        "RenderFailed",
    )


def render_appearance(
    wk,
    build_dir: Path,
    out_dir: Path | None = None,
    *,
    views=DEFAULT_VIEWS,
    resolution=(768, 1024),
    materials="clay",
    verbosity: int = 0,
    cancel=None,
) -> list[Path]:
    build_dir = Path(build_dir)
    out_dir = Path(out_dir) if out_dir is not None else build_dir / "preview"
    out_dir.mkdir(parents=True, exist_ok=True)

    render_stage_root = Path.home() / ".cache" / "npv" / "render_stage"
    render_stage_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=render_stage_root))
    try:
        if cancel is not None:
            cancel.raise_if_cancelled()

        meshes = _gather_meshes(wk, build_dir, stage, cancel)

        if cancel is not None:
            cancel.raise_if_cancelled()

        manifest = {
            "meshes": meshes,
            "views": list(views),
            "resolution": list(resolution),
            "materials": materials,
            "out_dir": str(out_dir),
        }
        manifest_path = stage / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        _run_blender(manifest_path, stage, verbosity)

        pngs = []
        for view in views:
            png = out_dir / f"{view['name']}.png"
            if not png.exists():
                raise NpvError(
                    f"RenderFailed: view {view['name']} missing",
                    remediation="Check the Blender render log for errors.",
                    module_name="Appearance Render",
                )
            pngs.append(png)
        return pngs
    finally:
        shutil.rmtree(stage, ignore_errors=True)
