import pytest

from npv_build.save_probe import format_probe, probe_save


def test_probe_reports_version_and_nodes(synth_save_2310):
    info = probe_save(synth_save_2310)
    assert info["version"][1] == info["build"]
    assert info["patch"] == "2.13"
    assert info["supported"] is True
    assert info["cc_node_present"] is True
    assert info["cc_node_size"] > 0


def test_probe_unknown_build_is_reported_not_raised(make_synth_save):
    # 9999 is not a key in data/save_versions.json -> unknown build.
    save_path = make_synth_save(build=9999)
    info = probe_save(save_path)
    assert info["build"] == 9999
    assert info["patch"] is None
    assert info["supported"] is False


def test_format_probe_contains_key_facts(synth_save_2310):
    text = format_probe(probe_save(synth_save_2310))
    assert "2310" in text
    assert "v3" in text


def test_probe_bad_file_raises_save_format_error(tmp_path):
    from npv_build.core.errors import NpvError

    bad = tmp_path / "sav.dat"
    bad.write_bytes(b"not a save")
    with pytest.raises(NpvError):
        probe_save(bad)
