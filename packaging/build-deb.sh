#!/usr/bin/env bash
# Buduje pakiet .deb (Debian, Ubuntu, Mint) z drzewa zrodel: bash packaging/build-deb.sh [katalog_wyjsciowy]
# Wymaga: dpkg-deb, python3. Ukladem odpowiada pakietowi RPM (te same sciezki).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT}"
VER="$(python3 -I -c "import re,sys;print(re.search(r'__version__ = \"([^\"]+)\"',open('$ROOT/tidydisk/__init__.py').read()).group(1))")"
PKG="tidydisk_${VER}_all"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
B="$T/$PKG"
install -d "$B/DEBIAN" "$B/usr/share/tidydisk" "$B/usr/bin" "$B/usr/libexec/tidydisk"
cp -a "$ROOT/tidydisk" "$ROOT/data" "$B/usr/share/tidydisk/"
find "$B" -name __pycache__ -type d -prune -exec rm -rf {} +
cat > "$B/usr/bin/tidydisk" <<'SH'
#!/usr/bin/bash
export PYTHONPATH=/usr/share/tidydisk${PYTHONPATH:+:$PYTHONPATH}
exec /usr/bin/python3 -m tidydisk "$@"
SH
chmod 755 "$B/usr/bin/tidydisk"
install -Dm644 "$ROOT/data/tidydisk.svg" "$B/usr/share/icons/hicolor/scalable/apps/tidydisk.svg"
for d in "$ROOT"/data/icons/*x*/; do
  s="$(basename "$d")"; install -Dm644 "$d/tidydisk.png" "$B/usr/share/icons/hicolor/$s/apps/tidydisk.png"
done
install -Dm644 "$ROOT/data/tidydisk.desktop" "$B/usr/share/applications/tidydisk.desktop"
install -Dm644 "$ROOT/data/tidydisk.metainfo.xml" "$B/usr/share/metainfo/tidydisk.metainfo.xml"
install -Dm644 "$ROOT/data/org.tidydisk.admin-scan.policy" "$B/usr/share/polkit-1/actions/org.tidydisk.admin-scan.policy"
install -Dm644 "$ROOT/LICENSE" "$B/usr/share/doc/tidydisk/copyright"
install -Dm644 "$ROOT/README.md" "$B/usr/share/doc/tidydisk/README.md"
( cd "$ROOT" && python3 -I -c '
import sys; sys.path.insert(0, ".")
from tidydisk import scanner, __version__
sys.stdout.write(scanner.build_admin_source("/", "", (), argv=True, version=__version__))' ) > "$B/usr/libexec/tidydisk/admin_scan.py"
chmod 755 "$B/usr/libexec/tidydisk/admin_scan.py"
SIZE="$(du -sk "$B/usr" | cut -f1)"
cat > "$B/DEBIAN/control" <<EOF
Package: tidydisk
Version: $VER
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-pyqt6, policykit-1 | polkitd
Replaces: fedora-cleaner
Conflicts: fedora-cleaner
Provides: fedora-cleaner
Installed-Size: $SIZE
Maintainer: TidyDisk contributors <noreply@example.invalid>
Description: Free up disk space safely, with optional local AI review
 Finds caches, old kernels, unused packages, leftover installers and duplicate
 files, explains every item and removes only what you confirm.
EOF
mkdir -p "$OUT"
dpkg-deb --root-owner-group --build "$B" "$OUT/$PKG.deb" >/dev/null
echo "$OUT/$PKG.deb"
