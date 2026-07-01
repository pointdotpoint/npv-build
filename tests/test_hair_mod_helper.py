import pytest
import zipfile
import py7zr
import shutil
import subprocess
from pathlib import Path
from npv_build.hair_mod_helper import derive_hair_name, install_hair_mod

def test_derive_hair_name():
    assert derive_hair_name("fhair_zara.archive") == "zara"
    assert derive_hair_name("mhair_buzz.archive") == "buzz"
    assert derive_hair_name("fhair_miyavi_twistup_soft_mod.archive") == "miyavi_twistup_soft"
    assert derive_hair_name("cool_hair.archive") == "cool"
    assert derive_hair_name("fhair_edie_hair_v1.0.archive") == "edie"
    assert derive_hair_name("fhair_long_wavy_hair_mod_v2.archive") == "long_wavy"

def test_install_hair_mod_archive(tmp_path):
    # Set up source directories
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    game_dir = tmp_path / "game"
    
    archive_file = src_dir / "fhair_zara.archive"
    archive_file.write_text("dummy archive content")
    
    xl_file = src_dir / "fhair_zara.xl"
    xl_file.write_text("dummy xl content")
    
    # Run installer
    hair_name, installed = install_hair_mod(archive_file, game_dir)
    
    assert hair_name == "zara"
    dest_mod_dir = game_dir / "archive" / "pc" / "mod"
    assert (dest_mod_dir / "fhair_zara.archive").exists()
    assert (dest_mod_dir / "fhair_zara.xl").exists()
    assert dest_mod_dir / "fhair_zara.archive" in installed
    assert dest_mod_dir / "fhair_zara.xl" in installed

def test_install_hair_mod_zip(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    game_dir = tmp_path / "game"
    
    zip_path = src_dir / "hair_mod.zip"
    
    # Create a real zip file with nested structure
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("archive/pc/mod/fhair_zara.archive", "dummy zip archive content")
        zf.writestr("archive/pc/mod/fhair_zara.xl", "dummy zip xl content")
        zf.writestr("README.txt", "should not extract")
        
    hair_name, installed = install_hair_mod(zip_path, game_dir)
    
    assert hair_name == "zara"
    dest_mod_dir = game_dir / "archive" / "pc" / "mod"
    assert (dest_mod_dir / "fhair_zara.archive").exists()
    assert (dest_mod_dir / "fhair_zara.xl").exists()
    assert not (dest_mod_dir / "README.txt").exists()
    assert len(installed) == 2

def test_install_hair_mod_7z(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    game_dir = tmp_path / "game"
    
    sevenz_path = src_dir / "hair_mod.7z"
    
    # Create a real 7z file
    with py7zr.SevenZipFile(sevenz_path, 'w') as sz:
        sz.writestr("dummy 7z archive content", "archive/pc/mod/fhair_zara.archive")
        sz.writestr("dummy 7z xl content", "archive/pc/mod/fhair_zara.xl")
        sz.writestr("should not extract", "README.txt")
        
    hair_name, installed = install_hair_mod(sevenz_path, game_dir)
    
    assert hair_name == "zara"
    dest_mod_dir = game_dir / "archive" / "pc" / "mod"
    assert (dest_mod_dir / "fhair_zara.archive").exists()
    assert (dest_mod_dir / "fhair_zara.xl").exists()
    assert not (dest_mod_dir / "README.txt").exists()
    assert len(installed) == 2

def test_install_hair_mod_rar(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    game_dir = tmp_path / "game"
    
    rar_path = src_dir / "hair_mod.rar"
    rar_path.write_text("fake rar data")
    
    # Mock shutil.which to ensure 'unrar' is found
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/unrar" if cmd == "unrar" else None)
    
    # Mock subprocess.run to simulate unrar writing files to the extraction dir
    def mock_run(args, **kwargs):
        # The last argument is the extraction path
        extract_path = Path(args[-1])
        # Create mock extracted structure
        arch_dir = extract_path / "archive" / "pc" / "mod"
        arch_dir.mkdir(parents=True, exist_ok=True)
        (arch_dir / "fhair_zara.archive").write_text("mock rar archive")
        (arch_dir / "fhair_zara.xl").write_text("mock rar xl")
        (extract_path / "readme.txt").write_text("should be ignored")
        return subprocess.CompletedProcess(args, 0, stdout="success", stderr="")
        
    monkeypatch.setattr(subprocess, "run", mock_run)
    
    hair_name, installed = install_hair_mod(rar_path, game_dir)
    
    assert hair_name == "zara"
    dest_mod_dir = game_dir / "archive" / "pc" / "mod"
    assert (dest_mod_dir / "fhair_zara.archive").exists()
    assert (dest_mod_dir / "fhair_zara.xl").exists()
    assert not (dest_mod_dir / "readme.txt").exists()
    assert len(installed) == 2

def test_install_hair_mod_unsupported(tmp_path):
    game_dir = tmp_path / "game"
    bad_file = tmp_path / "cool_hair.txt"
    bad_file.write_text("test")
    
    with pytest.raises(ValueError, match="Unsupported mod file format"):
        install_hair_mod(bad_file, game_dir)

def test_install_hair_no_archive_in_zip(tmp_path):
    game_dir = tmp_path / "game"
    zip_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("README.txt", "no archives here")
        
    with pytest.raises(ValueError, match="No .archive file found inside the mod package"):
        install_hair_mod(zip_path, game_dir)
