import json

import pytest
from PIL import Image

from npv_build.core.artifact_cache import ArtifactCache
from npv_build.core.errors import NpvError
from npv_build.photomode import (
    _normalize_thumbnail,
    _patch_app,
    _patch_entity,
    artifact_paths,
    author_photomode_assets,
    runtime_dependency_status,
    validate_thumbnail,
    write_photomode_registration,
)


def _ref(path):
    return {
        "DepotPath": {
            "$type": "ResourcePath",
            "$storage": "string",
            "$value": path,
        },
        "Flags": "Default",
    }


def test_thumbnail_validation_accepts_static_image_and_hashes_it(tmp_path):
    path = tmp_path / "portrait.png"
    Image.new("RGBA", (640, 360), (200, 20, 100, 255)).save(path)
    result = validate_thumbnail(path)
    assert result.width == 640
    assert result.height == 360
    assert result.format == "PNG"
    assert len(result.sha256) == 64


def test_thumbnail_validation_rejects_small_image(tmp_path):
    path = tmp_path / "small.png"
    Image.new("RGB", (199, 200)).save(path)
    with pytest.raises(NpvError, match="too small"):
        validate_thumbnail(path)


def test_normalized_thumbnail_files_are_reused_from_artifact_cache(tmp_path):
    source = tmp_path / "portrait.png"
    Image.new("RGB", (640, 360), "magenta").save(source)
    thumbnail = validate_thumbnail(source)
    artifacts = artifact_paths(tmp_path / "source", "cache_test")
    cache = ArtifactCache(tmp_path / "cache")

    _normalize_thumbnail(thumbnail, artifacts, artifact_cache=cache)
    expected_preview = artifacts.preview.read_bytes()
    expected_dds = artifacts.dds.read_bytes()
    artifacts.preview.unlink()
    artifacts.dds.unlink()
    source.unlink()

    _normalize_thumbnail(thumbnail, artifacts, artifact_cache=cache)

    assert artifacts.preview.read_bytes() == expected_preview
    assert artifacts.dds.read_bytes() == expected_dds


def test_changed_thumbnail_misses_and_corrupt_dds_regenerates(tmp_path):
    cache_root = tmp_path / "cache"
    cache = ArtifactCache(cache_root)
    for name, color in (("first", "red"), ("second", "blue")):
        source = tmp_path / f"{name}.png"
        Image.new("RGB", (300, 300), color).save(source)
        _normalize_thumbnail(
            validate_thumbnail(source),
            artifact_paths(tmp_path / name, name),
            artifact_cache=cache,
        )
    assert len(list(cache_root.rglob("*.png"))) == 2
    assert len(list(cache_root.rglob("*.dds"))) == 2

    cached_dds = list(cache_root.rglob("*.dds"))
    for dds in cached_dds:
        dds.write_bytes(b"")
    first_source = tmp_path / "first.png"
    first_artifacts = artifact_paths(tmp_path / "regenerated", "first")
    _normalize_thumbnail(
        validate_thumbnail(first_source),
        first_artifacts,
        artifact_cache=cache,
    )
    assert first_artifacts.dds.stat().st_size > 128
    assert sum(dds.stat().st_size > 128 for dds in cached_dds) == 1


def test_photomode_authoring_uses_one_conversion_pair_and_one_helper_start(
    monkeypatch, tmp_path
):
    source_dir = tmp_path / "source"
    mod_id = "photo_test"
    normal_dir = source_dir / "base" / "npv-build" / mod_id
    normal_dir.mkdir(parents=True)
    (normal_dir / f"{mod_id}.app").write_bytes(b"app")
    (normal_dir / f"{mod_id}.ent").write_bytes(b"ent")
    portrait = tmp_path / "portrait.png"
    Image.new("RGB", (300, 300), "cyan").save(portrait)
    thumbnail = validate_thumbnail(portrait)
    conversions = []
    helpers = []

    monkeypatch.setattr(
        "npv_build.photomode._round_trip_patch",
        lambda *_args, **_kwargs: conversions.append("single"),
    )
    monkeypatch.setattr(
        "npv_build.photomode._round_trip_patch_many",
        lambda *_args, **_kwargs: conversions.append("batch"),
        raising=False,
    )

    def fake_helper(args):
        helpers.append(args)
        values = dict(zip(args[1::2], args[2::2], strict=True))
        for option in ("--xbm", "--inkatlas", "--localization"):
            path = values[option]
            from pathlib import Path

            Path(path).write_bytes(option.encode())

    monkeypatch.setattr("npv_build.photomode._run_helper", fake_helper)

    author_photomode_assets(
        object(),
        source_dir=source_dir,
        mod_id=mod_id,
        npv_name="Photo Test",
        body_rig="pwa",
        thumbnail=thumbnail,
    )

    assert conversions == ["batch"]
    assert len(helpers) == 1
    assert helpers[0][0] == "author-metadata"


