# Spec: Automated Save Parsing & Part Resolution for `npv-build`

**Status:** Draft for implementation
**Date:** 2026-05-23
**Author:** generated during NPV automation work
**Supersedes:** the `parse_save()` mock in `npv_build/save_parser.py`; the
`preset_id`-only path in `npv_build/mapping.py`

---

## 1. Purpose & goal

Make `npv-build` produce an NPV that matches the player's V **automatically from
a `sav.dat`**, with no manual CET dumping, no Blender, and no hand-editing.

The end state: a user runs

```bash
npv-build /path/to/sav.dat "My V" --output ./my_v_mod
```

and the tool reads V's real Character Customization (CC) selections out of the
save, resolves each selection to the base-game part entity (`.ent`) that
provides it, composes those parts into an authored (uncooked) NPV `.app`/`.ent`
via `partsValues`, cooks and packs with WolvenKit, and writes the AMM `.lua`.

This spec covers the two remaining modules:

1. **Save parser** (`save_parser.py`) — decode the CC node into a structured,
   labelled set of selections. The low-level container reader
   (`save_format.py`) already exists and works.
2. **Part resolution** (`mapping.py` + new `part_resolver.py`) — turn selection
   names into part `.ent` depot paths the composer can consume.

---

## 2. Background: what we proved

These are established facts from investigation, not assumptions:

- **Container format works.** `npv_build/save_format.py` parses the `CSAV`
  (on-disk `VASC`) container: header → footer (`DONE`) → `NODE` descriptor
  table → `CLZF` (on-disk `FZLC`) compressed-chunk table → `XLZ4` LZ4 blocks.
  It decompresses the full node blob and returns the bytes of any node by name.
  Verified on the user's `AutoSave-0/sav.dat` (version `(269, 2310, 195)`,
  1203 nodes, CC node = 9747 bytes).

- **The CC node is named selections, not slider floats.** V's face is **not** a
  sculpted morph requiring Blender. It is a set of named appearance selections
  (`h0_000_pwa__basehead__01_ca_pale`, `he_000_pwa__basehead__14_gradient_grey`,
  makeup/scars/etc.) that all exist as base-game assets. This kills the entire
  Blender branch (see ADR-0002; this confirms its instinct for a new reason).

- **Composition via `partsValues` works end to end.** An authored (no
  `compiledData` buffer) `.app` whose appearance lists `partsValues` →
  part `.ent`s cooks correctly and the references survive packing. This is the
  composition primitive; the only missing input is the *correct, complete* part
  list. Editing a cooked donor `.app` does **not** work (buffer is
  authoritative) — never reintroduce that approach.

---

## 3. CC node binary layout (authoritative)

Ported from PixelRick `CharacetrCustomization_Appearances.h`. All multi-byte
integers little-endian. The node bytes are what `save_format.SaveContainer.
node_bytes("CharacetrCustomization_Appearances")` returns.

### 3.1 Primitive encodings

- `u8`, `u32`, `i32`, `u64` — fixed little-endian.
- `packed_int` — variable-length signed int (`read_int64_packed`, already in
  `save_format._Reader`). 1–5 bytes; continuation bit `0x40` on first byte then
  `0x80` on subsequent; sign bit `0x80` on first byte.
- `lpfxd_string` — `packed_int` count `c`:
  - `c < 0`: `-c` bytes of Latin-1/UTF-8 (the common case here).
  - `c > 0`: `c` UTF-16LE code units (`c*2` bytes).
  - `c == 0`: empty.
  (`save_format._Reader.read_str_lpfxd` already implements this.)

### 3.2 Struct grammar (version v3 == 195, which the user's save is)

