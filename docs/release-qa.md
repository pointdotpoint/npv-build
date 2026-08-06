# Release QA Checklist

Run before publishing a release on a fresh machine or clean user profile where possible.

## Required release assets

- [ ] Windows installer: `npv-build-<version>-windows-x86_64-setup.exe`
- [ ] Windows portable bundle: `npv-build-<version>-windows-x86_64.zip`
- [ ] Linux AppImage: `npv-build-<version>-x86_64.AppImage`
- [ ] Debian package: `npv-build_<version>_amd64.deb`
- [ ] `SHA256SUMS` covers exactly those four assets.

## Per platform and format

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
- [ ] (Linux only) Launch on a system without WebKitGTK; the bundled Qt WebEngine UI must still open.
- [ ] Windows installer creates Start menu/uninstall entries and cleanly uninstalls.
- [ ] Windows portable ZIP runs after extraction without installation.
- [ ] AppImage runs after `chmod +x` without extracting it manually.
- [ ] `.deb` installs with `apt`, exposes `/usr/bin/npv-build`, and cleanly removes.

## Cross-distribution Linux spot-check

The AppImage bundles its own Qt WebEngine runtime, but glibc floor, GPU/EGL
stack, and sandbox behavior differ per distro. CI only proves Ubuntu under
Xvfb. Before (or shortly after) publishing, spot-check the release AppImage
on at least one distro from a different family than the last release's check.
Rotate through:

| Family | Example distro | Notes |
| --- | --- | --- |
| Debian-based | Ubuntu LTS (CI-covered), Mint | baseline |
| Fedora/RHEL | Fedora Workstation (current) | newer glibc, Wayland default |
| Arch-based | Arch, EndeavourOS | rolling glibc/Mesa |
| openSUSE | Tumbleweed | rolling, AppArmor default |

Per distro, on a real desktop session (not a container):

1. Download the release `.AppImage` + `SHA256SUMS`; verify
   `sha256sum -c SHA256SUMS` passes for it.
2. `chmod +x` and double-click (or run) with **no arguments** — the GUI must
   open and render the Source screen (no blank/white window, no missing-lib
   dialog).
3. Wayland session if available: confirm the window renders (Qt may fall back
   to XWayland — fallback is acceptable, a blank window is not).
4. From a terminal, run CLI mode against any real save:
   `./npv-build-*.AppImage <sav.dat> "QA V" --output /tmp/qa_v` — it must
   parse the save and report the patch version (full build optional; needs a
   game install).
5. Record distro, version, session type (X11/Wayland), and result in the
   release notes draft.

Failures here are release blockers only if the GUI cannot launch at all on a
mainstream current distro; render glitches get an issue with the distro +
session details instead.

### CLI and integration
- [ ] CLI works from a terminal: `npv-build --probe-save <save>` prints the patch.
- [ ] Running the packaged executable with no arguments launches the web UI.
- [ ] Bundled `npv-inject`, `npv-photomode`, and `npv-tweakdb` helpers are present.
- [ ] Spawn a built NPV in-game via AMM → correct face/clothing/animation, no T-pose.

## Artifact hygiene
- [ ] No standalone WolvenKit, Blender, or CDPR payloads are bundled — inspect the artifact.
- [ ] Only NPV Build's self-contained helper binaries are bundled; WolvenKit, Blender, and CDPR assets are not.
- [ ] Linux artifacts contain Qt WebEngine and do not contain PyGObject (`gi`) or require host WebKitGTK.
