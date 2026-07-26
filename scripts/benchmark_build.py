#!/usr/bin/env python3
"""Run repeatable cold, changed-input, and identical NPV build benchmarks."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from npv_build.core.pipeline import BuildRequest, PipelineService
from npv_build.gui_logic.presets import load_preset

_SENTINEL = ".npv-benchmark-owned"

_GARMENTS = {
    "pwa": (
        r"base\characters\garment\player_equipment\torso"
        r"\t2_002_vest__puffy\t2_002_pwa_vest__puffy.mesh",
        r"base\characters\garment\player_equipment\head"
        r"\h1_002_hat__headcap\h1_002_pwa_hat__headcap.mesh",
    ),
    "pma": (
        r"base\characters\garment\player_equipment\torso"
        r"\t2_002_vest__puffy\t2_002_pma_vest__puffy.mesh",
        r"base\characters\garment\player_equipment\head"
        r"\h1_002_hat__headcap\h1_002_pma_hat__headcap.mesh",
    ),
}


@dataclass(frozen=True)
class BenchmarkWorkspace:
    """Two directories that may be cleared only after explicit sentinel ownership."""

    output_dir: Path
    cache_dir: Path

    def _directories(self) -> tuple[Path, Path]:
        return self.output_dir.resolve(), self.cache_dir.resolve()

    @staticmethod
    def _assert_safe(path: Path) -> None:
        forbidden = {Path("/"), Path.home().resolve(), Path.cwd().resolve()}
        if path in forbidden:
            raise ValueError(f"Refusing to use broad benchmark directory: {path}")

    def claim(self) -> None:
        for directory in self._directories():
            self._assert_safe(directory)
            if directory.exists() and not (directory / _SENTINEL).is_file():
                if any(directory.iterdir()):
                    raise ValueError(
                        f"Refusing to adopt non-empty directory without {_SENTINEL}: "
                        f"{directory}"
                    )
            directory.mkdir(parents=True, exist_ok=True)
            (directory / _SENTINEL).write_text(
                "Owned by scripts/benchmark_build.py\n", encoding="utf-8"
            )

    def prepare(self, profile: str) -> None:
        if profile not in {"cold", "warm-changed", "identical"}:
            raise ValueError(f"Unknown benchmark profile: {profile}")
        self.claim()
        if profile != "cold":
            return
        for directory in self._directories():
            if not (directory / _SENTINEL).is_file():
                raise ValueError(f"Benchmark ownership sentinel disappeared: {directory}")
            shutil.rmtree(directory)
            directory.mkdir(parents=True)
            (directory / _SENTINEL).write_text(
                "Owned by scripts/benchmark_build.py\n", encoding="utf-8"
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--preset", choices=("pwa", "pma"), required=True)
    parser.add_argument("--thumbnail", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="Dedicated cache directory (default: sibling of --output-dir).",
    )
    parser.add_argument(
        "--profile",
        choices=("cold", "warm-changed", "identical"),
        required=True,
    )
    parser.add_argument("--garment", help="Depot path used by the cold profile.")
    parser.add_argument(
        "--changed-garment",
        help="Depot path used by warm-changed and identical profiles.",
    )
    parser.add_argument("--json-output", type=Path)
    return parser


def run_benchmark(args: argparse.Namespace) -> dict:
    output_dir = args.output_dir.resolve()
    cache_dir = (
        args.cache_dir.resolve()
        if args.cache_dir is not None
        else output_dir.parent / f"{output_dir.name}.benchmark-cache"
    )
    workspace = BenchmarkWorkspace(output_dir=output_dir, cache_dir=cache_dir)
    workspace.prepare(args.profile)

    default_garment, default_changed_garment = _GARMENTS[args.preset]
    garment = (
        args.garment or default_garment
        if args.profile == "cold"
        else args.changed_garment or default_changed_garment
    )
    request = BuildRequest(
        save_path=None,
        npv_name="NPV Build Benchmark",
        output_dir=output_dir,
        game_dir=args.game_dir.resolve(),
        template_cache=cache_dir,
        cc_settings_override=load_preset(args.preset),
        garments=[garment],
        photomode_thumbnail=args.thumbnail.resolve(),
        resume=args.profile != "cold",
    )

    started_at = time.monotonic()
    result = PipelineService().build(request)
    total_seconds = max(0.0, time.monotonic() - started_at)
    report = {
        "profile": args.profile,
        "preset": args.preset,
        "garment": garment,
        "total_seconds": total_seconds,
        "stage_durations": result.stage_durations,
        "tool_stats": result.tool_stats,
        "stages_run": result.stages_run,
        "stages_resumed": result.stages_resumed,
        "mod_id": result.mod_id,
        "output_dir": result.output_dir,
        "cache_dir": str(cache_dir),
        "zip_path": result.zip_path,
    }
    return report


def main() -> int:
    args = _parser().parse_args()
    report = run_benchmark(args)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
