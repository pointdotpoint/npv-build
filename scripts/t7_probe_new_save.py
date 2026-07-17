#!/usr/bin/env python3
"""M2 T7 step 1 — probe a new-patch save and report what the runbook needs.

Run this the moment a current-patch save exists:
    uv run python scripts/t7_probe_new_save.py "<path to new sav.dat>"

It prints the build/struct facts that decide the rest of T7:
  - the build number to add to save_versions.json
  - the CC struct version (v3): if 195, the existing decoder is reused (alias);
    if not, a new decoder must be authored by diffing against a 2.13 save.
  - whether the CC node is present and parses under the current (195) decoder.

This does NOT modify anything. It is the read-only front door to the T7 runbook
in docs/superpowers/plans/2026-07-17-m2-patch-currency.md (Task 7).
"""

from __future__ import annotations

import sys
from pathlib import Path

from npv_build.save_format import SaveContainer
from npv_build.save_probe import format_probe, probe_save

KNOWN_2310_V3 = 195


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    save = Path(argv[1])
    if not save.is_file():
        print(f"No such file: {save}", file=sys.stderr)
        return 1

    info = probe_save(save)
    print("=== probe ===")
    print(format_probe(info))
    v1, v2, v3 = info["version"]

    print("\n=== T7 decision ===")
    if info["supported"]:
        print(f"Build {v2} is ALREADY supported (patch {info['patch']}). This is not a new patch;")
        print("nothing to do unless you expected a newer build — check you saved after updating.")
        return 0

    print(f'Build {v2} is NOT yet in save_versions.json -> add "{v2}": "<patch>".')
    if v3 == KNOWN_2310_V3:
        print(f"CC struct v3={v3} MATCHES the 2.13 decoder. Fast path: register the build in")
        print("save_versions.json and alias v3 in CC_DECODERS (no new decoder needed). Then verify")
        print("parse_save() extracts sane cc_settings from this save.")
    else:
        print(f"CC struct v3={v3} DIFFERS from 2.13 (195). A new decoder is required:")
        print(f"  1. copy _decode_cc_v195 -> _decode_cc_v{v3}")
        print("  2. diff the CC node bytes against a 2.13 save's structure, adjust reads")
        print(f"  3. register CC_DECODERS[{v3}]")
        print("  4. add a real 2.3x save fixture + golden cc_settings test")

    print("\n=== raw node inventory (for reverse-engineering) ===")
    container = SaveContainer(save.read_bytes())
    cc = "CharacetrCustomization_Appearances"
    if cc in container.node_names():
        node = container.node_bytes(cc)
        print(f"{cc}: {len(node)} bytes (this is the struct to decode)")
    else:
        print(f"{cc}: MISSING — unexpected; save may be incomplete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
