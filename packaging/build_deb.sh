#!/usr/bin/env bash
# Build a Debian package from the PyInstaller one-dir output.
# Usage: packaging/build_deb.sh <version>
set -euo pipefail

VERSION="${1:?usage: build_deb.sh <version>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="$ROOT/packaging"
DIST="$PKG/dist"
BUNDLE="$DIST/npv-build"
DEBROOT="$DIST/deb-root"
OUTPUT="$DIST/npv-build_${VERSION}_amd64.deb"

if [ ! -x "$BUNDLE/npv-build" ]; then
  echo "missing PyInstaller bundle: $BUNDLE/npv-build" >&2
  exit 1
fi

rm -rf "$DEBROOT"
install -d \
  "$DEBROOT/DEBIAN" \
  "$DEBROOT/usr/bin" \
  "$DEBROOT/usr/lib/npv-build" \
  "$DEBROOT/usr/share/applications" \
  "$DEBROOT/usr/share/icons/hicolor/scalable/apps"
cp -a "$BUNDLE/." "$DEBROOT/usr/lib/npv-build/"
ln -s ../lib/npv-build/npv-build "$DEBROOT/usr/bin/npv-build"
install -m 0644 "$PKG/npv-build.desktop" \
  "$DEBROOT/usr/share/applications/npv-build.desktop"
install -m 0644 "$PKG/npv-build.svg" \
  "$DEBROOT/usr/share/icons/hicolor/scalable/apps/npv-build.svg"

INSTALLED_SIZE="$(du -sk "$DEBROOT/usr" | cut -f1)"
sed \
  -e "s/@VERSION@/$VERSION/g" \
  -e "s/@INSTALLED_SIZE@/$INSTALLED_SIZE/g" \
  "$PKG/debian/control.in" > "$DEBROOT/DEBIAN/control"

dpkg-deb --build --root-owner-group "$DEBROOT" "$OUTPUT"
echo "built: $OUTPUT"
