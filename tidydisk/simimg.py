"""Podobne (nie identyczne) zdjecia: skrot roznicowy dHash 64 bity + grupowanie po odleglosci Hamminga.

Czysty Python. Wartosci szarosci 9x8 dostarcza warstwa Qt (widgets.gray9x8).
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def dhash(gray: list) -> int:
    """gray = 72 wartosci (8 wierszy po 9). Bit = czy piksel jest jasniejszy od sasiada po prawej."""
    bits = 0
    for r in range(8):
        for c in range(8):
            bits = (bits << 1) | (1 if gray[r * 9 + c] > gray[r * 9 + c + 1] else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def group(items: list, max_dist: int = 3) -> list:
    """items = [(klucz, hash)] -> lista grup (listy kluczy, >= 2). Odleglosc <= max_dist (0-8).

    Zasada szufladkowa: przy 9 kawalkach po <=8 bitow odleglosc <= 8 zostawia co najmniej jeden kawalek rowny,
    wiec porownujemy tylko elementy z tego samego koszyka (zamiast wszystkich par)."""
    max_dist = max(0, min(8, max_dist))
    parent = list(range(len(items)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    buckets: dict = {}
    for i, (_k, h) in enumerate(items):
        for part in range(9):
            buckets.setdefault((part, (h >> (part * 7)) & 0x7F if part < 9 else 0), []).append(i)
    seen: set = set()
    for members in buckets.values():
        if len(members) < 2 or len(members) > 400:  # ogromne koszyki (np. jednolite tla) pomijamy
            continue
        for x in range(len(members)):
            for y in range(x + 1, len(members)):
                i, j = members[x], members[y]
                if (i, j) in seen:
                    continue
                seen.add((i, j))
                if hamming(items[i][1], items[j][1]) <= max_dist:
                    parent[find(i)] = find(j)
    groups: dict = {}
    for i, (k, _h) in enumerate(items):
        groups.setdefault(find(i), []).append(k)
    return [g for g in groups.values() if len(g) >= 2]


def weaker_copies(group_info: list) -> list:
    """group_info = [(sciezka, szer, wys, rozmiar, mtime)] -> sciezki do odznaczenia/usuniecia: wszystko poza
    najlepsza kopia (najwieksza rozdzielczosc, potem rozmiar, potem starszy plik)."""
    best = max(group_info, key=lambda g: (g[1] * g[2], g[3], -g[4]))
    return [g[0] for g in group_info if g is not best]


def load_cache(path: str) -> dict:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return {k: v for k, v in d.items() if isinstance(k, str) and isinstance(v, list) and len(v) == 3}
    except (OSError, ValueError, AttributeError):
        return {}


def save_cache(path: str, cache: dict, keep: set) -> None:
    data = {k: v for k, v in cache.items() if k in keep}
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except OSError:
        pass
