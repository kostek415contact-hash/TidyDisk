"""Migawki btrfs (snapper / Timeshift) - tylko odczyt i informacja. Program niczego tu nie usuwa."""
from __future__ import annotations

import os
import shutil

from . import osal


def btrfs_mounted(mounts_file: str = "/proc/mounts") -> bool:
    try:
        with open(mounts_file, encoding="utf-8") as f:
            return any(ln.split()[2:3] == ["btrfs"] for ln in f)
    except OSError:
        return False


def _count_dirs(path: str, numeric: bool) -> int | None:
    try:
        names = os.listdir(path)
    except OSError:
        return None  # zwykle: katalog nalezy do roota
    return sum(1 for n in names if (n.isdigit() or not numeric))


def detect(mounts_file: str = "/proc/mounts", snapper_dir: str = "/.snapshots", timeshift_dir: str = "/timeshift/snapshots") -> dict:
    """{'btrfs': bool, 'tool': 'snapper'|'timeshift'|'', 'count': int|None, 'text': str}"""
    bt = btrfs_mounted(mounts_file) and not osal.is_windows()  # Windows (takze Wine): brak migawek btrfs
    out = {"btrfs": bt, "tool": "", "count": None, "text": ""}
    if not bt:
        return out
    if os.path.isdir(snapper_dir) or shutil.which("snapper"):
        out["tool"], out["count"] = "snapper", _count_dirs(snapper_dir, True)
    elif os.path.isdir(timeshift_dir) or shutil.which("timeshift"):
        out["tool"], out["count"] = "timeshift", _count_dirs(timeshift_dir, False)
    if out["tool"]:
        n = out["count"]
        out["text"] = (f"btrfs: {out['tool']}, migawek: {n}" if n is not None else
                       f"btrfs: {out['tool']} (lista migawek wymaga roota: sudo {out['tool']} list)")
        out["text"] += ". Usunięte pliki zwolnią miejsce dopiero, gdy żadna migawka ich nie trzyma."
    else:
        out["text"] = "btrfs: nie wykryłem snapper ani Timeshift, ale migawki ręczne mogą trzymać dane."
    return out
