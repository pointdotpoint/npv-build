import json
from npv_build.config_editor import build_app_template


def test_template_has_empty_components_and_no_parts():
    result = build_app_template("my_npv_abc123")
    app_def = result["Data"]["RootChunk"]["appearances"][0]["Data"]
    assert app_def["name"]["$value"] == "my_npv_abc123_appearance"
    assert app_def["components"] == []
    assert app_def["partsValues"] == []
    assert app_def["partsOverrides"] == []
    tags = [t["$value"] for t in app_def["visualTags"]["tags"]]
    assert "AppearanceParts" not in tags


def test_template_has_correct_resource_type():
    result = build_app_template("x")
    assert result["Data"]["RootChunk"]["$type"] == "appearanceAppearanceResource"
    assert result["Header"]["WolvenKitVersion"] == "8.18.0"
