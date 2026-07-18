# Release QA Checklist

Run before publishing a release (both Windows and Linux). Fresh machine / clean user profile ideal.

## Per platform (Windows .zip, Linux AppImage)

### Web UI flow
- [ ] Artifact downloads and its SHA-256 matches the line in `SHA256SUMS`.
- [ ] Launches by double-click → web UI (pywebview) opens (Windows: dismiss the SmartScreen warning — unsigned is expected).
- [ ] Settings onboarding appears; game-dir auto-detect finds the install (or manual browse works).
- [ ] Settings installs WolvenKit + Blender (checksum-verified) — NOT bundled.
- [ ] Source screen allows picking a save file; save list shows thumbnails.
- [ ] Appearance screen displays parsed CC data (face morphs, skin tone, eyes, etc.).
- [ ] Build screen shows configurable options (hair, skin, garments); build completes with stage timeline visible.
- [ ] Install screen shows install instructions; after copying to game folder, NPV spawns in-game via AMM.
- [ ] My NPVs screen lists previously built NPVs.
- [ ] (Linux only) Verify WebKitGTK is present (`gir1.2-webkit2-4.1` installed); on a clean system, first run should prompt or fail gracefully if missing.

### CLI and integration
- [ ] CLI works from a terminal: `npv-build --probe-save <save>` prints the patch.
- [ ] `npv-build-gui` from the terminal launches the web UI.
- [ ] Spawn a built NPV in-game via AMM → correct face/clothing/animation, no T-pose.

## Artifact hygiene
- [ ] No third-party binaries in the artifact (no WolvenKit/Blender/.NET/CDPR assets) — inspect the bundle.
- [ ] SHA256SUMS covers every attached artifact.
