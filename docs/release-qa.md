# Release QA Checklist

Run before publishing a release (both Windows and Linux). Fresh machine / clean user profile ideal.

## Per platform (Windows .zip, Linux AppImage)
- [ ] Artifact downloads and its SHA-256 matches the line in `SHA256SUMS`.
- [ ] Launches by double-click → GUI opens (Windows: dismiss the SmartScreen warning — unsigned is expected).
- [ ] First-run wizard appears; game-dir auto-detect finds the install (or manual browse works).
- [ ] Wizard installs WolvenKit + Blender (checksum-verified) — NOT bundled.
- [ ] Save browser lists saves with thumbnails.
- [ ] Build a real NPV from a current-patch save → succeeds; the `.zip` output is produced.
- [ ] Spawn the NPV in-game via AMM → correct face/clothing/animation, no T-pose.
- [ ] CLI works from a terminal: `npv-build --probe-save <save>` prints the patch.

## Artifact hygiene
- [ ] No third-party binaries in the artifact (no WolvenKit/Blender/.NET/CDPR assets) — inspect the bundle.
- [ ] SHA256SUMS covers every attached artifact.