```
CCharacterCustomization:
    data_exists : u8           # nonzero when CC present
    uk0         : u32
    if data_exists:
        uk1   : u32
        uk2   : u8
        uk3   : u8
        ukt0  : Group           # section A (head)
        ukt1  : Group           # section B (body)
        ukt2  : Group           # section C (arms)
        ukt5_count : u32
        ukt5  : Thing5 * ukt5_count
        if version.v1 > 171:
            uk6_count : packed_int
            uk6   : lpfxd_string * uk6_count

Group (cetr_uk_thing1):
    count : u32
    slots : Slot * count

Slot (cetr_uk_thing2):
    uks   : lpfxd_string        # slot label, e.g. "eyes", "hairs", "face"
    v3_count : u32
    v3    : Sel * v3_count       # appearance selections
    v4_count : u32
    v4    : Link * v4_count

Sel (cetr_uk_thing3):           # one chosen appearance for the slot
    cn   : u64                   # CName hash (FNV1a64) of the resource/appearance
    uk0  : lpfxd_string          # appearance name, e.g. "h0_000_pwa__basehead__01_ca_pale"
    uk1  : lpfxd_string          # secondary name (sometimes a sub-appearance / variant)
    uk2  : u32
    uk3  : u32

Link (cetr_uk_thing4):
    uk0  : lpfxd_string
    uk1  : lpfxd_string
    uk2  : u32
    uk3  : u32

Thing5 (cetr_uk_thing5):
    uk0  : lpfxd_string
    uk1  : lpfxd_string
    uk2  : lpfxd_string
```

> **Version note:** For `v3 < 195`, `Sel.cn` is an `lpfxd_string` (the resolved
> CName) instead of a `u64` hash. For `v1 <= 168` there are extra branches. We
> target `v3 == 195` (current game) and **must fail loudly** on unsupported
> versions rather than mis-parse — see §6.

### 3.3 Interpreting selections

From the user's save, `Sel.uk0` strings carry the human-meaningful selection:

| Slot label (`uks`) | Example `Sel.uk0`                                   | Meaning                |
|--------------------|-----------------------------------------------------|------------------------|
| (head section)     | `h0_000_pwa__basehead__face_rig`                    | head rig              |
| (head section)     | `h0_000_pwa__basehead__01_ca_pale`                  | head + **skin tone**  |
| `eyes`             | `he_000_pwa__basehead__14_gradient_grey`            | eyes + colour         |
| (head section)     | `female_ht_000__basehead`                           | teeth                 |
| `hairs`            | `fhair_miyavivi_twistup_soft`                       | hair (modded)         |
| (head section)     | `hx_000_pwa__basehead_makeup_eyes__01_black`        | makeup eyes           |
| (head section)     | `hx_000_pwa__basehead__makeup_lips_01__01_black`    | makeup lips           |
| (head section)     | `hx_000_pwa__morphs_makeup_freckles_01__02_...`     | freckles              |
| (head section)     | `hx_000_pwa__basehead_pimples_01__black_02`         | pimples               |
| (head section)     | `h0_000_pwa__scars_01__q_307`                       | scars                 |

The **naming convention** (decode, do not hardcode):

```
<prefix>_<NNN>_<rig>__<group>[__<variant>]
  prefix : h0 head | he eyes | ht teeth | hb brows | hx overlay | i1 accessory
           | t0 body | a0 arms | l0 legs | n0 neck | fhair hair (mod)
  NNN    : preset index (zero-padded)
  rig    : pwa | pma | pa (gender-neutral)
  group  : basehead | scars_01 | makeup_lips_01 | morphs_makeup_freckles_01 | ...
  variant: skin/colour tone suffix, e.g. 01_ca_pale, 14_gradient_grey, 01_black
```

The `__<variant>` suffix is what selects the material/colour. It maps to the
*named appearance inside the part's `.app`*, not to a different `.ent`.

---

## 4. Module 1 — `save_parser.py` (replace the mock)

### 4.1 Signature

```python
def parse_save(save_path: Path) -> dict:  # returns cc_settings
```

Unchanged signature so the orchestrator and `--cc-json` path keep working.

