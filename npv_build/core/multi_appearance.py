"""Multi-appearance NPVs: merge an already-built appearance into an already-built mod.

The community "add appearance to an NPV" workflow appends an appearance entry
(with its own component array) to an existing mod's `.app` `appearances` list
and registers the appearance name in the AMM lua's `appearances` block. This
module implements exactly that merge — it does NOT rebuild the npv-build
pipeline. Both the base mod and the incoming appearance are assumed to already
be fully-built, valid npv-build output (i.e. products of `wolvenkit.py`'s
normal assembly, including npv-inject's component injection).

M3's H1 spike (docs/research/2026-07-17-archivexl-spike-notes.md) proved that
WolvenKit `serialize` -> `deserialize` round-trips a full component-bearing
`.app` with JSON-structural equality (same components, mesh/morph depot-path
hashes, meshAppearance, and bind names) for a SINGLE `.app`. `add_appearance`
reuses that exact mechanism: serialize both `.app` files to JSON, merge at the
JSON level, deserialize the merged JSON back to a cooked `.app`, then pack.

KNOWN LIMITATION -- handle/CRUID reconciliation across two different .app
files is NOT implemented and is explicitly out of scope for this module.

WolvenKit's CR2W format carries an internal handle table (component object
references resolved via `HandleRefId`/`HandleId` pairs) and a `CruidDict`
(component-handle UID table) that WolvenKit regenerates on every write. H1's
own round-trip of a SINGLE `.app` already showed the `CruidDict` value table
changes on every `deserialize` pass (keys stayed structurally identical, but
values differed) -- i.e. even a same-file round-trip does not guarantee
byte-stable handles. Merging the appearance entry of a SECOND, independently
-serialized `.app` into a first `.app`'s JSON means:

- The incoming appearance's component objects carry `HandleRefId` values that
  were only ever valid relative to *its own* `.app`'s handle table. Splicing
  that appearance's `Data` dict wholesale into a different `.app`'s JSON does
  not, by itself, remap those handle IDs into the target document's handle
  space. If WolvenKit's `deserialize` step does not independently re-resolve
  or regenerate those references (unconfirmed -- not desk-tested here), a
  merged document could silently carry dangling/incorrect handle references
  even though the merge is JSON-structurally "valid" (keys and shapes match).
- H1 explicitly reported one unresolved appearance-fidelity defect (overlapping
  eye colors) after a same-file round-trip, not yet root-caused as
  round-trip-loss vs. a pre-existing mapping gap. A cross-.app merge is a
  strictly less-proven operation than what H1 tested.
- H2 (a related but different mechanism -- ArchiveXL resource-patching a new
  appearance onto a *different* stock `.app`) was spike-tested and FAILED
  as-built (loaded, but the patch was a no-op) -- i.e. the adjacent "merge two
  appearances across .app boundaries" problem space has an already-observed
  failure mode in this codebase's own research, not just a theoretical risk.

Given the above, `merge_appearance_json` in this module deliberately does
ONLY a shallow, structural dict merge: it copies the named appearance entry
(whatever handle/CRUID references it contains) from `new` into `base`'s
`appearances` list, verbatim, and raises `NpvError` on a name collision. It
does NOT attempt to detect, remap, or validate handle/CRUID consistency
between the two source documents. Treat the merged output as an UNVERIFIED
artifact until a real-WolvenKit round trip + in-game spawn check confirms the
merged `.app` loads correctly with both appearances intact. That real
verification (build two real npv-build mods, run `add_appearance` against
their actual `.app` output, deserialize+pack, spawn-test in AMM) is a
follow-up requiring the user's game install and WolvenKit -- gated the same
way M3-T4 (in-game spike verification) was gated. It is NOT performed by this
module or its test suite, which operate purely at the JSON/text level.
"""

from __future__ import annotations

import copy
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from .errors import NpvError

__all__ = ["merge_appearance_json", "append_amm_appearance", "add_appearance"]


