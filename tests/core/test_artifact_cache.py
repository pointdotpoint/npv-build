from __future__ import annotations

from pathlib import Path

import pytest

from npv_build.core.artifact_cache import (
    ArchiveFingerprint,
    ArtifactCache,
    ToolFingerprint,
)


def test_json_cache_round_trip_uses_canonical_content_address(tmp_path: Path) -> None:
    cache = ArtifactCache(tmp_path)
    key_a = {
        "archive": ArchiveFingerprint("/game/base.archive", 100, 200),
        "tool": ToolFingerprint("/tools/cp77tools", 300, 400),
        "resource": "head.ent",
    }
    key_b = {
        "resource": "head.ent",
        "tool": ToolFingerprint("/tools/cp77tools", 300, 400),
        "archive": ArchiveFingerprint("/game/base.archive", 100, 200),
    }

    cache.save_json("uncook-json-v1", key_a, {"Data": {"ok": True}})

    assert cache.path_for("uncook-json-v1", key_a, ".json") == cache.path_for(
        "uncook-json-v1", key_b, ".json"
    )
    assert cache.load_json("uncook-json-v1", key_b) == {"Data": {"ok": True}}


def test_corrupt_or_non_dict_cache_entry_is_removed_as_a_miss(tmp_path: Path) -> None:
    cache = ArtifactCache(tmp_path)
    key = {"resource": "head.ent"}
    path = cache.path_for("uncook-json-v1", key, ".json")
    path.parent.mkdir(parents=True)
    path.write_text("[]", encoding="utf-8")

    assert cache.load_json("uncook-json-v1", key) is None
    assert not path.exists()


@pytest.mark.parametrize("namespace", ["../escape", "/absolute", "a/b", ""])
def test_cache_namespace_cannot_escape_root(tmp_path: Path, namespace: str) -> None:
    cache = ArtifactCache(tmp_path)
    with pytest.raises(ValueError):
        cache.path_for(namespace, {"key": "value"}, ".json")
