"""Male narzedzia plikowe: zapis atomowy z prawami 0600 (bez polowicznych plikow po zabiciu procesu)."""
from __future__ import annotations

import os
from pathlib import Path


def atomic_write(path, text: str, mode: int = 0o600) -> None:
    """Zapisuje plik przez unikalny plik tymczasowy + os.replace. Rzuca OSError przy bledzie."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
