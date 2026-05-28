import pytest
from npv_build.orchestrator import compute_mod_id

def test_compute_mod_id_determinism():
    cc_settings = {"patch": "2.13", "body_rig": "pwa"}
    id1 = compute_mod_id("My V", cc_settings)
    id2 = compute_mod_id("My V", cc_settings)
    assert id1 == id2
    assert id1.startswith("my_v_")
    
    # Change setting
    cc_settings["body_rig"] = "pma"
    id3 = compute_mod_id("My V", cc_settings)
    assert id1 != id3
