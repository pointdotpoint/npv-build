import pytest
from pathlib import Path
import npv_build.installer as installer


def test_auto_install_missing_all_missing(monkeypatch):
    calls = []
    
    def mock_check_dependencies(game_dir):
        # Return that everything is missing
        return {
            "wolvenkit": False,
            "blender": False,
            "npv_inject": False,
            "game_dir_valid": False
        }
        
    def mock_install_dotnet(tools_dir, progress_cb):
        calls.append("dotnet")
        
    def mock_install_wolvenkit(tools_dir, progress_cb):
        calls.append("wolvenkit")
        
    def mock_build_npv_inject(tools_dir, progress_cb):
        calls.append("npv-inject")
        
    def mock_install_blender(tools_dir, progress_cb):
        calls.append("blender")

    monkeypatch.setattr("npv_build.gui_backend.check_dependencies", mock_check_dependencies)
    monkeypatch.setattr(installer, "install_dotnet_windows", mock_install_dotnet)
    monkeypatch.setattr(installer, "install_dotnet_linux", mock_install_dotnet)
    monkeypatch.setattr(installer, "install_wolvenkit", mock_install_wolvenkit)
    monkeypatch.setattr(installer, "build_npv_inject", mock_build_npv_inject)
    monkeypatch.setattr(installer, "install_blender", mock_install_blender)
    
    # Mock get_cache_dir
    monkeypatch.setattr(installer, "get_cache_dir", lambda: Path("/tmp/mock_cache"))
    
    # Mock shutil.which to say dotnet is not installed (so it downloads it)
    monkeypatch.setattr(installer.shutil, "which", lambda cmd: None)

    # Run auto install
    installer.auto_install_missing(lambda msg, pct: None)
    
    assert "dotnet" in calls
    assert "wolvenkit" in calls
    assert "npv-inject" in calls
    assert "blender" in calls


def test_auto_install_missing_some_present(monkeypatch):
    calls = []
    
    def mock_check_dependencies(game_dir):
        # Return that WolvenKit is present, but Blender and npv-inject are missing
        return {
            "wolvenkit": True,
            "blender": False,
            "npv_inject": False,
            "game_dir_valid": False
        }
        
    def mock_install_dotnet(tools_dir, progress_cb):
        calls.append("dotnet")
        
    def mock_install_wolvenkit(tools_dir, progress_cb):
        calls.append("wolvenkit")
        
    def mock_build_npv_inject(tools_dir, progress_cb):
        calls.append("npv-inject")
        
    def mock_install_blender(tools_dir, progress_cb):
        calls.append("blender")

    monkeypatch.setattr("npv_build.gui_backend.check_dependencies", mock_check_dependencies)
    monkeypatch.setattr(installer, "install_dotnet_windows", mock_install_dotnet)
    monkeypatch.setattr(installer, "install_dotnet_linux", mock_install_dotnet)
    monkeypatch.setattr(installer, "install_wolvenkit", mock_install_wolvenkit)
    monkeypatch.setattr(installer, "build_npv_inject", mock_build_npv_inject)
    monkeypatch.setattr(installer, "install_blender", mock_install_blender)
    
    # Mock get_cache_dir
    monkeypatch.setattr(installer, "get_cache_dir", lambda: Path("/tmp/mock_cache"))
    
    # Mock shutil.which to say dotnet is available globally
    monkeypatch.setattr(installer.shutil, "which", lambda cmd: "/usr/bin/dotnet" if cmd == "dotnet" else None)

    # Run auto install
    installer.auto_install_missing(lambda msg, pct: None)
    
    # Should not download dotnet since it's available globally,
    # and should skip wolvenkit since it's present.
    # But should build npv-inject and install Blender.
    assert "dotnet" not in calls
    assert "wolvenkit" not in calls
    assert "npv-inject" in calls
    assert "blender" in calls
