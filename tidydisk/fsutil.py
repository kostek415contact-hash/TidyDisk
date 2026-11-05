"""Male narzedzia plikowe: zapis atomowy z prawami 0600 (bez polowicznych plikow po zabiciu procesu)."""
from __future__ import annotations

import os
import secrets
import threading
from pathlib import Path


def atomic_write(path, text: str, mode: int = 0o600) -> None:
    """Zapisuje plik przez unikalny plik tymczasowy + os.replace. Rzuca OSError przy bledzie."""
    path = Path(os.path.realpath(path))  # dowiazanie (np. dotfiles) zostaje dowiazaniem, zapis idzie do celu
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}.{threading.get_ident()}.{secrets.token_hex(3)}")  # unikalny: rownolegle zapisy nie deptaja sobie po pliku
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        with os.fdopen(fd, "w", encoding="utf-8", errors="backslashreplace") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def csv_safe(v):
    """Komorka CSV zaczynajaca sie od = + - @ (albo tab/CR) bylaby w arkuszu formula: dopisujemy apostrof. Puste zostaja puste."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v
