# Changelog

All notable changes to npv-build are documented here. Format: [Keep a Changelog](https://keepachangelog.com/); versioning: [SemVer](https://semver.org/).

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

[2.0.0]: https://github.com/pointdotpoint/npv-build/releases/tag/v2.0.0
