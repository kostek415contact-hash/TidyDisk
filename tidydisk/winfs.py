"""Usuwanie plikow na Windows. Zasady bezpieczenstwa sa takie same jak na Linuksie, ale mechanizm inny:
nie ma dir_fd ani O_NOFOLLOW, wiec zamiast tego (1) sciezka musi byc 'prawdziwa' (realpath == sciezka: zaden skladnik
nie jest junction/dowiazaniem), (2) przy czyszczeniu dowiazania i junctiony sa usuwane jako same dowiazania, nigdy nie
sa przekraczane, (3) nigdy nie kasujemy korzenia dysku ani katalogu domowego.
Funkcje IO uzywaja tylko os/stat, wiec da sie je przetestowac na Linuksie (tam 'dowiazanie' = symlink)."""
from __future__ import annotations

import ntpath
import os
import stat
import subprocess

from . import kb_windows

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
MAX_DEPTH = 200


def is_reparse(st) -> bool:
    """Symlink albo junction/punkt ponownej analizy (OneDrive, junctiony)."""
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def bad_path(path) -> bool:
    if not isinstance(path, str) or not ntpath.isabs(path):
        return True
    return ntpath.basename(path.rstrip("\\/")) in ("", ".", "..") or "\0" in path


def is_drive_root(path: str) -> bool:
    n = kb_windows.norm(path)
    return len(n) <= 3 and n.endswith((":", ":/"))  # "c:" albo "c:/"


def same_real(path: str) -> bool:
    """Czy sciezka jest 'prawdziwa': realpath nie zmienia jej (poza wielkoscia liter i separatorami)."""
    return kb_windows.norm(os.path.realpath(path)) == kb_windows.norm(path)


def _clear_readonly(path: str) -> None:
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except PermissionError:
        _clear_readonly(path)
        os.unlink(path)


def remove_tree(path: str, errors: list, depth: int = 0) -> bool:
    """Usuwa katalog z cala zawartoscia. Dowiazania/junctiony usuwa jako same dowiazania (bez wchodzenia).
    Zwraca True, gdy katalog zniknal. Pliki zajete przez program sa pomijane z komunikatem."""
    if depth > MAX_DEPTH:
        errors.append(f"{path}: pominięto (zbyt głęboko zagnieżdżony katalog)")
        return False
    clean = True
    try:
        with os.scandir(path) as it:
            children = list(it)
    except FileNotFoundError:
        return True
    except OSError as ex:
        errors.append(f"{path}: {ex.strerror or ex}")
        return False
    for c in children:
        full = c.path
        try:
            st = c.stat(follow_symlinks=False)
            if is_reparse(st):
                if c.is_dir(follow_symlinks=False) and not stat.S_ISLNK(st.st_mode):
                    os.rmdir(full)  # junction: usuwa samo dowiazanie, nie cel
                else:
                    _unlink(full)
            elif stat.S_ISDIR(st.st_mode):
                if remove_tree(full, errors, depth + 1):
                    continue
                clean = False
            else:
                _unlink(full)
        except FileNotFoundError:
            continue
        except OSError as ex:
            errors.append(f"{full}: {_why(ex)}")
            clean = False
        except RecursionError:
            errors.append(f"{full}: pominięto (zbyt głęboko zagnieżdżony katalog)")
            clean = False
    if not clean:
        return False
    try:
        os.rmdir(path)
    except FileNotFoundError:
        return True
    except OSError as ex:
        errors.append(f"{path}: {_why(ex)}")
        return False
    return True


def _why(ex: OSError) -> str:
    if isinstance(ex, PermissionError) or getattr(ex, "winerror", 0) in (5, 32, 33):
        return "plik używany przez program lub brak uprawnień - pominięto"
    return ex.strerror or str(ex)


def remove_item(path: str, errors: list) -> None:
    """Plik albo katalog (z zawartoscia) - bez podazania za dowiazaniami."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as ex:
        errors.append(f"{path}: {_why(ex)}")
        return
    try:
        if is_reparse(st):
            if stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode):
                os.rmdir(path)
            else:
                _unlink(path)
        elif stat.S_ISDIR(st.st_mode):
            remove_tree(path, errors)
        else:
            _unlink(path)
    except FileNotFoundError:
        pass
    except OSError as ex:
        errors.append(f"{path}: {_why(ex)}")


_PS = ("Add-Type -AssemblyName Microsoft.VisualBasic; $p=$env:TIDYDISK_PATH; "
       "if (Test-Path -LiteralPath $p -PathType Container) "
       "{[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($p,'OnlyErrorDialogs','SendToRecycleBin')} "
       "else {[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($p,'OnlyErrorDialogs','SendToRecycleBin')}")


def recycle(path: str, errors: list, run=None) -> None:
    """Przenosi do Kosza (mozna przywrocic). Sciezka idzie przez zmienna srodowiskowa, nie przez wiersz polecenia."""
    env = dict(os.environ, TIDYDISK_PATH=path)
    try:
        r = (run or subprocess.run)(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS],
                                    capture_output=True, text=True, timeout=120, env=env)
    except (OSError, subprocess.SubprocessError) as ex:
        errors.append(f"{path}: nie mogę przenieść do Kosza ({ex})")
        return
    if r.returncode != 0:
        errors.append(f"{path}: przeniesienie do Kosza nie powiodło się (kod {r.returncode})")
