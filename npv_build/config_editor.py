"""Author NPV .app and .ent files from scratch (uncooked).

NPV mods inline ALL mesh components directly in the .app appearance's
`components` array — partsValues is player-equipment-only. Using the
`AppearanceParts` visualTag enables partsValues for NPCs but breaks
the animation rig (T-pose). So we inline instead.

Each component gets inline entHardTransformBinding + entSkinningBinding
with `bindName: "root"`, which resolves against the donor NPC entity's
root entAnimatedComponent at spawn. WolvenKit cooks the inline
HandleId+Data into correct HandleRefId linkage.

Material overrides (skin tone, eye colour) are applied directly as
`meshAppearance` on each component rather than via partsOverrides.
"""

ENT_DEPOT_DIR = "base\\npv-build"
APP_DEPOT_DIR = "base\\npv-build"

# Components extracted from part-ents that are mesh-like and should be inlined
_MESH_COMPONENT_TYPES = {
    "entSkinnedMeshComponent",
    "entMorphTargetSkinnedMeshComponent",
    "entGarmentSkinnedMeshComponent",
}


def _cname(value):
    return {"$type": "CName", "$storage": "string", "$value": value}


def _resource(value, flags="Soft"):
    return {
        "DepotPath": {
            "$type": "ResourcePath",
            "$storage": "string",
            "$value": value,
        },
        "Flags": flags,
    }


def _parts_override_entry(component_name: str, mesh_appearance: str):
    return {
        "$type": "appearanceAppearancePartOverrides",
        "componentsOverrides": [
            {
                "$type": "appearancePartComponentOverrides",
                "componentName": _cname(component_name),
                "meshAppearance": _cname(mesh_appearance),
            }
        ],
        "partResource": _resource(""),
    }


def build_app_template(mod_id: str, parts_overrides: list[dict] | None = None):
    """A minimal uncooked .app with one empty appearance definition.

    Produces a skeleton appearanceAppearanceResource that the user can open in
    WolvenKit GUI to manually add mesh components. No partsValues, no
    AppearanceParts visualTag. partsOverrides are populated when runtime
    material overrides are needed (e.g. eyelash color on the eyes mesh).
    """
    appearance_name = f"{mod_id}_appearance"
    overrides = [
        _parts_override_entry(po["componentName"], po["meshAppearance"])
        for po in (parts_overrides or [])
    ]
    return {
        "Header": {
            "WolvenKitVersion": "8.18.0",
            "WKitJsonVersion": "0.0.9",
            "GameVersion": 2310,
            "DataType": "CR2W",
        },
        "Data": {
            "RootChunk": {
                "$type": "appearanceAppearanceResource",
                "appearances": [
                    {
                        "HandleId": "0",
                        "Data": {
                            "$type": "appearanceAppearanceDefinition",
                            "name": _cname(appearance_name),
                            "partsValues": [],
                            "partsOverrides": overrides,
                            "components": [],
                            "visualTags": {"$type": "redTagList", "tags": []},
                            "resolvedDependencies": [],
                            "censorFlags": 0,
                        },
                    }
                ],
                "baseEntityType": _cname("None"),
                "baseType": _cname("None"),
                "cookingPlatform": "PLATFORM_PC",
            }
        },
    }


NPC_BASE_ENT = {
    "pwa": "base\\characters\\entities\\main_npc\\judy.ent",
    "pma": "base\\characters\\entities\\main_npc\\thompson.ent",
}


def build_ent_from_donor(mod_id: str, donor_ent_json: dict, body_rig: str = "pwa"):
    """Build the NPV .ent by taking a REAL NPC's cooked entity template (with
    full animation rig, AI, locomotion — 101 components) and replacing only the
    top-level fields that survive WolvenKit's deserialize round-trip:

    - Header.Name → our mod-scoped depot path
    - appearances[] → single entry pointing at our .app
    - defaultAppearance → our appearance name

    All cooked buffer data (animation controllers, rig, skinning, AI, etc.)
    passes through unchanged. This gives the NPV a fully animated puppet.
    """
    appearance_name = f"{mod_id}_appearance"
    app_depot = f"{APP_DEPOT_DIR}\\{mod_id}\\{mod_id}.app"

    donor_ent_json["Header"]["Name"] = f"{ENT_DEPOT_DIR}\\{mod_id}\\{mod_id}.ent"

    rc = donor_ent_json["Data"]["RootChunk"]
    rc["appearances"] = [
        {
            "$type": "entTemplateAppearance",
            "appearanceName": _cname(appearance_name),
            "appearanceResource": _resource(app_depot),
            "name": _cname(appearance_name),
        }
    ]
    rc["defaultAppearance"] = _cname(appearance_name)

    return donor_ent_json
