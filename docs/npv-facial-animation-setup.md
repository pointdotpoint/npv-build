# NPV Facial Animation Setup -- Complete Reference

**Date:** 2025-05-24
**Source:** WolvenKit source code analysis + wiki.redmodding.org

## Root Cause of Static Face

The face_rig `entAnimatedComponent` must exist **in the .app file** (inside
each `appearanceAppearanceDefinition.components[]`), NOT just in the .ent.
The .ent provides the body animation rig (`root` entAnimatedComponent), but
facial animations are per-appearance and live in the .app.

If the .app has NO `face_rig` entAnimatedComponent, the face will be
completely static -- no blinking, no lip movement, no expressions.

## Required Components in .app

### 1. face_rig (entAnimatedComponent) -- CRITICAL

This is the component that drives ALL facial animations.

```json
{
  "$type": "entAnimatedComponent",
  "name": "face_rig",
  "rig": {
    "DepotPath": "base\\characters\\head\\player_base_heads\\player_female_average\\h0_000_pwa_c__basehead\\h0_000_pwa_c__basehead_skeleton.rig"
  },
  "graph": {
    "DepotPath": "<ANIMGRAPH -- see section below>"
  },
  "facialSetup": {
    "DepotPath": "base\\characters\\head\\player_base_heads\\player_female_average\\h0_000_pwa_c__basehead\\h0_000_pwa_c__basehead_rigsetup.facialsetup"
  },
  "animations": {
    "cinematics": [],
    "gameplay": []
  },
  "controlBinding": {
    "$type": "entAnimationControlBinding",
    "bindName": "face_rig",
    "enabled": true
  }
}
```

Key properties:
- **name**: Must be `"face_rig"` (exact string)
- **rig**: Points to V's head skeleton `.rig` file
- **graph**: The facial animation graph (`.animgraph`) -- determines WHAT
  animations play
- **facialSetup**: The facial rig setup (`.facialsetup`) -- maps rig bones to
  facial blend shapes
- **controlBinding.bindName**: Must be `"face_rig"` to match the component
  name, so the animation system can find it
- **animations**: Can hold gameplay and cinematic `.anims` entries

### 2. entAnimationSetupExtensionComponent -- REQUIRED for animation sets

This component loads the actual `.anims` files that contain facial animation
data (idle expressions, transitions, gestures, lip sync, etc.).

```json
{
  "$type": "entAnimationSetupExtensionComponent",
  "name": "face_base_animations",
  "animations": {
    "gameplay": [
      {
        "priority": 200,
        "animSet": { "DepotPath": "<path_to_.anims_file>" }
      }
    ],
    "cinematics": []
  },
  "controlBinding": {
    "$type": "entAnimationControlBinding",
    "bindName": "face_rig",
    "enabled": true
  }
}
```

Key: the `controlBinding.bindName` MUST be `"face_rig"` to bind these
animation sets to the face_rig entAnimatedComponent.

## AnimGraph Selection (graph property)

The animGraph determines facial behavior. Different graphs serve different
purposes:

### For spawned NPVs (AMM, world-placed):
| Gender | AnimGraph |
|--------|-----------|
| Female (player head) | `base\animations\facial\_facial_graphs\player_woman_paperdoll_sermo.animgraph` |
| Female (average NPC) | `base\animations\facial\_facial_graphs\woman_average_sermo.animgraph` |
| Male (player head) | `base\animations\facial\_facial_graphs\player_man_paperdoll_sermo.animgraph` |
| Male (average NPC) | `base\animations\facial\_facial_graphs\man_average_sermo.animgraph` |

### For photomode NPVs:
| Gender | AnimGraph |
|--------|-----------|
| Female | `base\animations\facial\_facial_graphs\player_woman_photomode_sermo.animgraph` |
| Male | `base\animations\facial\_facial_graphs\player_man_photomode_sermo.animgraph` |

**IMPORTANT DISTINCTION:**
- `player_woman_photomode_sermo.animgraph` = Photomode only (responds to
  photomode pose commands, NOT gameplay idle animations)
- `player_woman_paperdoll_sermo.animgraph` = Spawned NPC with player V head
  (responds to gameplay idle, blinking, looking around)
- `woman_average_sermo.animgraph` = Standard NPC facial behavior (most
  natural for world NPCs)

**If you copied Judy's face_rig and it uses
`player_woman_photomode_sermo.animgraph`, that is WRONG for a spawned NPV.**
That graph only activates during photomode. For a regular spawned NPC,
use `player_woman_paperdoll_sermo.animgraph` or `woman_average_sermo.animgraph`.

## FacialSetup (facialSetup property)

Must match the head skeleton being used:

