"""Skan Windows (TYLKO ODCZYT): rozpoznaje znane miejsca z kb_windows.RULES i pokazuje ich rozmiary.

Pierwsze wydanie dla Windows niczego nie usuwa - patrz core.run_clean (blokada) i README. Bez zaleznosci od Qt;
wszystkie sciezki sa parametrami, wiec da sie to przetestowac na Linuksie na sztucznym drzewie katalogow."""
from __future__ import annotations

import os
from pathlib import Path

from . import kb, kb_windows


def _expand(home: str, pattern: str) -> list:
    """Rozwija wzorzec z reguly ("~/appdata/local/.../*/cache") na istniejace katalogi; '*' = jeden poziom,
    nazwy porownywane bez wielkosci liter (jak w NTFS)."""
    parts = [p for p in pattern.replace("\\", "/").split("/") if p]
    if not parts or parts[0] != "~":
        return []
    cur = [home]
    for seg in parts[1:]:
        nxt: list = []
        for base in cur:
            if seg == "*":
                try:
                    with os.scandir(base) as it:
                        nxt += [e.path for e in it if e.is_dir(follow_symlinks=False)]
                except OSError:
                    pass
                continue
            try:
                with os.scandir(base) as it:
                    nxt += [e.path for e in it if e.name.lower() == seg and e.is_dir(follow_symlinks=False)]
            except OSError:
                pass
        cur = nxt
        if not cur:
            return []
    return cur


_GROUPS = (
    ("temp", "Pliki tymczasowe", "Dane tymczasowe systemu i programów.", ("/temp", "/crashdumps", "/explorer")),
    ("browsers", "Przeglądarki", "Tylko cache stron; hasła, ciasteczka i historia są poza nim.",
     ("/edge/", "/chrome/", "/firefox/", "/brave", "/code/", "/discord/")),
    ("shaders", "Cache shaderów", "Skompilowane shadery gier i sterowników.", ("dxcache", "glcache", "d3dscache")),
    ("dev", "Narzędzia programistyczne", "Pobrane pakiety i zależności - pobiorą się ponownie.", ("",)),
)


def _group_of(rule: str) -> int:
    r = rule.lower()
    for i, (_k, _t, _d, needles) in enumerate(_GROUPS):
        if any(n and n in r for n in needles):
            return i
    return len(_GROUPS) - 1


def scan(home: str | None = None, size_of=None, status=lambda _m: None) -> list:
    """Zwraca liste core.Category (rating z bazy wiedzy Windows). `size_of(path)` domyslnie core.path_size."""
    from . import core  # tu, bo core importuje ten modul przy wyborze skanu
    home = str(home or Path.home())
    size_of = size_of or core.path_size
    base = kb.KnowledgeBase(home, [], system="windows")
    grouped: list = [[] for _ in _GROUPS]
    seen: set = set()
    for rule in kb_windows.RULES:
        pattern, rating, title = rule[0], rule[1], rule[2]
        if rating not in (kb_windows.SAFE, kb_windows.REVIEW):
            continue
        status(f"Skanuję: {title} …")
        for path in _expand(home, pattern):
            key = kb_windows.norm(path)
            if key in seen or kb_windows.is_protected(path):
                continue
            seen.add(key)
            size = size_of(path)
            if size <= 0:
                continue
            v = base.classify(path)
            ent = core.Entry(label=title, size=size, kind="path", paths=[path], note=path,
                             rating=v.rating, rule=v.rule, why=v.why,
                             what=f"{v.title} - {v.what}" if v.title else v.what)
            grouped[_group_of(pattern)].append(ent)
    cats = []
    for (key, title, desc, _n), entries in zip(_GROUPS, grouped):
        if entries:
            entries.sort(key=lambda e: -e.size)
            cats.append(core.Category(key, title, desc, False, entries))
    return cats


def refuse_message() -> str:
    return ("Usuwanie na Windows jest wyłączone w tej wersji (skan i raport działają). "
            "Włączę je dopiero po przetestowaniu na prawdziwym Windows 11.")