### 4.2 Algorithm

1. `data = save_path.read_bytes()`.
2. `sc = SaveContainer(data)` (from `save_format`). On `SaveFormatError`, raise
   `SaveParserError` with the message.
3. `raw = sc.node_bytes("CharacetrCustomization_Appearances")`. If `None`,
   raise `SaveParserError("no CC node — is this a character save?")`.
4. Parse `raw` with a `_CCReader` implementing §3.2 exactly, producing a typed
   tree: `groups = [Group, Group, Group]`, each `Group.slots`, each
   `Slot{label, selections:[Sel{cn,uk0,uk1}], links}`.
5. **Flatten to `cc_settings`** (the schema the rest of the pipeline consumes).
   Derive fields by decoding `Sel.uk0` with the §3.3 convention:

   ```python
   cc_settings = {
       "patch": detect_patch(sc.version),       # see §4.3
       "body_rig": "pwa" | "pma",                # from any pwa/pma token seen
       "selections": [                            # NEW: full ordered list
           {"slot": <label>, "prefix": "h0", "index": 0, "rig": "pwa",
            "group": "basehead", "variant": "01_ca_pale", "raw": "<uk0>",
            "cname_hash": <u64>}
           , ...
       ],
       # convenience roll-ups (back-compat with current mapping fields):
       "head":  {"preset_id": 0, "raw": "h0_000_pwa__basehead__01_ca_pale"},
       "eyes":  {"raw": "he_000_pwa__basehead__14_gradient_grey"},
       "teeth": {"raw": "female_ht_000__basehead"},
       "skin":  {"tone_id": "01_ca_pale"},
       "hair":  {"style_id": "miyavivi_twistup_soft", "raw": "fhair_..."},
       "overlays": [ <hx_* raws> ],               # makeup/freckles/pimples/scars
   }
   ```

6. Persist nothing here; the orchestrator already writes `cc_settings.json`.

### 4.3 Patch detection

`sc.version` is `(v1, v2, v3)`; for the user's save `v2 == 2310`. Map game build
→ asset-mapping patch label:

