"""Publish self-contained native helpers for a frozen NPV Build release."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

HELPERS = ("npv-inject", "npv-photomode", "npv-tweakdb")
RIDS = ("linux-x64", "win-x64")


def _remove_foreign_native_assets(output: Path, rid: str) -> None:
    # Managed .NET assemblies use .dll on every platform, so they must remain
    # in the shared helper directory even for Linux releases.
    foreign_suffixes = (".dylib",) if rid == "linux-x64" else (".so", ".dylib")
    for path in output.iterdir():
        is_foreign = path.suffix.lower() in foreign_suffixes
        if path.suffix.lower() == ".pdb" or is_foreign:
            path.unlink()


def publish_helper(repo_root: Path, output_root: Path, helper: str, rid: str) -> Path:
    project = repo_root / "tools" / helper / f"{helper}.csproj"
    if not project.is_file():
        raise FileNotFoundError(f"Missing helper project: {project}")

    output_root.mkdir(parents=True, exist_ok=True)

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
            str(output_root),
            "--nologo",
        ],
        cwd=repo_root,
        check=True,
    )
    executable = output_root / (f"{helper}.exe" if rid == "win-x64" else helper)
    if not executable.is_file():
        raise FileNotFoundError(f"dotnet publish did not produce {executable}")
    if rid == "linux-x64":
        executable.chmod(executable.stat().st_mode | 0o111)
    return executable


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
    for helper in HELPERS:
        executable = publish_helper(repo_root, output_root, helper, args.rid)
        print(f"published {helper}: {executable}")
    _remove_foreign_native_assets(output_root, args.rid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
