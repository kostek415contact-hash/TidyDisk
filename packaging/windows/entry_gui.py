"""Punkt wejscia okna dla PyInstaller (tidydisk-gui.exe, bez konsoli). Z argumentem (np. `notify`, `ai`, `scan`) dziala jak
program konsolowy, ale bez okna - tak uruchamia go Harmonogram zadan; bez argumentow otwiera okno.
Program okienkowy nie ma stdout/stderr (sa None), wiec kierujemy je w nicosc."""
import os
import sys

for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from tidydisk.__main__ import main
        main()
    else:
        from tidydisk.gui import main
        sys.exit(main())
