# Buduje tidydisk.exe (PyInstaller): skan, raport i czyszczenie (jak na Linuksie).
# Uruchom z korzenia repozytorium:  powershell -File packaging\windows\build-exe.ps1
$ErrorActionPreference = "Stop"
python -m PyInstaller --noconfirm --onefile --name tidydisk `
  --exclude-module PyQt6 --exclude-module tkinter `
  --add-data "tidydisk\locale;tidydisk\locale" `
  --paths . packaging\windows\entry.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with code ($LASTEXITCODE)" }
Write-Host "Gotowe: dist\tidydisk.exe  (uruchom: dist\tidydisk.exe scan)"

# Wersja z oknem (PyQt6): wymaga `pip install PyQt6`. Na Windows tylko skan i raport, usuwanie jest zablokowane.
if ($env:BUILD_GUI -eq "1") {
  python -m PyInstaller --noconfirm --onefile --windowed --name tidydisk-gui `
    --exclude-module tkinter `
    --add-data "tidydisk\locale;tidydisk\locale" --add-data "data;data" `
    --paths . packaging\windows\entry_gui.py
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller (GUI) failed with code ($LASTEXITCODE)" }
  Write-Host "Gotowe: dist\tidydisk-gui.exe  (dwuklik uruchamia okno)"
}
