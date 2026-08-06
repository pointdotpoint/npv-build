"""Render an assembled NPV appearance to preview PNGs via headless Blender.

Pipeline: read the build's `npv_components.json`, locate each mesh component's
CR2W file (mod-scoped meshes live under the build's own `source/archive/`;
everything else is extracted from the game's base appearance archive, falling
back to a scan of installed mod archives — some components, like VTK
headpatch/seamfix or CCXL hair/eyes, are never copied into the built mod and
are resolved live from the user's other installed archives at game runtime),
export each to .glb via WolvenKit, write a manifest, then hand off to
`data/blender/render_npv.py` (Task 2) which imports the glbs and renders the
requested views.

Preview rendering is best-effort, unlike the main build (which hard-fails on
first error): a component whose mesh can't be found in any archive, or that
WolvenKit's exporter rejects for asset-specific reasons outside npv-build's
control, is skipped rather than aborting the whole preview. A missing
*mod-scoped* mesh (the build's own output) is still a hard failure — that
always means the build itself needs to be redone.

Skips are never silent: every skipped component is recorded in
`render_report.json` next to the PNGs ({name, depot, reason}), plus one
summary warning logged with the count, so the preview is explicitly labeled
incomplete rather than quietly missing parts.

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
from .wk_cli import WolvenKitError

logger = logging.getLogger(__name__)

DEFAULT_VIEWS = (
    {"name": "full_front", "framing": "body", "yaw_deg": 0},
    {"name": "face_front", "framing": "face", "yaw_deg": 0},
    {"name": "face_34", "framing": "face", "yaw_deg": 35},
)

RENDER_SCRIPT = Path(__file__).parent / "data" / "blender" / "render_npv.py"

_MOD_SCOPED_PREFIX = "base\\npv-build\\"


class _MeshUnavailable(Exception):
    """A mesh could not be found in any known archive. Soft-skip, not a hard build failure —
    unlike a missing mod-scoped mesh (which means the build itself is broken)."""


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


def _mod_archives(game_dir: Path | None):
    """Installed mod .archive files, same scan style as wolvenkit._resolve_garment_mesh."""
    if not game_dir:
        return []
    mod_dir = Path(game_dir) / "archive" / "pc" / "mod"
    if not mod_dir.exists():
        return []
    return [
        a
        for a in sorted(mod_dir.glob("*.archive"))
        if not a.name.startswith("my_v_") and a.name != "archive.archive"
    ]


def _find_in_mod_archives(wk, depots: list[str], stage: Path) -> dict[str, Path]:
    """Locate depot paths that are not in the base appearance archive.

    Some components (e.g. VTK headpatch/seamfix, CCXL hair/eyes) are never
    copied into the built mod — the game resolves them live from whatever mod
    archive the user has installed. Preview rendering needs the actual bytes.

    A naive per-depot, per-archive `extract` scan is ~5-10s/call (CLI process
    spin-up dominates, not I/O) and there are ~300+ installed mod archives on
    a typical setup with the matching archive potentially near the end of an
    alphabetical scan — that's 20-50 minutes for a handful of misses. This
    instead does exactly one `list_archive` call per archive (all missing
    depots in a single combined regex) to find which archive(s) hold them,
    then one `extract` call per archive that had a hit — and tries archives
    whose filename hints at the depot's first path segment (e.g. an archive
    named "...VTK..." for a "base\\vtk\\..." depot) before falling back to a
    full alphabetical scan, since that pattern held for every mod-sourced
    depot seen in practice (vtk, ccxl, sedth, b1w, ...).
    """
    game_dir = wk.config.game_dir
    archives = _mod_archives(game_dir)
    if not archives or not depots:
        return {}

    remaining = set(depots)
    combined_regex = "|".join(re.escape(d) for d in remaining)
    extract_dir = stage / "extract_mod"
    found: dict[str, Path] = {}

    hints = {d.split("\\")[1].lower() for d in remaining if len(d.split("\\")) > 1}
    hinted = [a for a in archives if any(h in a.name.lower() for h in hints)]
    unhinted = [a for a in archives if a not in hinted]

    for arch in hinted + unhinted:
        if not remaining:
            break
        try:
            matches = wk.list_archive(combined_regex, archive=arch)
        except WolvenKitError:
            continue
        hits = remaining & set(matches)
        if not hits:
            continue
        try:
            wk.extract(combined_regex, archive=arch, dest=extract_dir)
        except WolvenKitError:
            continue
        for depot in hits:
            path = extract_dir / Path(*depot.split("\\"))
            if path.exists():
                found[depot] = path
                remaining.discard(depot)

    return found


def _locate_cr2w(wk, depot: str, stage: Path, build_dir: Path, mod_hits: dict[str, Path]) -> Path:
    if depot.startswith(_MOD_SCOPED_PREFIX):
        local = build_dir / "source" / "archive" / Path(*depot.split("\\"))
        if not local.exists():
            raise NpvError(
                f"RenderFailed: mod-scoped mesh not found: {depot}",
                remediation="Rebuild the mod before rendering a preview.",
                module_name="Appearance Render",
            )
        return local

    # 1. Base game appearance archive (vanilla assets) — already batch-extracted
    # by _base_archive_misses into stage/"extract" for every non-mod-scoped depot.
    extracted = stage / "extract" / Path(*depot.split("\\"))
    if extracted.exists():
        return extracted

    # 2. Pre-resolved installed mod archives (see _find_in_mod_archives).
    if depot in mod_hits:
        return mod_hits[depot]

    raise _MeshUnavailable(depot)


def _base_archive_misses(wk, depots: list[str], stage: Path) -> list[str]:
    """Depots not extractable from the base appearance archive, batched into one call."""
    extract_dir = stage / "extract"
    combined_regex = "|".join(re.escape(d) for d in depots)
    try:
        wk.extract(combined_regex, dest=extract_dir)
    except WolvenKitError:
        pass
    return [d for d in depots if not (extract_dir / Path(*d.split("\\"))).exists()]


def _gather_meshes(wk, build_dir: Path, stage: Path, cancel) -> tuple[list[dict], list[dict]]:
    """Returns (meshes, skipped). `skipped` entries are {name, depot, reason} —
    see render_appearance's render_report.json for why this isn't just a log line:
    a preview must never look complete while quietly missing parts."""
    components = _mesh_components(build_dir)
    non_mod_scoped = [c["mesh"] for c in components if not c["mesh"].startswith(_MOD_SCOPED_PREFIX)]

    mod_hits: dict[str, Path] = {}
    if non_mod_scoped:
        if cancel is not None:
            cancel.raise_if_cancelled()
        missing = _base_archive_misses(wk, non_mod_scoped, stage)
        if missing:
            if cancel is not None:
                cancel.raise_if_cancelled()
            mod_hits = _find_in_mod_archives(wk, missing, stage)

    meshes = []
    skipped = []
    for i, comp in enumerate(components):
        if cancel is not None:
            cancel.raise_if_cancelled()

        depot = comp["mesh"]
        try:
            cr2w = _locate_cr2w(wk, depot, stage, build_dir, mod_hits)
        except _MeshUnavailable:
            skipped.append(
                {
                    "name": comp["name"],
                    "depot": depot,
                    "reason": "mesh not found in game or mod archives",
                }
            )
            continue

        glb_dir = stage / "glb" / str(i)
        glb_dir.mkdir(parents=True, exist_ok=True)
        try:
            # clay-only tier (see task-1-report.md): materials export is broken on
            # Linux WolvenKit (DirectXTexNet native-init crash) and also requires a
            # MaterialRepo we don't have; skip it, we only need geometry.
            glb = wk.export(cr2w, dest=glb_dir, with_materials=False)
        except WolvenKitError as e:
            if depot.startswith(_MOD_SCOPED_PREFIX):
                # A mod-scoped mesh (the build's own output) failing to export
                # always means the build itself is broken — never best-effort,
                # matching _locate_cr2w's hard-fail for a missing mod-scoped
                # mesh above.
                raise NpvError(
                    f"RenderFailed: mod-scoped mesh failed to export: {depot}",
                    remediation="Rebuild the mod before rendering a preview.",
                    module_name="Appearance Render",
                    details=str(e),
                ) from e
            # Preview rendering is best-effort (unlike the main build, which
            # hard-fails): a small subset of meshes fail WolvenKit's classic
            # mesh exporter for structural reasons unrelated to npv-build
            # (confirmed live: base\vtk\femv_vtk_headpatch.mesh — a decal-like
            # patch mesh — returns a clean `false` from HandleMesh() with no
            # exception, while its sibling femv_seamfix.mesh in the same
            # archive exports fine). Skip and keep rendering the rest.
            skipped.append({"name": comp["name"], "depot": depot, "reason": f"export failed: {e}"})
            continue

        meshes.append(
            {
                "glb": str(glb),
                "name": comp["name"],
                "appearance": comp.get("meshAppearance", ""),
                "chunk_mask": comp.get("chunkMask", ""),
            }
        )
    return meshes, skipped


_OUTPUT_TAIL_CHARS = 1500


def _run_blender(manifest_path: Path, stage: Path, verbosity: int):
    local_script = stage / "render_npv.py"
    shutil.copy2(RENDER_SCRIPT, local_script)
    return _run(
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

        meshes, skipped = _gather_meshes(wk, build_dir, stage, cancel)

        report_path = out_dir / "render_report.json"
        report_path.write_text(json.dumps({"skipped": skipped}, indent=2), encoding="utf-8")
        if skipped:
            names = ", ".join(s["name"] for s in skipped)
            logger.warning(
                f"[Render] preview is INCOMPLETE: {len(skipped)} component(s) skipped "
                f"({names}) — see {report_path}"
            )

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

        blender_result = _run_blender(manifest_path, stage, verbosity)

        pngs = []
        for view in views:
            png = out_dir / f"{view['name']}.png"
            if not png.exists():
                stderr = getattr(blender_result, "stderr", "") or ""
                stdout = getattr(blender_result, "stdout", "") or ""
                tail = (stderr + stdout)[-_OUTPUT_TAIL_CHARS:]
                raise NpvError(
                    f"RenderFailed: view {view['name']} missing",
                    remediation="Check the Blender render log for errors.",
                    module_name="Appearance Render",
                    details=tail,
                )
            pngs.append(png)
        return pngs
    finally:
        shutil.rmtree(stage, ignore_errors=True)
