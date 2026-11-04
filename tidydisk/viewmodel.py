"""Logika widokow bez Qt (latwa do testowania): wiersze tabel, podsumowania."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

from . import kb
from .core import HOME, ai_only, confidence_text, dedupe_selection, fmt_size

RATING_ORDER = {kb.SAFE: 0, kb.REVIEW: 1, kb.MINE: 2, kb.KEEP: 3}

# Jedno zrodlo ocen dla wszystkich widokow (lista, plakietki, mapa, legenda): ocena to ZAWSZE glif + tekst + kolor,
# nigdy sam kolor (daltonizm). Kolory dobrane na kontrast >= 4,5:1 na tle karty motywu ciemnego / jasnego.
RATING_GLYPH = {kb.SAFE: "✔", kb.REVIEW: "▲", kb.MINE: "◆", kb.KEEP: "✖"}
RATING_COLORS = {  # ocena: (kolor na ciemnym tle, kolor na jasnym tle)
    kb.SAFE: ("#4ade9e", "#0a6f44"),
    kb.REVIEW: ("#f5b83d", "#8a5a00"),
    kb.MINE: ("#6aaeff", "#1558c0"),
    kb.KEEP: ("#ff8a98", "#b3263a"),
}
RATING_COLOR = {r: pair[0] for r, pair in RATING_COLORS.items()}  # zgodnosc wsteczna: kolory dla ciemnego tla


def rating_color(rating: str, dark: bool = True) -> str:
    pair = RATING_COLORS.get(rating)
    return pair[0 if dark else 1] if pair else ("#9aa5b4" if dark else "#566070")


def rating_text(rating: str) -> str:
    """'✔ Bezpieczne' - czytelne bez koloru i dla czytnika ekranu."""
    return f"{RATING_GLYPH.get(rating, '•')} {kb.RATING_LABEL.get(rating, rating)}"


def rating_legend_html(dark: bool = True) -> str:
    return " &nbsp; ".join(f"<span style='color:{rating_color(r, dark)}'>{RATING_GLYPH[r]}</span> {kb.RATING_LABEL[r]}"
                           for r in (kb.SAFE, kb.REVIEW, kb.MINE, kb.KEEP))


def plan_line(sel: list, to_trash: bool, fmt) -> str:
    """Jedna linia 'co dokladnie zniknie' do stalego paska podsumowania: bezpowrotnie / do kosza + liczby wg ocen."""
    perm = trash = 0
    by: dict = {}
    for e in sel:
        size = max(e.size, 0)
        if e.user_pick and (e.trash or to_trash):
            trash += size
        else:
            perm += size
        by[e.rating] = by.get(e.rating, 0) + 1
    if not sel:
        return ""
    parts = [f"bezpowrotnie {fmt(perm)}", f"do kosza {fmt(trash)}"]
    parts += [f"{RATING_GLYPH.get(r, '•')} {by[r]}" for r in (kb.SAFE, kb.REVIEW, kb.MINE, kb.KEEP) if r in by]
    return "Co zniknie: " + "  ·  ".join(parts)


def plan_rows(sel: list, to_trash: bool, fmt) -> list:
    """Wiersze do okna 'co zostanie usuniete': (sposob, nazwa, rozmiar, ocena, gdzie, dlaczego, bajty), najpierw bezpowrotnie, od najwiekszych."""
    rows = []
    for e in sel:
        how = "Do kosza" if e.user_pick and (e.trash or to_trash) else "Bezpowrotnie"
        where = e.paths[0] if e.paths else (e.cmd or e.note or "")
        why = e.why or e.what or e.note
        rows.append((how, e.label, fmt(e.size) if e.size > 0 else "-", rating_text(e.rating), where, why, max(e.size, 0)))
    rows.sort(key=lambda r: (r[0] != "Bezpowrotnie", -r[6]))
    return rows  # ostatnia kolumna = rozmiar w bajtach (do sortowania)


def plural(n: int, one: str, few: str, many: str) -> str:
    if n == 1:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def date_text(ts: int) -> str:
    if not ts:
        return "—"
    try:
        return time.strftime("%Y-%m-%d", time.localtime(ts))
    except (OverflowError, OSError, ValueError):  # absurdalny mtime z uszkodzonego pliku nie moze wywalic okna
        return "—"


def short_path(path: str) -> str:
    h = str(HOME)
    return "~" + path[len(h):] if path == h or path.startswith(h + "/") or (os.name == "nt" and path.startswith(h + "\\")) else path


@dataclass
class FolderRow:
    path: str
    name: str
    size: int
    files: int
    rating: str
    title: str
    frac: float
    expandable: bool


def folder_rows(scan, path: str) -> list:
    """Podkatalogi `path` z wyniku skanu (posortowane od najwiekszego)."""
    kids = scan.children(path)
    biggest = max((k[1] for k in kids), default=0)
    out = []
    for p, size, files, rating, title in kids:
        out.append(FolderRow(
            p, os.path.basename(p) or p, size, files, rating, title,
            (size / biggest) if biggest else 0.0,
            bool(scan.children(p)),
        ))
    return out


@dataclass
class FileRow:
    path: str
    name: str
    folder: str
    size: int
    mtime: int
    rating: str
    title: str


def file_rows(scan, rating: str | None = None, text: str = "") -> list:
    needle = text.strip().lower()
    out = []
    for size, path, mtime, r, title in scan.top_files:
        if rating and r != rating:
            continue
        if needle and needle not in path.lower() and needle not in title.lower():
            continue
        out.append(FileRow(path, os.path.basename(path), os.path.dirname(path), size, mtime, r, title))
    return out


def type_rows(scan) -> list:
    """[(kategoria, bajty, liczba, udzial)] od najwiekszej."""
    total = sum(v[0] for v in scan.by_type.values()) or 1
    rows = [(k, v[0], v[1], v[0] / total) for k, v in scan.by_type.items()]
    rows.sort(key=lambda r: -r[1])
    return rows


def rating_rows(scan) -> list:
    total = sum(scan.by_rating.values()) or 1
    return [(r, scan.by_rating.get(r, 0), scan.by_rating.get(r, 0) / total) for r in kb.RATINGS]


def entry_details(e) -> str:
    """Tekst panelu szczegolow dla pozycji sprzatania."""
    lines = []
    if e.what:
        lines.append(f"Co to jest: {e.what}")
    if e.why:
        lines.append(f"Dlaczego: {e.why}")
    if e.warn:
        lines.append(f"⚠ {e.warn}")
    if e.note:
        lines.append(f"Gdzie: {e.note}")
    if e.disk:
        lines.append(f"Dysk: {e.disk}")
    lines.append(f"Ocena: {kb.RATING_LABEL.get(e.rating, e.rating)}"
                 + (f"  (reguła: {e.rule})" if e.rule else ""))
    return "\n".join(lines)


def detail_sections(e) -> dict:
    """Pola panelu szczegolow (po prawej): tytul, sciezka, kafelki, opisy, werdykt AI. Czysta logika, bez Qt."""
    ai_text, level = "", ""
    if getattr(e, "ai", ""):
        names = {"usunac": "Można usunąć", "zostawic": "Lepiej zostawić", "nie_wiem": "Nie jestem pewien"}
        ai_text = names.get(e.ai, e.ai)
        why = next((r[2:].strip() for r in e.reasons if r.startswith("🤖")), "")
        if why:
            ai_text += "\n" + why
        level = {"usunac": "ok", "zostawic": "warn"}.get(e.ai, "unsure")
    return dict(
        title=e.label, path=e.paths[0] if getattr(e, "paths", None) else e.note,
        size=fmt_size(e.size), score=(f"{e.score}%" if getattr(e, "score", 0) else "-"),
        what=e.what or "-", why=(e.why or "-"), warn=e.warn or "",
        ai=ai_text, ai_level=level, rating=kb.RATING_LABEL.get(e.rating, e.rating),
        can_toggle=bool(getattr(e, "deletable", False)),
        rating_text=rating_text(e.rating), **decision_of(e),
    )


EMPTY_HINT = ("Kliknij pozycję na liście, a tutaj zobaczysz: co to jest, dlaczego proponuję jej usunięcie, "
              "jak pewna jest ocena i czy jest zaznaczona do usunięcia.")


def decision_of(e) -> dict:
    """Co stanie sie z pozycja: zaznaczona do usuniecia / zostaje / chroniona (tekst i poziom do kolorowania)."""
    if not getattr(e, "deletable", False):
        return dict(decision="🔒 Program tego nie usuwa", decision_level="keep")
    if getattr(e, "checked", False):
        return dict(decision="✖ Zaznaczone do usunięcia", decision_level="delete")
    return dict(decision="✔ Zostaje (niezaznaczone)", decision_level="stay")


def cleanup_summary(cats: list, extra=()) -> dict:
    allentries = [e for c in cats for e in c.entries] + list(extra)
    sel = dedupe_selection([e for e in allentries if e.checked and e.deletable])
    rest = [e for c in cats for e in c.entries if not (e.checked and e.deletable)]
    return dict(
        n_delete=len(sel), size_delete=sum(e.size for e in sel),
        n_keep=len(rest), size_keep=sum(e.size for e in rest),
        n_root=sum(1 for e in sel if e.root), n_warn=sum(1 for e in sel if e.warn),
        n_mine=sum(1 for e in sel if e.rating == kb.MINE),
        selected=sel,
    )


def disk_summary(cats: list, extra=()) -> list:
    """[(dysk, ile_do_usuniecia, rozmiar_do_usuniecia)] tylko dyski z zaznaczeniem."""
    acc: dict = {}
    for e in dedupe_selection([e for c in cats for e in c.entries if e.checked and e.deletable]
                              + [e for e in extra if e.checked and e.deletable]):
        d = acc.setdefault(e.disk or "?", [0, 0])
        d[0] += 1
        d[1] += e.size
    return [(k, n, s) for k, (n, s) in sorted(acc.items(), key=lambda kv: -kv[1][1])]


def plan_text(sel: list, to_trash: bool, fmt) -> str:
    """Plan przed czyszczeniem: ile i skad, co bezpowrotnie a co do kosza, co zrobi administrator."""
    perm = trash = 0
    disks: dict = {}
    cmds: list = []
    for e in sel:
        into_trash = e.user_pick and (e.trash or to_trash)
        if e.root:
            if e.cmd:
                cmds.append(e.cmd)
            elif e.kind == "root_pkg" and e.pkgs:
                cmds.append("dnf remove " + " ".join(e.pkgs[:6]) + (" …" if len(e.pkgs) > 6 else ""))
        if into_trash:
            trash += max(e.size, 0)
        else:
            perm += max(e.size, 0)
        disks[e.disk or "?"] = disks.get(e.disk or "?", 0) + max(e.size, 0)
    lines = [f"Bezpowrotnie: {fmt(perm)}", f"Do kosza (miejsce zwolni się po jego opróżnieniu): {fmt(trash)}"]
    if len(disks) > 1 or (disks and "?" not in disks):
        lines.append("Na dyskach: " + "; ".join(f"{d} {fmt(s)}" for d, s in sorted(disks.items(), key=lambda kv: -kv[1])))
    if cmds:
        lines.append("Jako administrator wykonam:")
        lines += ["   " + c for c in cmds]
    if any("btrfs" in (e.disk or "") for e in sel):
        lines.append("Uwaga: na btrfs migawki (snapshoty) mogą nadal trzymać usunięte dane - miejsce zwolni się po ich usunięciu.")
    return "\n".join(lines)


class ReviewSession:
    """Przeglad pozycji po kolei przed usunieciem: kazda wymaga osobnej decyzji (bez Qt, latwe do testow).

    Akcje: 'delete' (usun te), 'keep' (zostaw te), 'delete_rest' (usun te i wszystkie pozostale),
    'keep_rest' (zostaw te i pozostale), 'abort' (przerwij calosc - nic nie zostanie usuniete)."""

    def __init__(self, entries: list) -> None:
        self.items = sorted(entries, key=lambda e: -e.size)
        self.i = 0
        self.approved: list = []
        self.kept: list = []
        self.aborted = False

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def finished(self) -> bool:
        return self.aborted or self.i >= len(self.items)

    @property
    def current(self):
        return None if self.finished else self.items[self.i]

    def decide(self, action: str) -> bool:
        """Zapisuje decyzje dla biezacej pozycji; zwraca True, gdy przeglad dobiegl konca."""
        if self.finished:
            return True
        if action == "abort":
            self.aborted = True
            self.approved = []
            return True
        rest = self.items[self.i:] if action in ("delete_rest", "keep_rest") else [self.items[self.i]]
        (self.approved if action in ("delete", "delete_rest") else self.kept).extend(rest)
        self.i += len(rest)
        return self.finished


def review_text(e, preview: dict | None = None) -> str:
    """Opis pozycji do okna przegladu: co to, dlaczego, uwagi, podglad zawartosci."""
    lines = []
    if e.paths:
        lines.append(f"Ścieżka: {e.paths[0]}")
    lines.append(f"Rozmiar: {fmt_size(e.size)}   ·   Ocena: {kb.RATING_LABEL.get(e.rating, e.rating)}"
                 + ((f"   ·   {confidence_text(e.score)}" if ai_only() else f"   ·   Pewność: {e.score}%") if e.score else ""))
    if e.what:
        lines.append(f"Co to jest: {e.what}")
    if e.reasons:
        lines.append("Dlaczego proponuję usunięcie:")
        lines += [f"  • {r}" for r in e.reasons]
    elif e.why:
        lines.append(f"Dlaczego: {e.why}")
    if preview:
        lines.append("")
        lines.append("W środku:")
        if preview.get("pominiete"):
            lines.append(f"  ({preview['pominiete']})")
        if preview.get("typ"):
            lines.append(f"  Typ: {preview['typ']}")
        if preview.get("pakiet"):
            lines.append(f"  Pakiet: {preview['pakiet']}")
        if preview.get("poczatek_tekstu"):
            lines.append(f"  Początek: {preview['poczatek_tekstu'][:300]}")
        if preview.get("w_archiwum"):
            n = preview.get("plikow_w_archiwum")
            lines.append(f"  Archiwum{f' ({n} plików)' if n else ''}: " + ", ".join(preview["w_archiwum"][:10]))
    notes = []
    if e.rating == kb.MINE:
        notes.append("⚠ To Twój plik - trafi do kosza (jeśli opcja kosza jest włączona).")
    if e.warn:
        notes.append(f"⚠ {e.warn}")
    if e.root:
        notes.append("Wymaga hasła administratora.")
    if notes:
        lines.append("")
        lines += notes
    return "\n".join(lines)
