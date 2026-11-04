# Buduje tidydisk.exe (wersja konsolowa: skan i raport, bez usuwania). Wymaga: Python 3.11+ i `pip install pyinstaller`.
# Uruchom z korzenia repozytorium:  powershell -File packaging\windows\build-exe.ps1
$ErrorActionPreference = "Stop"
python -m PyInstaller --noconfirm --onefile --name tidydisk `
  --exclude-module PyQt6 --exclude-module tkinter `
  --paths . tidydisk\__main__.py
Write-Host "Gotowe: dist\tidydisk.exe  (uruchom: dist\tidydisk.exe scan)"