- Maintain `npv_build/data/save_versions.json`: `{ "2310": "2.13", ... }`.
- `detect_patch` looks up `v2`; on miss, default to the newest known label and
  emit a warning (assets may still resolve; fail later if they don't).

### 4.4 `_CCReader`

A small class wrapping the node bytes with the same primitives as
`save_format._Reader` (reuse it — import, don't duplicate). Implements the §3.2
grammar top-down. **Must consume to a known end** (track byte cursor; after
parsing, assert cursor within `len(raw)` and ideally `== len(raw)` modulo the
trailing `uk6` block — log if leftover bytes remain, since that signals a
version drift).

---

## 5. Module 2 — part resolution (`part_resolver.py` + `mapping.py`)

### 5.1 The problem

A selection like `h0_000_pwa__basehead__01_ca_pale` must become a
`partsValues` entry. Two viable forms:

- **(A) Named-appearance reference.** The cooked head `.app`
  (`base\characters\head\player_base_heads\appearances\head\h0_000__basehead.app`)
  already contains an appearance literally named
  `h0_000_pwa__basehead__01_ca_pale`. The NPV head part `.ent` for that preset
  references this `.app`; selecting the variant is choosing that appearance
  name. **Preferred** — it carries skin tone + everything baked correctly.

- **(B) Part-ent list.** The per-part `.ent`s
  (`...\appearances\entity\head\h0_000_pwa__basehead.ent`, `he_...ent`,
  `ht_...ent`, `face_decals\heb_...ent`, makeup/scars ents) listed individually
  in `partsValues`. More granular but variant/tone is encoded per-part and
  easy to get wrong.

**Decision:** use **(A) for the head/face/skin** (one part `.ent` whose `.app`
appearance name = V's exact head selection), and **(B) for additive overlays**
(scars, makeup, pimples, freckles) and body/eyes/teeth where a discrete part
`.ent` exists. This matches how the game's own `pwa_default` appearance composes
(verified: its `partsValues` lists head + eyes + teeth + face_decals + body).

### 5.2 Resolution strategy — automated, two-tier

Hardcoding paths per patch does not scale. Use a **generated index** + a small
curated fallback.

#### Tier 1 — generated asset index (preferred, automatic)

A one-time (cached) index built by scanning the game archives:

1. `npv-build --reindex` (or automatic on first run when index missing) runs
   `WolvenKit.CLI archiveinfo <basegame_4_appearance.archive> --list` and any
   other relevant archives.
2. Build `~/.cache/npv/index/<patch>.json`:
   ```json
   {
     "part_ents": {
       "h0_000_pwa__basehead": "base\\characters\\head\\...\\entity\\head\\h0_000_pwa__basehead.ent",
       "he_000_pwa__basehead": "...he_000_pwa__basehead.ent",
       ...
     },
     "head_apps": {
       "h0_000__basehead": "base\\characters\\head\\...\\appearances\\head\\h0_000__basehead.app"
     },
     "app_appearances": {
       "base\\...\\h0_000__basehead.app": ["h0_000_pwa__basehead__01_ca_pale", ...]
     }
   }
   ```
   The `app_appearances` map is built by uncooking just the appearance `.app`s
   (small set) and listing their `appearances[].Data.name`. Cache aggressively;
   keyed by patch.
3. Resolution: for each selection, look up its part `.ent` (and, for the head,
   the `.app` + the exact appearance name) in the index by the decoded
   `prefix_index_rig__group` key.

#### Tier 2 — curated overrides (`data/mappings/<patch>.json`)

For things the index can't disambiguate or for known-good defaults (the body
part, fallbacks when a selection's `.ent` is absent), keep a small curated map.
Tier 1 wins; Tier 2 fills gaps. This file stays tiny (body part, neck part,
proxy, and any rename quirks), not a giant hand-maintained table.

### 5.3 `resolve_assets(cc_settings) -> asset_paths`

Rewrite `mapping.py.resolve_assets`:

```python
asset_paths = {
  "patch": ..., "body_rig": ...,
  "head_app": "...h0_000__basehead.app",          # for form (A)
  "head_appearance_name": "h0_000_pwa__basehead__01_ca_pale",
  "part_entities": [ <ordered .ent depot paths> ],# eyes/teeth/brows/body/overlays
  "external_dependencies": [ {"selection":"fhair_miyavivi_...", "reason":"modded hair not in base game"} ],
  "unresolved": [ <selections with no asset> ],
}
```

- Walk `cc_settings["selections"]`.
- For each, decode key → look up Tier 1 → Tier 2.
- **Head/face/skin:** populate `head_app` + `head_appearance_name`.
- **Eyes/teeth/brows/body/overlays:** append resolved `.ent` to
  `part_entities`.
- **Modded selections** (e.g. `fhair_*` not found in index): record in
  `external_dependencies`, do **not** fail — the NPV will reference it and only
  render if the user has that mod installed. Emit a clear warning + list these
  in the AMM `.lua` header comment so the user knows what mods the NPV needs.
- **Unresolved base-game selections:** record in `unresolved`, warn, continue
  with a sensible fallback (basehead default) so a build always succeeds.

### 5.4 Composer changes (`config_editor.build_app`)

`build_app` currently takes `part_entities`. Extend so the NPV appearance can
either:

- reference the head via a single part `.ent` whose `.app` exposes
  `head_appearance_name` (form A), **plus**
- list the remaining `part_entities` (form B).

Concretely: the NPV `.app` appearance's `partsValues` references the head part
`.ent` (which internally points at the head `.app`); the appearance's
`partsValues` also includes eyes/teeth/brows/body/overlay `.ent`s. The NPV
appearance **name** stays `<mod_id>_appearance`. Skin tone rides along because
the head part’s `.app` appearance variant is the tone-specific one.

> Open verification item (do during impl, not now): confirm whether selecting
> the tone variant requires the NPV appearance to set a `partsOverrides`
> appearance name on the head part, or whether referencing the tone-specific
> head `.app` appearance through the part `.ent` is sufficient. Test both
> against a spawned NPV; keep whichever renders the tone. Document the result in
> a follow-up note in this file.

---

## 6. Robustness, versioning, failure modes

- **Version gate.** If `sc.version[2] != 195`, attempt parse but wrap in a guard
  that validates the post-parse cursor; on leftover/short bytes, raise
  `SaveParserError("CC layout mismatch for save version <v>; parser targets
  v3=195")`. Never emit a half-parsed `cc_settings`.
- **Always produce a build.** Resolution degrades gracefully: unresolved →
  fallback basehead; modded → external dependency note. A run never hard-fails
  on a single missing asset; it fails only if *no* head can be resolved at all.
- **Determinism.** Same save + same game version ⇒ identical `cc_settings.json`
  and identical `mod_id`. (mod_id already hashes cc_settings; keep it stable by
  sorting `selections` canonically before hashing.)
- **No network, no Blender, no CET required.** The save path is fully offline.
  CET dump (`--cc-json`) remains a supported alternative input, sharing the same
  resolution code downstream.

---

## 7. Deliverables & file plan

| File | Change |
|------|--------|
| `npv_build/save_format.py` | exists; no change (low-level container) |
| `npv_build/save_parser.py` | **rewrite**: real CC-node parse → `cc_settings` (§4) |
| `npv_build/part_resolver.py` | **new**: Tier-1 index build + lookup (§5.2) |
| `npv_build/mapping.py` | **rewrite** `resolve_assets` to use resolver, emit head_app + part_entities + deps (§5.3) |
| `npv_build/config_editor.py` | extend `build_app` for head-app + part list (§5.4) |
| `npv_build/orchestrator.py` | thread `external_dependencies`/`unresolved` into warnings + lua header |
| `npv_build/data/save_versions.json` | **new**: game build → patch label |
| `npv_build/data/mappings/<patch>.json` | shrink to curated fallbacks only |
| `~/.cache/npv/index/<patch>.json` | generated asset index (not vendored) |
| `tests/test_save_parser.py` | parse the real `CharacetrCustomization` node fixture → assert known selections |
| `tests/test_part_resolver.py` | selection-name decode + index lookup |

---

## 8. Acceptance criteria

1. `npv-build <real sav.dat> "My V" --output ./out` runs offline, no flags
   beyond first-run `--game-dir` (for index build), and writes a non-empty
   `.archive` + AMM `.lua`.
2. `cc_settings.json` contains V's real selections (head preset, skin tone,
   eyes, teeth, makeup, scars, hair) decoded from the save — verified against
   the known values for the test save (§3.3 table).
3. Spawned NPV renders V's basehead with the **correct skin tone** and the
   resolvable overlays; differs visibly from the bare-basehead build.
4. Modded selections (Miyavi hair) are reported as external dependencies in the
   build log and in the `.lua` header, not silently dropped or fatal.
5. Re-running on the same save is deterministic (same `mod_id`, same archive
   contents).
6. A save from a different preset (e.g. a pma save, or pwa preset != 0) resolves
   its head correctly via the generated index without code changes.

---

## 9. Out of scope (explicit)

- Slider-level facial sculpt baking (Blender). Not needed; V's face is the
  named preset/appearance. If a future save proves to carry per-vertex/joint
  deltas distinct from named appearances, that is a separate ADR.
- Shipping modded assets. The NPV references them; the user must have them.
- Cyberware/clothing transfer beyond face/head/body/hair (already out of v1
  scope per docs/legacy/SPEC.md §2.2).
- Non-2.x save formats.
