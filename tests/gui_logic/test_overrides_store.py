from npv_build.gui_logic import overrides_store


def test_roundtrip_and_delete(monkeypatch, tmp_path):
    monkeypatch.setattr(overrides_store, "_overrides_dir", lambda: tmp_path)
    overrides_store.save_overrides("/saves/a/sav.dat", {"skin_tone": "03_ca_medium"})
    assert overrides_store.load_overrides("/saves/a/sav.dat") == {
        "skin_tone": "03_ca_medium"}
    # distinct saves don't collide
    assert overrides_store.load_overrides("/saves/b/sav.dat") == {}
    # empty dict removes the file
    overrides_store.save_overrides("/saves/a/sav.dat", {})
    assert overrides_store.load_overrides("/saves/a/sav.dat") == {}
    assert list(tmp_path.iterdir()) == []


def test_corrupt_file_reads_as_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(overrides_store, "_overrides_dir", lambda: tmp_path)
    p = overrides_store.store_path("/saves/a/sav.dat")
    p.write_text("{not json")
    assert overrides_store.load_overrides("/saves/a/sav.dat") == {}
