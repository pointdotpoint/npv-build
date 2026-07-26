#!/usr/bin/env python3
"""Probe exact inventory-item garment appearances from the installed game."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from npv_build.config import get_cache_dir
from npv_build.gui_logic.clothing_catalog import (
    build_catalog_from_game,
    load_catalog,
)
from npv_build.wk_cli import WolvenKit, WolvenKitConfig


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("game_dir", type=Path)
    parser.add_argument(
        "item_ids",
        nargs="*",
        default=[
            "Shirt_01_basic_01",
            "Shirt_01_basic_02",
            "Q301_nusa_agent",
        ],
    )
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument(
        "--cache",
        type=Path,
        default=get_cache_dir() / "clothing_catalog.json",
    )
    args = parser.parse_args()

    entries = None if args.rebuild else load_catalog(args.cache)
    if entries is None:
        wk = WolvenKit(WolvenKitConfig(game_dir=args.game_dir, verbosity=0))
        entries = build_catalog_from_game(
            args.game_dir,
            wk,
            Path(__file__).parents[1] / "npv_build" / "data" / "clothes.json",
            args.cache,
        )

    selected = [
        entry for entry in entries if entry.get("item_id") in set(args.item_ids)
    ]
    print(json.dumps(selected, indent=2))
    missing = sorted(set(args.item_ids) - {entry["item_id"] for entry in selected})
    if missing:
        print(f"Missing item IDs: {', '.join(missing)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
