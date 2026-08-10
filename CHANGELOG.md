# Changelog

All notable changes to npv-build are documented here. Format: [Keep a Changelog](https://keepachangelog.com/); versioning: [SemVer](https://semver.org/).

## [2.1.0] - 2026-08-10

### Added
- **Appearance preview render** — headless Blender preview of assembled NPVs from
  My NPVs (progress on the button, cache previously rendered views, untextured clay
  materials with a front-facing camera).
- Web UI: library cards show what each NPV was built from; skipped preview
  components are surfaced in the bridge and library UI.
- Appearance inspector shows the save's body tattoo (read naturally from the
  body-tattoo row).
- Updated application icon (NPV brand).
- `npv-inject` hard-fails when its binary is stale relative to the project.

### Fixed
- Body tattoo appearances: strip the body-slot prefix and re-key tattoos to the
  effective skin tone so the appearance exists on the mesh.
- Skin tone is no longer stamped onto seamfix meshes.
- Preview: hard-fail mod-scoped export failures; restore real Blender cache in
  e2e; surface render tail on failure.

### Docs
- Appearance preview plan, follow-up hardening plan, and cross-distro Linux
  release-QA spot-check procedure.

## [2.0.2] - 2026-07-26

### Fixed
- Linux AppImage startup is now portable across distributions by bundling one
  coherent Qt WebEngine runtime instead of mixing packaged GTK libraries with
  the host's WebKitGTK installation.
- Release CI launches both the portable Linux bundle and AppImage under a
  virtual display, preventing CLI-only smoke tests from publishing a broken GUI.

## [2.0.1] - 2026-07-26

### Added
- Full from-scratch appearance controls, including explicit modded-hair loading.
- Complete Photo Mode NPC registration and custom thumbnail generation.
- Windows installer and portable ZIP plus Linux AppImage and Debian packages.

### Fixed
- Hair, clothing, body, and genital selection issues in generated NPVs.
- Native helper discovery in packaged applications.
- Release packages now include the required self-contained NPV helper tools.

### Changed
- Faster incremental builds through caching and reduced redundant WolvenKit work.
- GitHub releases are published automatically after all package smoke tests pass.

## [2.0.0] - 2026-07-17

The 2.0 rewrite: a GUI-first, cross-platform npv-build.

### Added
- **GUI-first workflow** — first-run wizard (game-dir detect + guided dependency install), save browser with thumbnails, build view with cancel and retry-from-failed-stage, mod manager (install/uninstall built NPVs), settings, and multi-appearance merge.
- **Resumable builds** — checkpoint manifest; `--resume` / GUI "Retry from failed stage" skip already-completed stages.
- **Current-patch support** — decodes Cyberpunk saves from patch 2.13 through 2.31 (`--probe-save` to inspect any save); unknown builds hard-fail with a clear message.
- **Mod-manager-ready `.zip`** — every build emits an installable zip.
- **Security** — path-traversal-safe archive extraction, SHA-256-verified downloads, absolute tool-path resolution.
- **Bundled apps** — Windows `.zip` and Linux AppImage; no preinstalled Python required.

### Changed
- Core rewrite: typed error hierarchy, structured logging, cancellable subprocess adapter, `PipelineService` orchestration.
- WolvenKit floor raised to 8.19.

### Notes
- WolvenKit and Blender are downloaded (checksum-verified) by the first-run wizard, not bundled.
- Windows binaries are unsigned in this release; SmartScreen may warn on first launch.

[2.1.0]: https://github.com/pointdotpoint/npv-build/releases/tag/v2.1.0
[2.0.2]: https://github.com/pointdotpoint/npv-build/releases/tag/v2.0.2
[2.0.1]: https://github.com/pointdotpoint/npv-build/releases/tag/v2.0.1
[2.0.0]: https://github.com/pointdotpoint/npv-build/releases/tag/v2.0.0
