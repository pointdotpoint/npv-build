from npv_build.orchestrator import write_photomode_files


def test_write_photomode_files_emits_tweak_and_xl(tmp_path):
    out = write_photomode_files("myv_abc123", "My V", "pwa", tmp_path)

    tweak = out["tweak"]
    xl = out["xl"]
    assert tweak.exists()
    assert xl.exists()

    text = tweak.read_text(encoding="utf-8")
    # Verbatim record shape from Global Constraints.
    assert "Character.myv_abc123_Photomode_Puppet:" in text
    assert "$type: Character" in text
    assert "persistentName: PhotomodePuppet" in text
    assert "AttachmentSlots.WeaponRight" in text
    assert "AttachmentSlots.WeaponLeft" in text
    assert 'displayName: "My V"' in text
    # Default (fallback) entityTemplatePath points at the NPV .ent, backslashes preserved.
    assert r"entityTemplatePath: base\npv-build\myv_abc123\myv_abc123.ent" in text


def test_write_photomode_files_respects_explicit_ent_path(tmp_path):
    out = write_photomode_files(
        "myv_abc123", "My V", "pwa", tmp_path,
        ent_depot_path=r"base\npv-build\myv_abc123\myv_abc123_photomode.ent",
    )
    text = out["tweak"].read_text(encoding="utf-8")
    assert r"entityTemplatePath: base\npv-build\myv_abc123\myv_abc123_photomode.ent" in text


def test_write_photomode_files_escapes_display_name_quotes(tmp_path):
    out = write_photomode_files('myv_abc123', 'V "The Merc"', "pwa", tmp_path)
    text = out["tweak"].read_text(encoding="utf-8")
    assert r'displayName: "V \"The Merc\""' in text
