#!/usr/bin/env bash
# Uruchamia wersje Windows programu na Linuksie przez Wine (do szybkiego sprawdzenia skanu; to NIE jest prawdziwy Windows).
# Wymaga: wine (sudo dnf install wine), curl, unzip. Pobiera oficjalny "embeddable" Python dla Windows z python.org.
set -euo pipefail
PYVER="${PYVER:-3.13.1}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${WORK:-$HOME/.cache/tidydisk-wine}"
export WINEPREFIX="$WORK/prefix" WINEDEBUG=-all
command -v wine >/dev/null || { echo "Brak wine: sudo dnf install wine"; exit 1; }
mkdir -p "$WORK"
if [[ ! -f "$WORK/py/python.exe" ]]; then
  curl -fL "https://www.python.org/ftp/python/$PYVER/python-$PYVER-embed-amd64.zip" -o "$WORK/py.zip"
  mkdir -p "$WORK/py" && unzip -qo "$WORK/py.zip" -d "$WORK/py"
  # embeddable Python ignoruje PYTHONPATH - dopisz katalog programu do pliku ._pth
  PTH="$(ls "$WORK"/py/python*._pth)"
  grep -q "$(winepath -w "$HERE")" "$PTH" || echo "$(winepath -w "$HERE")" >> "$PTH"
fi
PY="wine $WORK/py/python.exe"
echo "== wersja i system =="; $PY -c "import tidydisk, tidydisk.osal as o; print(tidydisk.__version__, o.SYSTEM)"
echo "== dyski Windows ==";   $PY -c "from tidydisk import disks; [print(d.name, d.kind, d.size, d.parts[0].fstype) for d in disks.list_disks()]"
echo "== status ==";          $PY -m tidydisk status || true
echo "== skan (tylko odczyt) =="; $PY -m tidydisk scan || true
echo "Uwaga: Wine to nie Windows. Wynik potwierdza, ze kod sie uruchamia i skan nie wywala wyjatkow; prawdziwy test to Windows 11."
