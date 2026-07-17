import json

import pytest

from npv_build.core.errors import NpvError
from npv_build.core.multi_appearance import append_amm_appearance, merge_appearance_json


def test_merge_appearance_adds_entry():
    base = {"Data": {"RootChunk": {"appearances": [{"Data": {"name": "app_a"}}]}}}
    new = {"Data": {"RootChunk": {"appearances": [{"Data": {"name": "app_b"}}]}}}
    merged = merge_appearance_json(base, new, "app_b")
    names = [a["Data"]["name"] for a in merged["Data"]["RootChunk"]["appearances"]]
    assert names == ["app_a", "app_b"]


def test_merge_rejects_name_collision():
    base = {"Data": {"RootChunk": {"appearances": [{"Data": {"name": "dup"}}]}}}
    new = {"Data": {"RootChunk": {"appearances": [{"Data": {"name": "dup"}}]}}}
    with pytest.raises(NpvError):
        merge_appearance_json(base, new, "dup")


def test_merge_raises_when_named_appearance_missing_from_new():
    base = {"Data": {"RootChunk": {"appearances": [{"Data": {"name": "app_a"}}]}}}
    new = {"Data": {"RootChunk": {"appearances": [{"Data": {"name": "app_b"}}]}}}
    with pytest.raises(NpvError):
        merge_appearance_json(base, new, "not_present")


def test_merge_does_not_mutate_inputs():
    base = {"Data": {"RootChunk": {"appearances": [{"Data": {"name": "app_a"}}]}}}
    new = {"Data": {"RootChunk": {"appearances": [{"Data": {"name": "app_b"}}]}}}
    base_copy = json.loads(json.dumps(base))
    new_copy = json.loads(json.dumps(new))
    merge_appearance_json(base, new, "app_b")
    assert base == base_copy
    assert new == new_copy


def test_append_amm_appearance(tmp_path):
    lua = tmp_path / "x.lua"
    lua.write_text('return {\n  appearances = {\n    "first"\n  }\n}\n', encoding="utf-8")
    append_amm_appearance(lua, "second")
    text = lua.read_text(encoding="utf-8")
    assert '"first"' in text and '"second"' in text


def test_append_amm_appearance_is_idempotent(tmp_path):
    lua = tmp_path / "x.lua"
    lua.write_text('return {\n  appearances = {\n    "first"\n  }\n}\n', encoding="utf-8")
    append_amm_appearance(lua, "second")
    append_amm_appearance(lua, "second")
    text = lua.read_text(encoding="utf-8")
    assert text.count('"second"') == 1
