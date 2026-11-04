"""Wykrywanie plikow otwartych teraz przez dzialajace programy (z /proc/*/fd), zeby ostrzec przed usunieciem."""
from __future__ import annotations

import bisect
import os


def open_paths(proc: str = "/proc") -> dict:
    """{sciezka: nazwa_procesu} dla zwyklych plikow i folderow otwartych przez procesy, ktore wolno nam obejrzec."""
    out: dict = {}
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return out
    for pid in pids:
        fd_dir = os.path.join(proc, pid, "fd")
        try:
            fds = os.listdir(fd_dir)
        except OSError:  # cudzy proces albo juz zakonczony
            continue
        name = ""
        for fd in fds:
            try:
                target = os.readlink(os.path.join(fd_dir, fd))
            except OSError:
                continue
            if not target.startswith("/") or (target.startswith(("/dev/", "/proc/", "/sys/", "/run/")) and not target.startswith("/run/media/")) or target.endswith(" (deleted)"):
                continue
            if not name:
                try:
                    with open(os.path.join(proc, pid, "comm"), encoding="utf-8", errors="replace") as f:
                        name = f.read().strip()
                except OSError:
                    name = pid
            out.setdefault(target, name)
    return out


def users_of(path: str, opened: dict) -> list:
    """Nazwy programow, ktore maja otwarty `path` albo cos wewnatrz niego (dla folderu)."""
    base = path.rstrip("/")
    names = set()
    if base in opened:
        names.add(opened[base])
    keys = sorted(opened)
    i = bisect.bisect_left(keys, base + "/")  # tylko klucze wewnatrz folderu (sasiednie nazwy typu 'base.bak' leza gdzie indziej)
    while i < len(keys) and keys[i].startswith(base + "/"):
        names.add(opened[keys[i]])
        i += 1
    return sorted(names)