| Body Rig | FacialSetup Path |
|----------|-----------------|
| pwa (female) | `base\characters\head\player_base_heads\player_female_average\h0_000_pwa_c__basehead\h0_000_pwa_c__basehead_rigsetup.facialsetup` |
| pma (male) | `base\characters\head\player_base_heads\player_man_average\h0_000_pma_c__basehead\h0_000_pma_c__basehead_rigsetup.facialsetup` |

Your current facialSetup path is correct for female V.

## Rig (rig property)

Must match the head skeleton:

| Body Rig | Rig Path |
|----------|----------|
| pwa (female) | `base\characters\head\player_base_heads\player_female_average\h0_000_pwa_c__basehead\h0_000_pwa_c__basehead_skeleton.rig` |
| pma (male) | `base\characters\head\player_base_heads\player_man_average\h0_000_pma_c__basehead\h0_000_pma_c__basehead_skeleton.rig` |

Your current rig path is correct for female V.

## Required Animation Sets (.anims files)

The entAnimationSetupExtensionComponent needs these .anims loaded in its
`animations.gameplay[]` array. These are the NPC facial animation entries
from WolvenKit's source (SelectAnimationPathViewModel.NPCAnimEntries):

### Core facial idle/expression animations:
```
base\animations\facial\female_average\interactive_scene\generic_average_female_facial_idle.anims
base\animations\facial\female_average\interactive_scene\generic_average_female_facial_transitions.anims
base\animations\facial\female_average\interactive_scene\generic_average_female_facial_transitions_correctives.anims
base\animations\facial\female_average\interactive_scene\generic_average_female_facial_gestures.anims
base\animations\facial\female_average\interactive_scene\generic_average_female_facial_custom_animations.anims
base\animations\facial\female_average\interactive_scene\generic_average_female_facial_quirks.anims
base\animations\facial\female_average\interactive_scene\generic_average_female_facial_idle_poses.anims
```

### Generic facial animations (both genders):
```
base\animations\facial\generic\interactive_scene\generic_facial_additives.anims
base\animations\facial\generic\interactive_scene\generic_facial_combat.anims
base\animations\facial\generic\interactive_scene\generic_facial_lipsync_gestures.anims
base\animations\facial\generic\interactive_scene\generic_facial_gestures.anims
```

### Gameplay/combat facial animations:
```
base\animations\facial\gameplay\face_reaction_base.anims
base\animations\facial\gameplay\mb_environmental_takedowns\face_environmental_takedowns.anims
```

For photomode, additional anims are used:
```
base\animations\ui\photomode\photomode_female_facial.anims
```

## controlBinding Configuration

The `controlBinding` on BOTH the face_rig entAnimatedComponent AND the
entAnimationSetupExtensionComponent must have:

```json
{
  "$type": "entAnimationControlBinding",
  "bindName": "face_rig",
  "enabled": true,
  "enableMask": {
    "hardTags": { "tags": [] },
    "softTags": { "tags": [] },
    "excludedTags": { "tags": ["NoBinding"] }
  }
}
```

The `bindName` of `"face_rig"` is what links the extension component's
animation sets to the face_rig's animation graph. Without this binding,
the animation sets are never fed to the facial animation graph.

## Photomode vs Regular NPV Differences

| Aspect | Regular NPV (AMM spawn) | Photomode NPV |
|--------|------------------------|---------------|
| AnimGraph | `player_woman_paperdoll_sermo.animgraph` or `woman_average_sermo.animgraph` | `player_woman_photomode_sermo.animgraph` |
| Animation sets | NPC facial idle/gesture/combat anims | `photomode_female_facial.anims` + xbaebsae entries |
| .ent extras | None | Needs `PhotoModePlayerEntityComponent` |
| .ent anims | Standard NPC locomotion | Photomode-specific locomotion anims |

## Diagnosis Checklist for "No Facial Animations"

1. **Does the .app have a `face_rig` entAnimatedComponent?**
   If not, facial animations cannot play. Add one.

2. **Is the animGraph correct for your use case?**
   `photomode_sermo` only works in photomode. For regular spawned NPCs,
   use `paperdoll_sermo` or the NPC-type `_average_sermo`.

3. **Does the .app have an entAnimationSetupExtensionComponent?**
   Without this, no .anims files are loaded, so no animation data exists.

4. **Is controlBinding.bindName set to "face_rig" on BOTH components?**
   This is how the engine links the animation sets to the facial rig.

5. **Are the .anims files actually loaded?**
   The gameplay[] array in the extension component must contain entries
   pointing to valid .anims files for facial idle, gestures, etc.

6. **Do the rig and facialSetup match the head mesh being used?**
   Mismatched skeleton/facialsetup will prevent animations from driving
   the correct bones.

7. **Is the face_rig component actually inside the .app appearance's
   components array (not just in the .ent)?**
   The .ent's `root` entAnimatedComponent handles body. The .app must
   provide the `face_rig` for facial animations.
