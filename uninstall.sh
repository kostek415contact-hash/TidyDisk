#!/usr/bin/env bash
# Usuwa TidyDisk zainstalowany przez install.sh.
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"

# najpierw wylacz timery uzytkownika (inaczej zostaja i padaja po usunieciu programu)
if [[ -x "$PREFIX/bin/tidydisk" ]]; then
  "$PREFIX/bin/tidydisk" schedule disable >/dev/null 2>&1 || true
  "$PREFIX/bin/tidydisk" schedule disable --ai >/dev/null 2>&1 || true
fi
rm -rf "$PREFIX/share/tidydisk"
rm -f  "$PREFIX/bin/tidydisk" \
       "$PREFIX/share/applications/tidydisk.desktop" \
       "$PREFIX/share/metainfo/tidydisk.metainfo.xml" \
       "$PREFIX/share/icons/hicolor/scalable/apps/tidydisk.svg"
rm -f "$PREFIX"/share/icons/hicolor/*x*/apps/tidydisk.png
rm -f "$PREFIX/share/icons/hicolor/icon-theme.cache"

command -v update-desktop-database >/dev/null && update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
command -v kbuildsycoca6          >/dev/null && kbuildsycoca6 >/dev/null 2>&1 || true

if [[ -e /usr/local/lib/tidydisk ]]; then
  read -rp "Usunąć też skaner administratora (sudo)? [T/n] " ans || ans=n
  if ! [[ "$ans" =~ ^[nN] ]]; then
    sudo rm -rf /usr/local/lib/tidydisk
    { rpm -q tidydisk || dpkg -s tidydisk; } >/dev/null 2>&1 || sudo rm -f /usr/share/polkit-1/actions/org.tidydisk.admin-scan.policy
  fi
fi

echo "TidyDisk usuniety."
