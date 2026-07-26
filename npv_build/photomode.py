"""Photo Mode asset authoring for generated NPVs.

The registration files alone are not sufficient: PhotoModeEx requires a
PhotoModeSticker icon and the game needs an entity using the Photo Mode player
component, pose animsets, and Photo Mode facial graph.  This module creates all
of those resources before WolvenKit packs the archive.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from PIL import __version__ as PILLOW_VERSION

from .core.artifact_cache import ArtifactCache
from .core.bundled_tools import bundled_tool_path
from .core.errors import NpvError
from .core.proc import run_tool
from .wk_cli import WolvenKit, WolvenKitError

logger = logging.getLogger(__name__)

ICON_SIZE = 200
MAX_IMAGE_PIXELS = 32_000_000
SUPPORTED_FORMATS = {"PNG", "JPEG", "WEBP"}


@dataclass(frozen=True)
class PhotoModeThumbnail:
    source: Path
    width: int
    height: int
    format: str
    sha256: str


@dataclass(frozen=True)
class PhotoModeArtifacts:
    entity: Path
    app: Path
    xbm: Path
    atlas: Path
    localization: Path
    preview: Path
    dds: Path
    entity_depot: str
    app_depot: str
    xbm_depot: str
    atlas_depot: str
    localization_depot: str
    loc_key: str


def runtime_dependency_status(game_dir: Path | None) -> dict[str, bool]:
    """Detect external runtime requirements without mutating the game."""
    if game_dir is None:
        return {
            "ArchiveXL": False,
            "TweakXL": False,
            "PhotoMode-EX": False,
            "Photomode NPCs Extended": False,
            "Codeware": False,
            "redscript": False,
        }
    game_dir = Path(game_dir)
    plugins = game_dir / "red4ext" / "plugins"
    mod_dir = game_dir / "archive" / "pc" / "mod"
    return {
        "ArchiveXL": (plugins / "ArchiveXL" / "ArchiveXL.dll").is_file(),
        "TweakXL": (plugins / "TweakXL" / "TweakXL.dll").is_file(),
        "PhotoMode-EX": (plugins / "PhotoModeEx" / "PhotoModeEx.dll").is_file(),
        "Photomode NPCs Extended": (
            any(mod_dir.glob("Photomode_NPCs_Extended*.archive")) if mod_dir.is_dir() else False
        ),
        "Codeware": (plugins / "Codeware" / "Codeware.dll").is_file(),
        "redscript": (
            (game_dir / "engine" / "tools" / "scc.exe").is_file()
            or (game_dir / "engine" / "tools" / "scc").is_file()
        ),
    }


def validate_thumbnail(path: Path) -> PhotoModeThumbnail:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise NpvError(
            f"Photo Mode thumbnail not found: {path}",
            remediation="Choose a PNG, JPEG, or WebP image.",
        )
    try:
        with Image.open(path) as image:
            image.seek(0)
            image.load()
            image_format = (image.format or "").upper()
            width, height = image.size
            frames = getattr(image, "n_frames", 1)
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise NpvError(
            f"Could not read Photo Mode thumbnail: {path}",
            remediation="Choose a valid PNG, JPEG, or WebP image.",
        ) from exc
    if image_format not in SUPPORTED_FORMATS:
        raise NpvError(
            f"Unsupported Photo Mode thumbnail format: {image_format or path.suffix}",
            remediation="Choose a PNG, JPEG, or WebP image.",
        )
    if frames != 1:
        raise NpvError(
            "Animated images cannot be used as a Photo Mode thumbnail.",
            remediation="Choose a static PNG, JPEG, or WebP image.",
        )
    if width < ICON_SIZE or height < ICON_SIZE:
        raise NpvError(
            f"Photo Mode thumbnail is too small ({width}x{height}).",
            remediation=f"Choose an image at least {ICON_SIZE}x{ICON_SIZE} pixels.",
        )
    if width * height > MAX_IMAGE_PIXELS:
        raise NpvError(
            f"Photo Mode thumbnail is too large ({width}x{height}).",
            remediation="Choose an image no larger than 32 megapixels.",
        )
    return PhotoModeThumbnail(
        source=path,
        width=width,
        height=height,
        format=image_format,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def thumbnail_preview_data_url(thumbnail: PhotoModeThumbnail) -> str:
    with Image.open(thumbnail.source) as image:
        image.seek(0)
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = ImageOps.fit(
            image,
            (ICON_SIZE, ICON_SIZE),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.42),
        )
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=86, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def artifact_paths(source_dir: Path, mod_id: str) -> PhotoModeArtifacts:
    depot_dir = f"base\\npv-build\\{mod_id}\\photomode"
    disk_dir = source_dir / "base" / "npv-build" / mod_id / "photomode"
    return PhotoModeArtifacts(
        entity=disk_dir / f"{mod_id}_photomode.ent",
        app=disk_dir / f"{mod_id}_photomode.app",
        xbm=disk_dir / f"{mod_id}_photomode_icon.xbm",
        atlas=disk_dir / f"{mod_id}_photomode_icon.inkatlas",
        localization=disk_dir / f"{mod_id}_photomode_i18n.json",
        preview=disk_dir / f"{mod_id}_photomode_icon.png",
        dds=disk_dir / f"{mod_id}_photomode_icon.dds",
        entity_depot=f"{depot_dir}\\{mod_id}_photomode.ent",
        app_depot=f"{depot_dir}\\{mod_id}_photomode.app",
        xbm_depot=f"{depot_dir}\\{mod_id}_photomode_icon.xbm",
        atlas_depot=f"{depot_dir}\\{mod_id}_photomode_icon.inkatlas",
        localization_depot=f"{depot_dir}\\{mod_id}_photomode_i18n.json",
        loc_key=f"npv_build_{mod_id}_photomode_name",
    )


def _valid_cached_icon(path: Path, expected_format: str) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        with Image.open(path) as image:
            image.load()
            return image.size == (ICON_SIZE, ICON_SIZE) and image.format == expected_format
    except (OSError, UnidentifiedImageError, ValueError):
        return False


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=".tmp-",
        suffix=destination.suffix,
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
    try:
        shutil.copy2(source, temp_path)
        temp_path.replace(destination)
    finally:
        temp_path.unlink(missing_ok=True)


def _normalize_thumbnail(
    thumbnail: PhotoModeThumbnail,
    artifacts: PhotoModeArtifacts,
    *,
    artifact_cache: ArtifactCache | None = None,
) -> None:
    artifacts.preview.parent.mkdir(parents=True, exist_ok=True)
    cache_preview: Path | None = None
    cache_dds: Path | None = None
    if artifact_cache is not None:
        key = {
            "schema": "photomode-icon-v1",
            "thumbnail_sha256": thumbnail.sha256,
            "icon_size": ICON_SIZE,
            "centering": [0.5, 0.42],
            "pillow_version": PILLOW_VERSION,
        }
        cache_preview = artifact_cache.path_for("photomode-icon-v1", key, ".png")
        cache_dds = artifact_cache.path_for("photomode-icon-v1", key, ".dds")
        if _valid_cached_icon(cache_preview, "PNG") and _valid_cached_icon(cache_dds, "DDS"):
            shutil.copy2(cache_preview, artifacts.preview)
            shutil.copy2(cache_dds, artifacts.dds)
            return

    with Image.open(thumbnail.source) as image:
        image.seek(0)
        image = ImageOps.exif_transpose(image).convert("RGBA")
        image = ImageOps.fit(
            image,
            (ICON_SIZE, ICON_SIZE),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.42),
        )
        image.save(artifacts.preview, format="PNG", optimize=True)
        image.save(artifacts.dds, format="DDS", pixel_format="DXT5")
    if cache_preview is not None and cache_dds is not None:
        _atomic_copy(artifacts.preview, cache_preview)
        _atomic_copy(artifacts.dds, cache_dds)


def _helper_binary() -> Path:
    configured = os.environ.get("NPV_PHOTOMODE_BINARY")
    if configured:
        binary = Path(configured).expanduser()
        if binary.is_file():
            return binary
    on_path = shutil.which("npv-photomode")
    if on_path:
        return Path(on_path)
    bundled = bundled_tool_path("npv-photomode")
    if bundled is not None:
        return bundled

    repo_root = Path(__file__).resolve().parents[1]
    project = repo_root / "tools" / "npv-photomode" / "npv-photomode.csproj"
    binary = (
        project.parent
        / "bin"
        / "Release"
        / "net8.0"
        / ("npv-photomode.exe" if os.name == "nt" else "npv-photomode")
    )
    if not binary.exists():
        run_tool(
            ["dotnet", "build", str(project), "-c", "Release", "--nologo"],
            tool="Photo Mode resource helper",
            timeout=600.0,
            logger=logger,
        )
    if not binary.is_file():
        raise NpvError(
            "Photo Mode resource helper could not be built.",
            remediation="Install the .NET 8 SDK and rebuild NPV Build.",
        )
    return binary


def photomode_helper_binary() -> Path:
    """Resolve (and, on first use, build) the Photo Mode helper executable."""
    return _helper_binary()


def _run_helper(args: list[str]) -> None:
    run_tool(
        [str(_helper_binary()), *args],
        tool="Photo Mode resource helper",
        timeout=120.0,
        logger=logger,
    )


def _resource_path(value: str) -> dict:
    return {
        "DepotPath": {
            "$type": "ResourcePath",
            "$storage": "string",
            "$value": value,
        },
        "Flags": "Default",
    }


def _anim_entry(depot: str, priority: int = 200) -> dict:
    return {
        "$type": "animAnimSetupEntry",
        "animSet": _resource_path(depot),
        "priority": priority,
        "variableNames": [],
    }


def _component_name(component: dict) -> str:
    name = component.get("name", "")
    if isinstance(name, dict):
        return str(name.get("$value", ""))
    return str(name)


def _depot_value(reference: object) -> str:
    if not isinstance(reference, dict):
        return ""
    depot = reference.get("DepotPath")
    if not isinstance(depot, dict):
        return ""
    return str(depot.get("$value", ""))


def _set_depot(reference: dict, value: str) -> None:
    depot = reference.setdefault("DepotPath", {})
    depot.update({"$type": "ResourcePath", "$storage": "string", "$value": value})


def _patch_app(data: dict, rig: str) -> None:
    root = data["Data"]["RootChunk"]
    photo_graph = {
        "pwa": "base\\animations\\facial\\_facial_graphs\\player_woman_photomode_sermo.animgraph",
        "pma": "base\\animations\\facial\\_facial_graphs\\player_man_photomode_sermo.animgraph",
    }[rig]
    base_facial = (
        "base\\animations\\ui\\photomode\\"
        f"photomode_{'female' if rig == 'pwa' else 'male'}_facial.anims"
    )
    extra_facial = [
        f"base\\animations\\xbaebsae\\pm_facials\\fem\\xbae_pm_facials_{number:02d}.anims"
        for number in range(1, 16)
    ]
    graph_count = 0
    extension_count = 0
    for appearance in root.get("appearances", []):
        appearance_data = appearance.get("Data", appearance)
        for component in appearance_data.get("components", []):
            if not isinstance(component, dict):
                continue
            for graph_key in ("graph", "animGraph"):
                graph = component.get(graph_key)
                graph_path = _depot_value(graph).lower()
                if isinstance(graph, dict) and (
                    "paperdoll_sermo.animgraph" in graph_path
                    or "photomode_sermo.animgraph" in graph_path
                ):
                    _set_depot(graph, photo_graph)
                    graph_count += 1
            if component.get("$type") != "entAnimationSetupExtensionComponent":
                continue
            animations = component.get("animations", {}).get("gameplay")
            if not isinstance(animations, list):
                continue
            existing = {_depot_value(entry.get("animSet", {})).lower() for entry in animations}
            for depot in [base_facial, *extra_facial]:
                if depot.lower() not in existing:
                    animations.append(_anim_entry(depot))
            extension_count += 1
    if graph_count == 0:
        raise NpvError("Photo Mode app has no face-rig animation graph to replace.")
    if extension_count == 0:
        raise NpvError("Photo Mode app has no facial animation setup component.")


def _photo_component(mod_id: str) -> dict:
    component_id = str(int(hashlib.sha256(mod_id.encode()).hexdigest()[:15], 16))
    return {
        "$type": "PhotoModePlayerEntityComponent",
        "id": component_id,
        "isReplicable": 0,
        "name": {
            "$type": "CName",
            "$storage": "string",
            "$value": "PhotoModePlayerEntity",
        },
    }


def _patch_entity(data: dict, rig: str, mod_id: str, app_depot: str) -> None:
    root = data["Data"]["RootChunk"]
    appearances = root.get("appearances", [])
    if not appearances:
        raise NpvError("Photo Mode entity has no appearance reference.")
    for appearance in appearances:
        _set_depot(appearance["appearanceResource"], app_depot)

    components = root.setdefault("components", [])
    if not any(c.get("$type") == "PhotoModePlayerEntityComponent" for c in components):
        components.append(_photo_component(mod_id))

    root_component = next(
        (
            component
            for component in components
            if component.get("$type") == "entAnimatedComponent"
            and _component_name(component) == "root"
        ),
        None,
    )
    if root_component is None:
        raise NpvError("Photo Mode entity has no root animated component.")
    gameplay = root_component.get("animations", {}).get("gameplay")
    if not isinstance(gameplay, list):
        raise NpvError("Photo Mode entity root has no gameplay animation list.")

    prefix = "female" if rig == "pwa" else "male"
    pose_sets = [
        f"base\\animations\\ui\\photomode\\photomode__{prefix}__idle.anims",
        f"base\\animations\\ui\\photomode\\photomode__{prefix}__action.anims",
        (
            "base\\animations\\ui\\photomode\\photomode__v_female__natural.anims"
            if rig == "pwa"
            else "base\\animations\\ui\\photomode\\photomode__v__natural.anims"
        ),
    ]
    existing = {_depot_value(entry.get("animSet", {})).lower() for entry in gameplay}
    for depot in pose_sets:
        if depot.lower() not in existing:
            gameplay.append(_anim_entry(depot))

    required_setup_names = {
        "Character Entity Animation Setup",
        "Special Locomotion Setup",
        "Ultimate Edition Animsets",
    }
    actual_names = {_component_name(component) for component in components}
    missing = sorted(required_setup_names - actual_names)
    if missing:
        raise NpvError(f"Photo Mode donor is missing required animation setup(s): {missing}")


def _round_trip_patch(wk: WolvenKit, binary: Path, patcher) -> None:
    with tempfile.TemporaryDirectory(prefix="npv-photomode-json-") as temp:
        temp_dir = Path(temp)
        json_path = wk.serialize(binary, dest=temp_dir)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        patcher(data)
        json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        wk.deserialize(json_path)
        cooked = json_path.with_suffix("")
        if not cooked.is_file():
            candidates = [p for p in temp_dir.rglob(binary.name) if p.is_file()]
            if not candidates:
                raise WolvenKitError(
                    f"Photo Mode conversion produced no {binary.name}",
                    operation="photomode",
                )
            cooked = candidates[0]
        shutil.copy2(cooked, binary)


def _round_trip_patch_many(wk: WolvenKit, patches: dict[Path, object]) -> None:
    with tempfile.TemporaryDirectory(prefix="npv-photomode-json-") as temp:
        temp_dir = Path(temp)
        json_dir = temp_dir / "json"
        json_paths = wk.serialize_many(list(patches), dest=json_dir)
        for binary, patcher in patches.items():
            json_path = json_paths[binary.name]
            data = json.loads(json_path.read_text(encoding="utf-8"))
            patcher(data)
            json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        wk.deserialize(json_dir)
        for binary in patches:
            json_path = json_paths[binary.name]
            cooked = json_path.with_suffix("")
            if not cooked.is_file():
                candidates = [p for p in json_dir.rglob(binary.name) if p.is_file()]
                if not candidates:
                    raise WolvenKitError(
                        f"Photo Mode conversion produced no {binary.name}",
                        operation="photomode",
                    )
                cooked = candidates[0]
            shutil.copy2(cooked, binary)


def author_photomode_assets(
    wk: WolvenKit,
    *,
    source_dir: Path,
    mod_id: str,
    npv_name: str,
    body_rig: str,
    thumbnail: PhotoModeThumbnail,
    artifact_cache: ArtifactCache | None = None,
) -> PhotoModeArtifacts:
    if body_rig not in {"pwa", "pma"}:
        raise NpvError(f"Unsupported Photo Mode body rig: {body_rig}")
    artifacts = artifact_paths(source_dir, mod_id)
    normal_dir = source_dir / "base" / "npv-build" / mod_id
    normal_ent = normal_dir / f"{mod_id}.ent"
    normal_app = normal_dir / f"{mod_id}.app"
    if not normal_ent.is_file() or not normal_app.is_file():
        raise WolvenKitError(
            "Normal NPV entity/app must exist before Photo Mode authoring.",
            operation="photomode",
        )

    artifacts.entity.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(normal_ent, artifacts.entity)
    shutil.copy2(normal_app, artifacts.app)
    _round_trip_patch_many(
        wk,
        {
            artifacts.app: lambda data: _patch_app(data, body_rig),
            artifacts.entity: lambda data: _patch_entity(
                data, body_rig, mod_id, artifacts.app_depot
            ),
        },
    )

    _normalize_thumbnail(thumbnail, artifacts, artifact_cache=artifact_cache)
    _run_helper(
        [
            "author-metadata",
            "--dds",
            str(artifacts.dds),
            "--xbm",
            str(artifacts.xbm),
            "--inkatlas",
            str(artifacts.atlas),
            "--xbm-depot",
            artifacts.xbm_depot,
            "--part",
            "custom_icon",
            "--localization",
            str(artifacts.localization),
            "--key",
            artifacts.loc_key,
            "--value",
            npv_name,
        ]
    )
    # Source files are useful in build metadata but must not be packed.
    artifacts.preview.unlink(missing_ok=True)
    artifacts.dds.unlink(missing_ok=True)

    required = [
        artifacts.entity,
        artifacts.app,
        artifacts.xbm,
        artifacts.atlas,
        artifacts.localization,
    ]
    missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise NpvError(f"Photo Mode authoring did not produce: {missing}")
    logger.info("[Photo Mode] Authored entity, app, icon, atlas, and localization.")
    return artifacts


def write_photomode_registration(
    *,
    mod_id: str,
    npv_name: str,
    body_rig: str,
    output_dir: Path,
    artifacts: PhotoModeArtifacts,
) -> dict[str, Path]:
    record_id = mod_id[0].upper() + mod_id[1:]
    record = f"Character.{record_id}_Photomode_Puppet"
    visual_tag = "\n  visualTags: [ !append ManAverage ]" if body_rig == "pma" else ""
    tweak_text = (
        f"{record}:\n"
        "  $type: Character\n"
        f"  entityTemplatePath: {artifacts.entity_depot}\n"
        f"  displayName: LocKey#{artifacts.loc_key}\n"
        "  persistentName: PhotomodePuppet\n"
        "  attachmentSlots: [ AttachmentSlots.WeaponRight, AttachmentSlots.WeaponLeft ]"
        f"{visual_tag}\n\n"
        f"{record}.icon:\n"
        "  $type: PhotoModeSticker\n"
        f"  atlasName: {artifacts.atlas_depot}\n"
        "  imagePartName: custom_icon\n"
    )
    tweak_dir = output_dir / "r6" / "tweaks" / "npv_build"
    tweak_dir.mkdir(parents=True, exist_ok=True)
    tweak_path = tweak_dir / f"{mod_id}_photomode.yaml"
    tweak_path.write_text(tweak_text, encoding="utf-8")

    scope = "photomode_wa.ent" if body_rig == "pwa" else "photomode_ma.ent"
    xl_text = (
        "localization:\n"
        "  onscreens:\n"
        f"    en-us: {artifacts.localization_depot}\n"
        "resource:\n"
        "  scope:\n"
        f"    {scope}:\n"
        f"      - {artifacts.entity_depot}\n"
    )
    xl_dir = output_dir / "archive" / "pc" / "mod"
    xl_dir.mkdir(parents=True, exist_ok=True)
    xl_path = xl_dir / f"{mod_id}.archive.xl"
    xl_path.write_text(xl_text, encoding="utf-8")
    return {"tweak": tweak_path, "xl": xl_path}
