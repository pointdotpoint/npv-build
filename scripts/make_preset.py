"""Decode an untouched default-V save into a vendorable preset.

Usage: uv run python scripts/make_preset.py <sav.dat> <pwa|pma>
Writes npv_build/data/presets/default_v_<rig>.json (strings/IDs only).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from npv_build.save_parser import parse_save  # noqa: E402

PRESET_DIR = Path(__file__).parents[1] / "npv_build" / "data" / "presets"


def make_preset(save_path: Path, rig: str) -> dict:
    cc = parse_save(Path(save_path))
    if cc.get("body_rig") != rig:
        sys.exit(
            f"Save decodes as body_rig={cc.get('body_rig')!r}, expected {rig!r}."
        )
    return cc


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[2] not in ("pwa", "pma"):
        sys.exit(__doc__)
    preset = make_preset(Path(sys.argv[1]), sys.argv[2])
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    out = PRESET_DIR / f"default_v_{sys.argv[2]}.json"
    out.write_text(json.dumps(preset, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {out} ({len(preset.get('selections', []))} selections)")


if __name__ == "__main__":
    main()
