# Buduje tidydisk.exe (wersja konsolowa: skan i raport, bez usuwania). Wymaga: Python 3.11+ i `pip install pyinstaller`.
# Uruchom z korzenia repozytorium:  powershell -File packaging\windows\build-exe.ps1
$ErrorActionPreference = "Stop"
python -m PyInstaller --noconfirm --onefile --name tidydisk `
  --exclude-module PyQt6 --exclude-module tkinter `
  --paths . packaging\windows\entry.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with code ($LASTEXITCODE)" }
Write-Host "Gotowe: dist\tidydisk.exe  (uruchom: dist\tidydisk.exe scan)"
