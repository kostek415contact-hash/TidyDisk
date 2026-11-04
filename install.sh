#!/usr/bin/env bash
# Instalacja TidyDisk dla biezacego uzytkownika (bez roota).
# Po instalacji program jest w menu aplikacji (Narzedzia / System) i pod
# komenda `tidydisk`.
#
#   ./install.sh            instalacja do ~/.local
#   PREFIX=/usr/local sudo -E ./install.sh   instalacja systemowa
set -euo pipefail

# Skaner administratora (skan calego systemu przez pkexec) jest kopia nalezaca do roota,
# zeby kod z katalogu uzytkownika nigdy nie dostal uprawnien roota.
install_admin() {
  local here; here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  sudo rm -rf /usr/local/lib/fedora-cleaner /usr/share/polkit-1/actions/org.fedoracleaner.admin-scan.policy  # po zmianie nazwy
  sudo install -d -m 755 -o root -g root /usr/local/lib/tidydisk
  # tresc idzie rura prosto do instalacji jako root (bez pliku tymczasowego, ktory mozna podmienic)
  ( cd "$here" && /usr/bin/python3 -I -c '
import sys; sys.path.insert(0, ".")
from tidydisk import scanner, __version__
sys.stdout.write(scanner.build_admin_source("/", "", (), argv=True, version=__version__))' ) \
    | sudo install -m 755 -o root -g root /dev/stdin /usr/local/lib/tidydisk/admin_scan.py
  # regula polkit tylko dla tego jednego skryptu (tylko odczyt); bez niej pkexec tez dziala, z ogolnym pytaniem o haslo
  if ! { rpm -q tidydisk || dpkg -s tidydisk; } >/dev/null 2>&1; then  # przy pakiecie RPM/DEB regule dostarcza pakiet
    sudo install -d -m 755 /usr/share/polkit-1/actions
    sudo install -m 644 -o root -g root "$here/data/org.tidydisk.admin-scan.policy" /usr/share/polkit-1/actions/org.tidydisk.admin-scan.policy
  fi
  echo "Zainstalowano skaner administratora: /usr/local/lib/tidydisk/admin_scan.py (+ regula polkit)"
}
if [[ "${1:-}" == "--admin" ]]; then install_admin; exit 0; fi

PREFIX="${PREFIX:-$HOME/.local}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPDIR="$PREFIX/share/tidydisk"

if [[ "${SKIP_DEP_CHECK:-0}" != "1" ]] && ! /usr/bin/python3 -c 'import PyQt6.QtWidgets' 2>/dev/null; then
  echo "Brakuje PyQt6 (pakiet python3-pyqt6)."
  if command -v apt-get >/dev/null 2>&1 && ! command -v dnf >/dev/null 2>&1; then PKG_CMD="apt-get install -y"; else PKG_CMD="dnf install -y"; fi
  read -rp "Zainstalowac teraz przez sudo ${PKG_CMD%% *}? [T/n] " ans || ans=n
  if [[ "$ans" =~ ^[nN]$ ]]; then
    echo "Przerwano. Zainstaluj: sudo ${PKG_CMD% -y} python3-pyqt6"
    exit 1
  fi
  sudo $PKG_CMD python3-pyqt6
fi

echo "Instaluje do $PREFIX ..."
# po zmianie nazwy (Fedora Cleaner -> TidyDisk): usun stara instalacje; ustawienia i dane program przenosi sam
rm -rf "$PREFIX/share/fedora-cleaner"
rm -f "$PREFIX/bin/fedora-cleaner" "$PREFIX/share/applications/fedora-cleaner.desktop" "$PREFIX"/share/icons/hicolor/*/apps/fedora-cleaner.*
rm -rf "$APPDIR"
ICONS="$PREFIX/share/icons/hicolor"
mkdir -p "$APPDIR" "$PREFIX/bin" "$PREFIX/share/applications" "$ICONS/scalable/apps"
cp -r "$HERE/tidydisk" "$HERE/data" "$APPDIR/"
find "$APPDIR" -name __pycache__ -type d -prune -exec rm -rf {} +

cat > "$PREFIX/bin/tidydisk" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$APPDIR\${PYTHONPATH:+:\$PYTHONPATH}"
exec /usr/bin/python3 -m tidydisk "\$@"
EOF
chmod +x "$PREFIX/bin/tidydisk"

# ikony: PNG w kilku rozmiarach + SVG (motyw hicolor)
install -Dm644 "$HERE/data/tidydisk.svg" "$ICONS/scalable/apps/tidydisk.svg"
for d in "$HERE"/data/icons/*x*/; do
  size="$(basename "$d")"
  install -Dm644 "$d/tidydisk.png" "$ICONS/$size/apps/tidydisk.png"
done
ICON_FILE="$ICONS/256x256/apps/tidydisk.png"

# W .desktop wpisujemy PELNA sciezke ikony - dziala od razu, bez odswiezania cache motywu.
sed -e "s|^Exec=tidydisk|Exec=$PREFIX/bin/tidydisk|" \
    -e "s|^Icon=.*|Icon=$ICON_FILE|" \
  "$HERE/data/tidydisk.desktop" > "$PREFIX/share/applications/tidydisk.desktop"
chmod 644 "$PREFIX/share/applications/tidydisk.desktop"
install -Dm644 "$HERE/data/tidydisk.metainfo.xml" "$PREFIX/share/metainfo/tidydisk.metainfo.xml"

# odswiezenie menu i ikon (kazde opcjonalne). Nieaktualny icon-theme.cache potrafi
# ukryc nowe ikony, wiec go usuwamy zamiast budowac od nowa.
rm -f "$ICONS/icon-theme.cache"
touch "$ICONS" 2>/dev/null || true
command -v update-desktop-database >/dev/null && update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
command -v kbuildsycoca6          >/dev/null && kbuildsycoca6 >/dev/null 2>&1 || true
command -v kbuildsycoca5          >/dev/null && kbuildsycoca5 >/dev/null 2>&1 || true

if [[ "${SKIP_ADMIN:-0}" != "1" ]]; then
  read -rp "Zainstalować skaner administratora (sudo, potrzebny do skanu całego systemu)? [T/n] " ans || ans=n
  [[ "$ans" =~ ^[nN]$ ]] || install_admin
fi

echo "Gotowe. Uruchom z menu aplikacji (\"TidyDisk\") albo komenda: tidydisk"
case ":$PATH:" in
  *":$PREFIX/bin:"*) ;;
  *) echo "Uwaga: $PREFIX/bin nie jest w PATH - z menu dziala, z terminala podaj pelna sciezke." ;;
esac
