# Clothing catalog name-to-mesh spike — 2026-07-25

**Superseding decision: ship the exact TweakDB → item entity → appearance
resource → garment component graph. The earlier filename join is retained only
as a test/diagnostic helper and is not used by the production picker.**

The catalog must prefer a smaller set of known-existing player meshes over a
larger set of plausible paths. A disabled row cannot break a build; an
incorrectly enabled row can.

## Inputs

- Game install: Cyberpunk 2077, local Steam installation on 2026-07-25.
- WolvenKit CLI: 8.19.0.
- Source names: `pointdotpoint/cyberpunk-mod-list` commit
  `5b7a86801ae1f0c89169c3ff48ce3214ab5cfca2`.
- Vendored `clothes.json`: 1,485 string-only records, SHA-256
  `df45b4604cecdd544302b4c1253c044263b9923e199682d692fab5b181c11db9`.

No game assets or image files are vendored.

## Option 1 measurements

WolvenKit enumerated 3,217 garment meshes from the base-game archives. Of
those, 190 groups are exact primary `player_equipment` meshes whose filename
matches the containing directory and which have a `pwa` and/or `pma` variant.
Decorative child meshes are excluded.

The plan's normalized-token fuzzy join enabled 56 of 1,485 items (3.8%).
Eyeballing the sample exposed false positives, so it failed both the 60%
coverage gate and the 90% precision gate.

A second deterministic join used the garment family and numeric part of the
TweakDB item ID, required an expected slot prefix, required a compatible mesh
descriptor, and accepted only an unambiguous primary mesh group. It measured:

| Expected slot | Joined | Total | Coverage |
| --- | ---: | ---: | ---: |
| Feet | 31 | 134 | 23.1% |
| Head | 54 | 283 | 19.1% |
| Inner torso | 30 | 272 | 11.0% |
| Legs | 26 | 229 | 11.4% |
| Outer torso | 18 | 405 | 4.4% |
| Other/quest | 0 | 162 | 0% |
| **Overall** | **159** | **1,485** | **10.7%** |

Of the 159 joined records, 140 have a PWA mesh and 153 have a PMA mesh.
The script prints 20 deterministic samples and writes the joined records to
`/tmp/clothing_spike_join.json`.

This mapping is intentionally conservative. The item number identifies a base
garment family, not necessarily the inventory item's exact visual variant.
The current NPV garment override contract stores a mesh path but not a garment
appearance, so the picker labels mapped records as base-mesh choices and never
claims to reproduce the inventory thumbnail's colour variant.

## Option 2 evaluation

No current, version-pinned, redistributable community dump containing the
required vanilla item-to-entity/appearance mapping was found. The available
TweakDB-Edit/TweakDump material is explicitly outdated and does not provide a
current licensed data artifact suitable for vendoring. Therefore no community
dump is added to the repository.

## Option 3 evaluation

The installed WolvenKit source can parse `r6/cache/tweakdb.bin` and exposes
`gamedataItem_Record.appearanceName` and `.entityName`. Those fields do not
directly name a garment mesh: resolving them requires traversing the item
factory, entity, appearance, and component graph, and preserving the selected
appearance in the build contract. Adding a partial TweakDB parser would still
produce unsafe mesh guesses and would create the maintenance surface called out
by the plan.

## Exact graph implementation and measurements

The `npv-tweakdb` helper reads `appearanceName` and `entityName` for the
requested `Items.*` records from the installed base-game and expansion
TweakDBs. Python then:

1. opens the corresponding `player_*_item.ent`;
2. selects the rig-specific inventory appearance;
3. opens its exact `.app`;
4. retains every garment mesh component and its `meshAppearance`;
5. uncooks each unique mesh and verifies that the appearance exists.

On the installed 2026-07-25 game this produced 1,485 visible rows, with 1,357
validated PWA choices and 1,343 validated PMA choices. The final one-time
uncached catalog build took 3m34s. Normal application starts load the versioned
derived cache; it is invalidated by size/`mtime_ns` changes to either TweakDB
or the helper binary.

The ambiguity gate now passes:

| Item | PWA mesh | Validated appearance |
| --- | --- | --- |
| `Shirt_01_basic_01` | `t1_035_pwa_shirt__suit.mesh` | `blue_moro` |
| `Shirt_01_basic_02` | `t1_035_pwa_shirt__suit.mesh` | `black_psycho` |

The EP1 gate also passes. `Q301_nusa_agent` traverses
`player_outfit_item_ep1.ent` to `ep1\...\outfit_01.app`, then validates
`t2_148_pwa_jacket__harford_slim.mesh` with appearance
`secret_service01`. Because this outfit also owns legs and feet components,
the catalog records all three occupied slots so fallback pants/shoes are
removed during assembly.

128 PWA rows and 142 PMA rows remain disabled. These include shapes with no
matching rig template or no validated mesh appearance; for example
`Q307_hospital_outfit` currently remains disabled rather than substituting a
default or partial outfit.

Thus two inventory records sharing a mesh retain different thumbnail/material
variants. Unresolved records and missing rig siblings remain visible but
disabled; production does not substitute `default`.

## Reproduction

```bash
uv run python scripts/clothing_spike.py \
  "$HOME/.local/share/Steam/steamapps/common/Cyberpunk 2077"

uv run python scripts/probe_clothing_appearances.py \
  "$HOME/.local/share/Steam/steamapps/common/Cyberpunk 2077"
```
