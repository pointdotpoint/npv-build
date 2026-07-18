import zipfile

from npv_build.orchestrator import write_photomode_files


def test_photomode_files_included_in_package(tmp_path):
    from npv_build.core.pipeline import package_mod

    mod_id = "myv_abc123"
    # Minimal mod tree: an archive + bin dir (what package_mod already zips)
    # plus the photomode files.
    (tmp_path / "archive" / "pc" / "mod").mkdir(parents=True)
    (tmp_path / "archive" / "pc" / "mod" / f"{mod_id}.archive").write_bytes(b"\x00")
    write_photomode_files(mod_id, "My V", "pwa", tmp_path)

    zip_path = package_mod(tmp_path, mod_id)

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert any(n.endswith(f"{mod_id}_photomode.yaml") for n in names)
    assert any(n.endswith(f"{mod_id}_photomode.archive.xl") for n in names)


def test_readme_documents_photomode_dependencies(tmp_path):
    from npv_build.project_writer import write_readme

    out = tmp_path / "README_GUI_STEPS.md"
    write_readme("myv_abc123", "myv_abc123_appearance", out)
    text = out.read_text(encoding="utf-8")
    assert "Photo Mode" in text
    assert "Photomode NPCs Extended" in text
    assert "PhotoMode-EX" in text
