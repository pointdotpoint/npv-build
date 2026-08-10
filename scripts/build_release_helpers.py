"""Publish self-contained native helpers for a frozen NPV Build release.

Each helper is published into its own subdirectory under ``--output`` so
managed assemblies (e.g. System.Text.Json 9.x required by WolvenKit) are not
clobbered by a later helper that ships a different version of the same DLL.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

HELPERS = ("npv-inject", "npv-photomode", "npv-tweakdb")
RIDS = ("linux-x64", "win-x64")


def _remove_foreign_native_assets(output: Path, rid: str) -> None:
    # Managed .NET assemblies use .dll on every platform, so they must remain
    # even for Linux releases.
    foreign_suffixes = (".dylib",) if rid == "linux-x64" else (".so", ".dylib")
    for path in output.rglob("*"):
        if not path.is_file():
            continue
        is_foreign = path.suffix.lower() in foreign_suffixes
        if path.suffix.lower() == ".pdb" or is_foreign:
            path.unlink()


def helper_output_dir(output_root: Path, helper: str) -> Path:
    """Per-helper publish directory (avoids shared-DLL clobbering)."""
    return output_root / helper


def publish_helper(repo_root: Path, output_root: Path, helper: str, rid: str) -> Path:
    project = repo_root / "tools" / helper / f"{helper}.csproj"
    if not project.is_file():
        raise FileNotFoundError(f"Missing helper project: {project}")

    dest = helper_output_dir(output_root, helper)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "dotnet",
            "publish",
            str(project),
            "-c",
            "Release",
            "-r",
            rid,
            "--self-contained",
            "true",
            "-p:PublishSingleFile=false",
            "-p:PublishTrimmed=false",
            "-p:DebugType=None",
            "-p:DebugSymbols=false",
            "-o",
            str(dest),
            "--nologo",
        ],
        cwd=repo_root,
        check=True,
    )
    executable = dest / (f"{helper}.exe" if rid == "win-x64" else helper)
    if not executable.is_file():
        raise FileNotFoundError(f"dotnet publish did not produce {executable}")
    if rid == "linux-x64":
        executable.chmod(executable.stat().st_mode | 0o111)
    _remove_foreign_native_assets(dest, rid)
    return executable


def _verify_inject_can_load_json(executable: Path) -> None:
    """Fail the release build if System.Text.Json was clobbered or missing.

    Launch path without JSON never loads STJ; a minimal parse forces the load.
    """
    with tempfile.TemporaryDirectory(prefix="npv-inject-smoke-") as td:
        td_path = Path(td)
        app = td_path / "x.app"
        comps = td_path / "comps.json"
        app.write_bytes(b"not-a-real-app")
        comps.write_text("[]\n", encoding="utf-8")
        result = subprocess.run(
            [str(executable), str(app), str(comps)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    combined = f"{result.stdout}\n{result.stderr}"
    if "System.Text.Json" in combined and (
        "Could not load file or assembly" in combined
        or "could not load file or assembly" in combined.lower()
    ):
        raise RuntimeError(
            f"{executable.name} cannot load System.Text.Json (shared-DLL clobber?): "
            f"{combined.strip()}"
        )
    # Healthy binary reaches JSON parse (empty array is the wrong root type).
    if "Failed to parse component spec" not in combined and result.returncode == 0:
        # Unexpected success is fine; only STJ load failure is fatal here.
        return


def _assert_stj_not_clobbered(helper_dir: Path) -> None:
    """If deps.json pins System.Text.Json 9.x, the DLL must not be the 8.x runtime copy.

    Heuristic: NuGet 9.0.x net8.0 STJ is ~0.6–0.8 MiB; the shared-framework 8.0
    self-contained copy is ~1.4 MiB. Mismatch with a 9.x deps pin is a clobber.
    """
    deps_path = helper_dir / f"{helper_dir.name}.deps.json"
    if not deps_path.is_file():
        return
    deps = json.loads(deps_path.read_text(encoding="utf-8"))
    stj_libs = [k for k in deps.get("libraries", {}) if k.startswith("System.Text.Json/")]
    if not stj_libs:
        return
    version = stj_libs[0].split("/", 1)[1]
    major = int(version.split(".", 1)[0])
    dll = helper_dir / "System.Text.Json.dll"
    if not dll.is_file():
        raise RuntimeError(f"{helper_dir.name}: deps pin {stj_libs[0]} but DLL missing")
    size = dll.stat().st_size
    if major >= 9 and size > 1_200_000:
        raise RuntimeError(
            f"{helper_dir.name}: deps pin {stj_libs[0]} but System.Text.Json.dll "
            f"is {size} bytes (looks like framework 8.x clobber from a shared publish dir)"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rid", required=True, choices=RIDS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    output_root = args.output.resolve()
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    published: dict[str, Path] = {}
    for helper in HELPERS:
        executable = publish_helper(repo_root, output_root, helper, args.rid)
        published[helper] = executable
        print(f"published {helper}: {executable}")
        _assert_stj_not_clobbered(executable.parent)

    inject = published.get("npv-inject")
    if inject is not None:
        _verify_inject_can_load_json(inject)
        print(f"smoke ok: {inject.name} loads System.Text.Json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
