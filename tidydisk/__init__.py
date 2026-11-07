"""TidyDisk - czyszczenie dysku (Linux, Windows): bezpiecznie, z wyjaśnieniem każdej pozycji."""

__version__ = "2.23.12"

from . import legacy as _legacy  # noqa: E402

_legacy.migrate_dirs()  # stare ~/.config|~/.local/share/fedora-cleaner -> tidydisk, zanim ktorykolwiek modul zapamieta sciezki
