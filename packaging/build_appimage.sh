#!/usr/bin/env bash
# Build a Linux AppImage from the PyInstaller one-dir output.
# Usage: packaging/build_appimage.sh <version>
set -euo pipefail
VERSION="${1:?usage: build_appimage.sh <version>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="$ROOT/packaging"
DIST="$PKG/dist"
APPDIR="$DIST/npv-build.AppDir"

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -r "$DIST/npv-build" "$APPDIR/usr/bin/npv-build"
cp "$PKG/AppRun" "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"
cp "$PKG/npv-build.desktop" "$APPDIR/npv-build.desktop"
# minimal icon (1x1 png is valid; a real icon can replace it later)
if [ ! -f "$PKG/npv-build.png" ]; then
  printf '\x89PNG\r\n\x1a\n' > "$APPDIR/npv-build.png"  # placeholder
else
  cp "$PKG/npv-build.png" "$APPDIR/npv-build.png"
fi

# fetch appimagetool if not present — into a tool dir OUTSIDE $DIST so it never
# matches the release's `*.AppImage` upload glob (would otherwise be attached to
# the release and land in SHA256SUMS).
TOOLDIR="$PKG/.appimagetool"
mkdir -p "$TOOLDIR"
TOOL="$TOOLDIR/appimagetool.AppImage"
if [ ! -f "$TOOL" ]; then
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$TOOL"
fi

ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" \
  "$DIST/npv-build-${VERSION}-x86_64.AppImage"
echo "built: $DIST/npv-build-${VERSION}-x86_64.AppImage"