def test_patch_entity_adds_photo_component_pose_sets_and_app_link():
    data = {
        "Data": {
            "RootChunk": {
                "appearances": [{"appearanceResource": _ref("old.app")}],
                "components": [
                    {
                        "$type": "entAnimatedComponent",
                        "name": {"$value": "root"},
                        "animations": {"gameplay": [], "cinematics": []},
                    },
                    *[
                        {
                            "$type": "entAnimationSetupExtensionComponent",
                            "name": {"$value": name},
                        }
                        for name in (
                            "Character Entity Animation Setup",
                            "Special Locomotion Setup",
                            "Ultimate Edition Animsets",
                        )
                    ],
                ],
            }
        }
    }
    _patch_entity(data, "pwa", "test_id", "base\\test\\photo.app")
    root = data["Data"]["RootChunk"]
    assert root["appearances"][0]["appearanceResource"]["DepotPath"]["$value"].endswith(
        "photo.app"
    )
    assert sum(
        component["$type"] == "PhotoModePlayerEntityComponent"
        for component in root["components"]
    ) == 1
    encoded = json.dumps(root)
    assert "photomode__female__idle.anims" in encoded
    assert "photomode__female__action.anims" in encoded


def test_patch_app_switches_graph_and_adds_facial_sets():
    component = {
        "$type": "entAnimationSetupExtensionComponent",
        "name": {"$value": "face_rig"},
        "graph": _ref(
            "base\\animations\\facial\\_facial_graphs\\"
            "player_woman_paperdoll_sermo.animgraph"
        ),
        "animations": {"gameplay": [], "cinematics": []},
    }
    data = {
        "Data": {
            "RootChunk": {
                "appearances": [{"Data": {"components": [component]}}],
            }
        }
    }
    _patch_app(data, "pwa")
    assert "player_woman_photomode_sermo" in component["graph"]["DepotPath"]["$value"]
    encoded = json.dumps(component["animations"])
    assert "photomode_female_facial.anims" in encoded
    assert "xbae_pm_facials_15.anims" in encoded


def test_registration_has_icon_loc_key_and_rig_scope(tmp_path):
    artifacts = artifact_paths(tmp_path / "source" / "archive", "my_v_abc")
    paths = write_photomode_registration(
        mod_id="my_v_abc",
        npv_name="My V",
        body_rig="pma",
        output_dir=tmp_path,
        artifacts=artifacts,
    )
    tweak = paths["tweak"].read_text()
    xl = paths["xl"].read_text()
    assert "Character.My_v_abc_Photomode_Puppet.icon:" in tweak
    assert "LocKey#npv_build_my_v_abc_photomode_name" in tweak
    assert "visualTags: [ !append ManAverage ]" in tweak
    assert "imagePartName: custom_icon" in tweak
    assert "photomode_ma.ent:" in xl
    assert artifacts.localization_depot in xl


def test_runtime_dependency_status_detects_installed_files(tmp_path):
    for plugin in ("ArchiveXL", "TweakXL", "PhotoModeEx", "Codeware"):
        folder = tmp_path / "red4ext" / "plugins" / plugin
        folder.mkdir(parents=True, exist_ok=True)
        dll = "PhotoModeEx.dll" if plugin == "PhotoModeEx" else f"{plugin}.dll"
        (folder / dll).write_bytes(b"x")
    mod_dir = tmp_path / "archive" / "pc" / "mod"
    mod_dir.mkdir(parents=True)
    (mod_dir / "Photomode_NPCs_Extended_xBaebsae.archive").write_bytes(b"x")
    scc = tmp_path / "engine" / "tools" / "scc"
    scc.parent.mkdir(parents=True)
    scc.write_bytes(b"x")
    assert all(runtime_dependency_status(tmp_path).values())
