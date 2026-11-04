"""Historia wolnego miejsca: jeden maly punkt na skan (data, zajete/calosc per dysk, ile bezpiecznie do odzyskania)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

MAX_POINTS = 2000
MIN_GAP = 3600  # nie czesciej niz raz na godzine


def _file(directory) -> Path:
    return Path(directory or Path.home() / ".local" / "share" / "tidydisk") / "space.json"


def load(directory=None) -> list:
    try:
        data = json.loads(_file(directory).read_text(encoding="utf-8"))
        return [p for p in data if isinstance(p, dict) and "ts" in p and "disks" in p] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def record(disks: dict, safe: int = 0, directory=None, now: float | None = None, force: bool = False) -> bool:
    """disks = {punkt: (zajete, calosc)}. Zwraca True, gdy zapisano nowy punkt."""
    now = time.time() if now is None else now
    pts = load(directory)
    if pts and not force and now - pts[-1]["ts"] < MIN_GAP:
        return False
    pts.append({"ts": int(now), "disks": {m: [int(u), int(t)] for m, (u, t) in disks.items()}, "safe": int(safe)})
    try:
        f = _file(directory)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(pts[-MAX_POINTS:], fh)
        os.replace(tmp, f)
        return True
    except OSError:
        return False


def series(points: list, mount: str | None = None) -> list:
    """[(ts, zajete)] dla jednego dysku (domyslnie pierwszego, ktory wystepuje)."""
    if not points:
        return []
    mount = mount or next(iter(points[-1]["disks"]), None)
    return [(p["ts"], p["disks"][mount][0]) for p in points if mount in p["disks"]]


def growth(points: list, days: int = 30, mount: str | None = None) -> tuple:
    """(przyrost_bajtow, ile_dni_obejmuje) miedzy najstarszym punktem z ostatnich `days` dni a najnowszym."""
    s = series(points, mount)
    if len(s) < 2:
        return 0, 0
    cutoff = s[-1][0] - days * 86400
    old = next((x for x in s if x[0] >= cutoff), s[0])
    return s[-1][1] - old[1], max(1, (s[-1][0] - old[0]) // 86400)
