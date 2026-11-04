"""Punkt wejscia dla PyInstaller: skrypt uruchamiany bezposrednio nie ma pakietu nadrzednego, wiec import bezwzgledny.
Wersja .exe jest konsolowa (bez okna Qt): bez argumentow pokazuje status dysku."""
import sys

from tidydisk.__main__ import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("status")
    main()