def _appearances(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return doc["Data"]["RootChunk"]["appearances"]


def _appearance_name(entry: dict[str, Any]) -> str:
    return entry["Data"]["name"]


def merge_appearance_json(
    base: dict[str, Any], new: dict[str, Any], new_name: str
) -> dict[str, Any]:
    """Copy the appearance entry named `new_name` from `new` into `base`.

    Pure dict merge -- no I/O, no WolvenKit. Does not mutate `base` or `new`;
    returns a new merged dict. Raises `NpvError` if `new_name` is already
    present in `base`'s appearances list, or if `new_name` is not found in
    `new`'s appearances list.

    See the module docstring's KNOWN LIMITATION for what this merge does
    NOT verify (handle/CRUID consistency across the two source .app files).
    """
    base_names = {_appearance_name(e) for e in _appearances(base)}
    if new_name in base_names:
        raise NpvError(
            f"Appearance '{new_name}' already exists in the target mod.",
            remediation="Choose a different appearance name, or remove the existing "
            "entry before merging.",
        )

    new_entries = {_appearance_name(e): e for e in _appearances(new)}
    if new_name not in new_entries:
        raise NpvError(
            f"Appearance '{new_name}' was not found in the source appearance file.",
            remediation="Check the appearance name against the source .app's appearances list.",
        )

    merged = copy.deepcopy(base)
    _appearances(merged).append(copy.deepcopy(new_entries[new_name]))
    return merged


_APPEARANCES_BLOCK_RE = re.compile(r"(appearances\s*=\s*\{)(.*?)(\n(\s*)\})", re.DOTALL)


def append_amm_appearance(lua_path: Path, appearance_name: str) -> None:
    """Insert `appearance_name` into the lua file's `appearances = { ... }` list.

    Idempotent: if the name is already present (as a quoted string literal
    inside the appearances block), the file is left unchanged.
    """
    text = lua_path.read_text(encoding="utf-8")

    match = _APPEARANCES_BLOCK_RE.search(text)
    if match is None:
        raise NpvError(
            f"Could not find an `appearances = {{ ... }}` block in {lua_path}.",
            remediation="Verify this is an npv-build-generated AMM lua file.",
        )

    body = match.group(2)
    quoted = f'"{appearance_name}"'
    if quoted in body:
        return  # already registered -- idempotent no-op

    closing_indent = match.group(4)
    entry_indent = closing_indent + "  "

    stripped_body = body.rstrip()
    if stripped_body and not stripped_body.endswith(","):
        stripped_body += ","
    new_body = f"{stripped_body}\n{entry_indent}{quoted}\n{closing_indent}"

    new_text = text[: match.start()] + match.group(1) + new_body + "}" + text[match.end() :]
    lua_path.write_text(new_text, encoding="utf-8")


def add_appearance(
    wk: Any,
    existing_mod_archive: Path,
    new_appearance_app: Path,
    new_appearance_name: str,
    out_archive: Path,
) -> Path:
    """Merge `new_appearance_name` from `new_appearance_app` into an existing
    mod's `.app` (found by serializing `existing_mod_archive`'s `.app`), then
    repack.

    File-level orchestration only: serialize both `.app` files to JSON via
    `wk`, delegate the actual merge to `merge_appearance_json` (kept pure and
    separately unit-tested), deserialize the merged JSON back to a cooked
    `.app`, and pack the result into `out_archive`. See the module docstring
    for the handle/CRUID KNOWN LIMITATION this orchestration does not
    resolve.

    `wk` must provide `serialize(cr2w_file, *, dest)`, `deserialize(target)`,
    and `pack(source_dir, *, dest)`, matching `npv_build.wk_cli.WolvenKit`'s
    contract.
    """
    with tempfile.TemporaryDirectory(prefix="npv_multi_appearance_") as td:
        td_path = Path(td)

        base_json_dir = td_path / "base_json"
        new_json_dir = td_path / "new_json"

        base_json_path = wk.serialize(existing_mod_archive, dest=base_json_dir)
        new_json_path = wk.serialize(new_appearance_app, dest=new_json_dir)

        base_doc = json.loads(base_json_path.read_text(encoding="utf-8"))
        new_doc = json.loads(new_json_path.read_text(encoding="utf-8"))

        merged_doc = merge_appearance_json(base_doc, new_doc, new_appearance_name)

        base_json_path.write_text(json.dumps(merged_doc), encoding="utf-8")
        wk.deserialize(base_json_path)

        # After deserialize, WolvenKit writes the cooked .app next to the JSON
        # (same directory, .app extension in place of .json).
        cooked_app = base_json_path.with_suffix("")
        pack_source = td_path / "pack_source"
        pack_source.mkdir(parents=True, exist_ok=True)
        target = pack_source / cooked_app.name
        target.write_bytes(cooked_app.read_bytes())

        return wk.pack(pack_source, dest=out_archive)
