"""Co sie zmienilo od ostatniego skanu: nowe duze foldery i foldery, ktore urosly. Bez Qt."""
from __future__ import annotations

import json
import time

from . import fsutil, osal

DIR = osal.data_dir()
SNAPSHOT = DIR / "snapshot.json"
LAST = DIR / "changes.json"
MIN_BYTES = 100 * 1024 * 1024  # mniejsze zmiany pomijamy
MIN_GROWTH = 0.2  # i wzrost mniejszy niz 20%
KEEP_NODES = 3000


def snapshot_from(nodes: dict) -> dict:
    """{sciezka: rozmiar} dla najwiekszych folderow."""
    big = sorted(((v[0], p) for p, v in nodes.items() if v and v[0] >= MIN_BYTES // 2), reverse=True)[:KEEP_NODES]
    return {p: int(s) for s, p in big}


def diff(old: dict, new: dict) -> list:
    """[(sciezka, stary_rozmiar, nowy_rozmiar)] malejaco wg przyrostu; stary 0 = nowy folder."""
    out = []
    for p, s in new.items():
        o = old.get(p, 0)
        grow = s - o
        if grow >= MIN_BYTES and (o == 0 or grow / max(o, 1) >= MIN_GROWTH):
            out.append((p, o, s))
    out.sort(key=lambda t: t[1] - t[2])
    # zostaje najwyzszy folder z lancucha (nie raportujemy tez wszystkich jego podfolderow)
    kept: list = []
    for p, o, s in out:
        if not any(p.startswith((q.rstrip("/\\") + "/",) + ((q.rstrip("/\\") + "\\",) if osal.is_windows() else ())) for q, _o, _s in kept):
            kept.append((p, o, s))
    return kept


def load_snapshot() -> dict:
    try:
        raw = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        return {k: int(v) for k, v in raw.get("n", {}).items()} if isinstance(raw, dict) else {}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def record(nodes: dict) -> list:
    """Porownuje z poprzednim skanem, zapisuje nowa migawke i liste zmian; zwraca liste zmian."""
    old, new = load_snapshot(), snapshot_from(nodes)
    ch = diff(old, new) if old else []
    try:
        fsutil.atomic_write(SNAPSHOT, json.dumps({"t": int(time.time()), "n": new}))
        fsutil.atomic_write(LAST, json.dumps({"t": int(time.time()), "first": not old, "c": ch}))
    except OSError:
        pass
    return ch


def last() -> dict:
    try:
        return json.loads(LAST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def describe(data: dict | None = None, limit: int = 8, home: str = "") -> str:
    d = data if data is not None else last()
    if not d:
        return "Brak porównania - zrób skan (potem kolejny, żeby było z czym porównać)."
    if d.get("first"):
        return "Pierwszy zapisany skan - porównanie będzie przy następnym."
    c = d.get("c") or []
    if not c:
        return "Od ostatniego skanu nie przybyło nic dużego."
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(d.get("t", 0)))
    lines = [f"Zmiany od poprzedniego skanu (stan z {when}):"]
    for p, o, s in c[:limit]:
        p = p.replace(home, "~") if home else p
        lines.append(f"  {'nowy' if not o else 'urósł'}: {p}  +{(s - o) / 2**20:.0f} MB")
    if len(c) > limit:
        lines.append(f"  … i {len(c) - limit} więcej")
    return "\n".join(lines)
