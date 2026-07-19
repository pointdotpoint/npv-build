"""Tests for save_format header probing."""

import pytest

from npv_build.save_format import SaveContainer, SaveFormatError, probe_save_version


def test_probe_matches_full_parse(synth_save_2310):
    probed = probe_save_version(synth_save_2310)
    full = SaveContainer(synth_save_2310.read_bytes()).version
    assert probed == full
    assert probed[1] == 2310


def test_probe_reads_header_only(make_synth_save):
    # Probe must not require the full file: truncate everything after the
    # header region and it still reads the version tuple.
    path = make_synth_save(build=2310)
    data = path.read_bytes()
    path.write_bytes(data[:64])
    assert probe_save_version(path)[1] == 2310


def test_probe_bad_magic_raises(tmp_path):
    p = tmp_path / "sav.dat"
    p.write_bytes(b"NOPE" + b"\x00" * 60)
    with pytest.raises(SaveFormatError):
        probe_save_version(p)


def test_probe_truncated_garbage_raises(tmp_path):
    p = tmp_path / "sav.dat"
    p.write_bytes(b"\x00")
    with pytest.raises(SaveFormatError):
        probe_save_version(p)
