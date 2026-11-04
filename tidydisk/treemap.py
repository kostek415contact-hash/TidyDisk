"""Mapa dysku: uklad prostokatow proporcjonalnych do rozmiaru (algorytm 'squarified treemap'). Bez Qt."""
from __future__ import annotations

import os


def _worst(row: list, side: float) -> float:
    s = sum(row)
    if s <= 0 or side <= 0:
        return float("inf")
    return max(max(side * side * r / (s * s), s * s / (side * side * r)) for r in row if r > 0)


def squarify(sizes: list, x: float, y: float, w: float, h: float) -> list:
    """Prostokaty (x, y, w, h) w kolejnosci wejscia; sizes malejaco posortowane daje najladniejszy uklad.
    Pozycje o rozmiarze <= 0 dostaja prostokat zerowy."""
    n = len(sizes)
    out: list = [(x, y, 0.0, 0.0)] * n
    idx = [i for i in range(n) if sizes[i] > 0]
    total = float(sum(sizes[i] for i in idx))
    if not idx or w <= 0 or h <= 0:
        return out
    area = w * h
    vals = [(i, sizes[i] / total * area) for i in idx]
    rx, ry, rw, rh = x, y, w, h
    row: list = []
    k = 0
    while k < len(vals):
        side = min(rw, rh)
        cand = row + [vals[k]]
        if not row or _worst([v for _i, v in cand], side) <= _worst([v for _i, v in row], side):
            row = cand
            k += 1
            continue
        rx, ry, rw, rh = _lay(row, out, rx, ry, rw, rh)
        row = []
    if row:
        _lay(row, out, rx, ry, rw, rh)
    return out


def _lay(row: list, out: list, x: float, y: float, w: float, h: float) -> tuple:
    s = sum(v for _i, v in row)
    if w >= h:  # kolumna po lewej
        cw = s / h if h else 0.0
        cy = y
        for i, v in row:
            ch = v / cw if cw else 0.0
            out[i] = (x, cy, cw, ch)
            cy += ch
        return x + cw, y, w - cw, h
    rh = s / w if w else 0.0
    cx = x
    for i, v in row:
        cw = v / rh if rh else 0.0
        out[i] = (cx, y, cw, rh)
        cx += cw
    return x, y + rh, w, h - rh


def children_of(nodes: dict, base: str, limit: int = 40) -> list:
    """Bezposrednie podfoldery `base` ze skanu: [(sciezka, rozmiar, ocena, tytul)] malejaco; reszte laczy w 'Pozostałe'."""
    base = base.rstrip("/") or "/"
    kids = []
    for p, (size, _files, rating, title, _d) in nodes.items():
        if p != base and os.path.dirname(p.rstrip("/")) == base and size > 0:
            kids.append((p, int(size), rating, title))
    kids.sort(key=lambda k: -k[1])
    if len(kids) > limit:
        rest = sum(k[1] for k in kids[limit:])
        kids = kids[:limit] + [("", rest, "review", "Pozostałe (%d)" % (len(kids) - limit))]
    return kids


def top_base(nodes: dict, roots=()) -> str:
    """Folder, od ktorego zaczyna sie mapa: pierwszy z roots, ktory jest w skanie, inaczej najplytszy folder."""
    for r in roots:
        if r in nodes:
            return r
    if not nodes:
        return ""
    return min(nodes, key=lambda p: (p.count("/") + p.count("\\"), -nodes[p][0]))
