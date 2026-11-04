"""Reguly tak/nie: co program w ogole moze proponowac do usuniecia (Ustawienia -> Reguly).

Kategoria pozycji jest ustalana z rozszerzenia i powodow podanych przez algorytm. Wylaczona kategoria dziala
twardo: pozycja nie trafia na liste (ani od algorytmu, ani od AI), a model dostaje informacje, czego nie ruszac.
Bez zaleznosci od Qt.
"""
from __future__ import annotations

import os

from . import kb

# (klucz, etykieta, podpowiedz, grupa)
RULES = [
    ("iso", "Obrazy dysków (.iso, .img)", "Zwykle pobrane do jednorazowej instalacji, ale bywają potrzebne ponownie.", "Pliki"),
    ("installers", "Instalatory (.rpm, .deb, AppImage, .exe, .msi, .run)", "Zwłaszcza gdy program jest już zainstalowany.", "Pliki"),
    ("archives", "Archiwa (.zip, .7z, .rar, .tar.gz …)", "Tylko te w Pobranych i podobnych miejscach.", "Pliki"),
    ("partial", "Niedokończone pobrania (.part, .crdownload)", "", "Pliki"),
    ("tempbak", "Pliki tymczasowe i kopie (.tmp, .bak, .old, nazwa kończąca się ~)", "", "Pliki"),
    ("logs", "Logi (.log)", "", "Pliki"),
    ("coredumps", "Zrzuty pamięci po awarii (core.NNN)", "", "Pliki"),
    ("video", "Filmy (.mkv, .mp4, .avi, .mov …)", "Wyłącz, jeśli filmy w Pobranych to Twoja kolekcja.", "Pliki"),
    ("duplicates", "Identyczne kopie plików", "Zostaje jedna kopia - najstarsza lub ta w lepszym miejscu.", "Powtórzenia"),
    ("versions", "Starsze wersje i numerowane kopie (instalator 1.2.8 obok 1.2.9, „nazwa (1).zip”)", "Zostaje najnowsza wersja albo oryginał.", "Powtórzenia"),
    ("extracted", "Archiwa rozpakowane obok", "Archiwum, którego zawartość leży już obok rozpakowana.", "Powtórzenia"),
    ("builddirs", "Foldery do odtworzenia (build, node_modules, Library, target …)", "Narzędzie zbuduje je ponownie.", "Foldery"),
    ("cache", "Cache i miejsca odtwarzane przez program", "Przeglądarki, miniatury, shadercache itp.", "Foldery"),
    ("old_review", "Stare rzeczy w miejscach „zwykle zbędnych”", "Pobrane, tymczasowe - gdy sam wiek i rozmiar wskazują na zbędność.", "Foldery"),
    ("mine", "Pozwól proponować też z moich plików (Dokumenty, Zdjęcia …)", "Tylko przy konkretnym sygnale, np. duplikat. Wyłącz = nigdy.", "Moje pliki"),
]
KEYS = [r[0] for r in RULES]
LABELS = {r[0]: r[1] for r in RULES}
SHORT = {"iso": "pliki ISO/IMG", "installers": "instalatory", "archives": "archiwa", "partial": "niedokończone pobrania",
         "tempbak": "pliki tymczasowe i kopie", "logs": "logi", "coredumps": "zrzuty pamięci", "video": "filmy",
         "duplicates": "identyczne kopie", "versions": "starsze wersje i numerowane kopie", "extracted": "archiwa rozpakowane obok",
         "builddirs": "foldery do odtworzenia (build, node_modules…)", "cache": "cache",
         "old_review": "stare rzeczy w miejscach zwykle zbędnych", "mine": "moje pliki (Dokumenty, Zdjęcia…)"}

VIDEO = set("mkv mp4 avi mov webm wmv m4v flv mpg mpeg ts".split())
ISO = {"iso", "img"}
INSTALL = set("rpm deb appimage run msi exe dmg".split())
ARCH = set("zip 7z rar tar gz tgz xz bz2 zst".split())
PART = set("part crdownload download".split())
TEMP = set("tmp temp bak old orig swp".split())


def _ext(path: str) -> str:
    n = os.path.basename(path.rstrip("/")).lower()
    for d in (".tar.gz", ".tar.xz", ".tar.bz2", ".tar.zst"):
        if n.endswith(d):
            return d[5:]
    return n.rsplit(".", 1)[-1] if "." in n.strip(".") else ""


def categories(path: str, reasons=(), rating: str = "", kind: str = "") -> set:
    """Zbior kluczy regul, pod ktore podpada pozycja."""
    out: set = set()
    ext = _ext(path)
    low = os.path.basename(path.rstrip("/")).lower()
    reasons = list(reasons)
    if kind != "dir":
        if ext in ISO:
            out.add("iso")
        elif ext in INSTALL:
            out.add("installers")
        elif ext in ARCH:
            out.add("archives")
        elif ext in PART:
            out.add("partial")
        elif ext in TEMP or low.endswith("~"):
            out.add("tempbak")
        elif ext == "log":
            out.add("logs")
        elif ext in VIDEO:
            out.add("video")
        if low.startswith("core.") and ext.isdigit():
            out.add("coredumps")
    if kb.has_reason(reasons, "dup"):
        out.add("duplicates")
    if kb.has_reason(reasons, "oldver") or kb.has_reason(reasons, "copyname"):
        out.add("versions")
    if kb.has_reason(reasons, "extracted"):
        out.add("extracted")
    if kb.has_reason(reasons, "installer") and ext not in ISO:
        out.add("installers")
    if kind == "dir" and kb.has_reason(reasons, "recreatable"):
        out.add("builddirs")
    if kb.has_reason(reasons, "loc_safe"):
        out.add("cache")
    if kb.has_reason(reasons, "loc_review"):
        out.add("old_review")
    if rating == "mine":
        out.add("mine")
    return out


def allowed(path: str, reasons, rating: str, kind: str, off) -> bool:
    return not (off and categories(path, reasons, rating, kind) & set(off))


def off_text(off) -> str:
    """Zdanie do promptu o tym, czego uzytkownik zabronil proponowac."""
    names = [SHORT[k] for k in KEYS if k in set(off)]
    if not names:
        return ""
    return ("Użytkownik wyłączył propozycje dla: " + "; ".join(names) +
            ". Dla takich pozycji zawsze odpowiadaj 'zostawic'.")
