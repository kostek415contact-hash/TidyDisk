"""Postep i szacowany czas (bez Qt - uzywane przez okno i przez tryb w tle)."""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import fsutil


def fmt_eta(sec: float) -> str:
    sec = max(0, int(sec))
    if sec < 60:
        return "mniej niż minuta"
    m = (sec + 30) // 60
    if m < 60:
        return f"ok. {m} min"
    return f"ok. {m // 60} h {m % 60:02d} min"


class ProgressTracker:
    """Procent i szacunkowy pozostaly czas z ulamka postepu (0..1) i czasu, ktory minal.
    update(f) -> (procent albo None gdy nieznany, tekst czasu albo ''). Szacunek zaczyna sie po 3% i 8 s,
    a pokazywany czas jest wygladzany, zeby nie skakal."""

    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self.reset()

    def reset(self) -> None:
        self.t0 = self.clock()
        self.last = 0.0
        self.smooth = None

    def update(self, f: float | None) -> tuple:
        if f is None or f < 0:
            return None, ""
        f = min(1.0, max(self.last, f))  # postep nie cofa sie
        self.last = f
        el = self.clock() - self.t0
        if f >= 1.0:
            return 100, ""
        if f < 0.03 or el < 8:
            return int(f * 100), "liczę czas …"
        rest = el * (1 - f) / f
        self.smooth = rest if self.smooth is None else 0.7 * self.smooth + 0.3 * rest
        return int(f * 100), fmt_eta(self.smooth)


SCANSTATS = Path.home() / ".local/share/tidydisk/scanstats.json"


def load_scanstats() -> dict:
    try:
        d = json.loads(SCANSTATS.read_text(encoding="utf-8"))
        return {k: int(v) for k, v in d.items() if isinstance(v, (int, float)) and v > 0}
    except (OSError, ValueError, AttributeError, OverflowError):
        return {}


def save_scanstats(d: dict) -> None:
    try:
        fsutil.atomic_write(SCANSTATS, json.dumps(d))
    except OSError:
        pass
