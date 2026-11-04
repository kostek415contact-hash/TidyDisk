"""Punkt wejscia okna dla PyInstaller (tidydisk-gui.exe). Na Windows okno dziala tylko do odczytu: skan i raport."""
import sys

from tidydisk.gui import main

if __name__ == "__main__":
    sys.exit(main())
