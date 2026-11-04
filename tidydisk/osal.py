"""Warstwa systemowa (OS abstraction layer): jedno miejsce na rzeczy zalezne od systemu (Linux / Windows / macOS).

Na Linuksie wszystkie funkcje robia dokladnie to, co dawniej kod wprost. Na innych systemach zwracaja bezpieczne
odpowiedniki albo None/False (np. brak blokady, brak priorytetu), a wywolujacy to obsluguje."""
from __future__ import annotations

import os
import shutil
import sys

SYSTEM = "windows" if sys.platform.startswith("win") else "macos" if sys.platform == "darwin" else "linux"


def is_windows() -> bool:
    return SYSTEM == "windows"


def alloc_size(st) -> int:
    """Rozmiar zajety na dysku z wyniku stat: bloki (Unix) albo rozmiar logiczny (Windows, brak st_blocks)."""
    blocks = getattr(st, "st_blocks", None)
    return blocks * 512 if blocks is not None else int(st.st_size)


def kernel_release() -> str:
    uname = getattr(os, "uname", None)
    if uname is not None:
        return uname().release
    import platform
    return platform.release()


def is_admin() -> bool:
    geteuid = getattr(os, "geteuid", None)
    if geteuid is not None:
        return geteuid() == 0
    if is_windows():
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            return False
    return False


def lower_priority() -> None:
    """Niski priorytet procesu (praca w tle nie ma przeszkadzac)."""
    nice = getattr(os, "nice", None)
    if nice is not None:
        try:
            nice(15)
        except OSError:
            pass
        return
    if is_windows():
        try:
            import ctypes
            BELOW_NORMAL = 0x00004000
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), BELOW_NORMAL)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def try_lock(fileobj) -> bool:
    """Wylaczna blokada otwartego pliku bez czekania; False, gdy ktos inny ja trzyma."""
    try:
        import fcntl
    except ImportError:
        fcntl = None
    if fcntl is not None:
        try:
            fcntl.flock(fileobj, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
    try:
        import msvcrt
        fileobj.seek(0)
        msvcrt.locking(fileobj.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
        return True
    except ImportError:
        return True  # brak mechanizmu blokady: nie blokujemy (lepsze niz nie uruchomic)
    except OSError:
        return False


def disk_usage(path: str) -> tuple:
    """(uzyte, razem) bajtow dla punktu montowania; statvfs na Unixie (zgodnie z df), shutil gdzie indziej."""
    statvfs = getattr(os, "statvfs", None)
    if statvfs is not None:
        st = statvfs(path)
        total = st.f_blocks * st.f_frsize
        return total - st.f_bfree * st.f_frsize, total
    u = shutil.disk_usage(path)
    return u.used, u.total


APP_DIR = "tidydisk"


def config_dir() -> "Path":
    """Katalog ustawien: Linux ~/.config/tidydisk, Windows %APPDATA%\\TidyDisk, macOS ~/Library/Application Support/TidyDisk."""
    from pathlib import Path
    if is_windows():
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "TidyDisk"
    if SYSTEM == "macos":
        return Path.home() / "Library" / "Application Support" / "TidyDisk"
    return Path.home() / ".config" / APP_DIR


def data_dir() -> "Path":
    """Katalog danych (pamiec AI, historia, cache): Linux ~/.local/share/tidydisk, Windows %LOCALAPPDATA%\\TidyDisk."""
    from pathlib import Path
    if is_windows():
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "TidyDisk"
    if SYSTEM == "macos":
        return Path.home() / "Library" / "Application Support" / "TidyDisk"
    return Path.home() / ".local" / "share" / APP_DIR
