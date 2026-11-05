"""Raport: co program usunie, co zostawi i co jest chronione (Markdown / CSV).

Raport nie zawiera zawartosci plikow. Domyslnie sciezki sa anonimizowane
(/home/uzytkownik -> ~), a nazwy plikow w "Twoich plikach" maskowane.
"""
from __future__ import annotations

import csv
import io
import os
import platform
import re
import time

from . import __version__, fsutil, kb, osal, settings
from .core import HOME, ai_only, fmt_size

DECISION_DELETE = "USUNĘ"
DECISION_KEEP = "ZOSTAWIĘ"
DECISION_PROTECTED = "CHRONIONE"


def os_pretty() -> str:
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for ln in f:
                if ln.startswith("PRETTY_NAME="):
                    return ln.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.platform()


def mask_home(text: str, home: str) -> str:
    """Katalog domowy -> ~ (tylko caly czlon sciezki; na Windows obie postacie separatora i bez rozrozniania wielkosci liter)."""
    if not home.rstrip("\\/") or re.fullmatch(r"[A-Za-z]:[\\/]*", home):
        return text  # HOME=/ albo korzen dysku: nie ma co maskowac (wytarloby caly tekst)
    win = "\\" in home or (len(home) > 1 and home[1] == ":")
    pat = r"[\\/]+".join(map(re.escape, re.split(r"[\\/]+", home.rstrip("\\/")))) if win else re.escape(home.rstrip("/"))
    return re.sub(r"(?<![\w~.-])" + pat + r"(?![\w-]|\.\w)", "~", text, flags=re.I if win else 0)


class Anon:
    def __init__(self, enabled: bool = True, private_names: bool = False) -> None:
        self.enabled = enabled
        self.private = private_names
        self.home = str(HOME)

    def path(self, text: str) -> str:
        if not self.enabled:
            return text
        text = mask_home(text, self.home)
        text = re.sub(r"(?<![\w.~-])/home/[^/\s'\"():,;]+", "~", text)  # cudze konta: znika cała nazwa, bez zjadania znaków za nią
        text = re.sub(r"(?<!~/home/)(?<=/home/)(?!<użytkownik>)[^/\s'\"():,;~]+", "<użytkownik>", text)  # /home/<login> w srodku sciezki (kopia na innym dysku)
        text = re.sub(r"(/run/media|/media)/[^/\s]+", r"\1/<użytkownik>", text)
        return text

    def text(self, s: str) -> str:
        """Opis (co to jest / dlaczego): ścieżki jak w path(), a nazwy w «…» (np. oryginał duplikatu) maskowane, gdy nazwy są ukryte."""
        if not self.enabled:
            return s
        s = self.path(s)
        return s if self.private else re.sub(r"«[^»]*»", "«…»", s)

    def shown(self, path: str, rating: str, is_dir: bool = False) -> str:
        """Sciezka do pokazania - maskuje szczegoly w 'Twoich plikach'."""
        if self.private or rating != kb.MINE:
            return self.path(path)
        sep = "\\" if "\\" in self.home else "/"
        if path != self.home and path.startswith(self.home + sep):
            parts = path[len(self.home) + 1:].split(sep)
            tail = "<folder>" if is_dir else f"<plik .{kb.ext_of(parts[-1]) or 'bez rozszerzenia'}>"
            if len(parts) <= 1:
                return f"~{sep}{tail}"
            return f"~{sep}{parts[0]}{sep}…{sep}{tail}"
        parts = [x for x in re.split(r"[\\/]", path) if x]  # poza katalogiem domowym (np. /mnt/dane/...): zostaje tylko pierwszy skladnik
        if len(parts) <= 1:
            return self.path(path)
        tail = "<folder>" if is_dir else f"<plik .{kb.ext_of(parts[-1]) or 'bez rozszerzenia'}>"
        lead = path[:path.index(parts[0]) + len(parts[0])]
        return f"{self.path(lead)}{sep if sep in path else '/'}…{sep if sep in path else '/'}{tail}"


def _cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def _rows(cats: list) -> list:
    """Splaszczone wiersze: dict z decyzja i polami."""
    rows = []
    for c in cats:
        for e in c.entries:
            if e.checked and e.deletable:
                dec, reason = DECISION_DELETE, ""
            elif e.warn:
                dec, reason = DECISION_KEEP, e.warn
            elif not e.deletable:
                dec, reason = DECISION_KEEP, "ocena: " + kb.RATING_LABEL.get(e.rating, e.rating)
            elif e.suggested:
                dec, reason = DECISION_KEEP, "odznaczone przez Ciebie"
            else:
                dec, reason = DECISION_KEEP, ("AI nie zatwierdziło usunięcia - decyzja należy do Ciebie" if ai_only()
                                              else "program nie zaznacza tego sam - decyzja należy do Ciebie")
            rows.append(dict(
                decision=dec, category=c.title, label=e.label, size=e.size, rating=e.rating,
                suggested=e.suggested, what=e.what, why=e.why, warn=e.warn, reason=reason,
                target=" ; ".join(e.paths) if e.paths else (e.cmd or ("dnf remove " + ", ".join(e.pkgs) if e.pkgs else e.kind)),
                disk=e.disk,
                root=e.root, rule=e.rule,
            ))
    return rows


def build_markdown(cats, protected=None, scan=None, disks=None, anon: Anon | None = None,
                   dry_run: bool = False, ai_count: int | None = None) -> str:
    an = anon or Anon()
    rows = _rows(cats)
    dele = [r for r in rows if r["decision"] == DECISION_DELETE]
    keep = [r for r in rows if r["decision"] == DECISION_KEEP]
    L: list = []
    L.append(f"# Raport TidyDisk {__version__}")
    L.append("")
    L.append(f"- Data: {time.strftime('%Y-%m-%d %H:%M')}")
    L.append(f"- System: {os_pretty()}" + ("" if osal.is_windows() else f", jądro {osal.kernel_release()}"))
    L.append(f"- Tryb: {'symulacja (nic nie zostało usunięte)' if dry_run else 'lista przed sprzątaniem'}")
    mode = settings.load().get("search_mode", "")
    label = {"algorithm": "niedokładny (tylko algorytm)", "assisted": "dokładny (algorytm + AI)",
             "ai_only": "bardzo dokładny (tylko AI)"}.get(mode, mode)
    L.append(f"- Wyszukiwanie: {label}" + ("" if ai_count is None or mode == "algorithm" else f"; ocen AI w tej liście: {ai_count}"))
    L.append(f"- Ścieżki zanonimizowane: {'tak' if an.enabled else 'nie'}; "
             f"nazwy w „Twoich plikach”: {'widoczne' if an.private else 'zamaskowane'}")
    L.append("")
    L.append("## Podsumowanie")
    L.append("")
    L.append(f"- **Usunę:** {len(dele)} pozycji, ok. {fmt_size(sum(r['size'] for r in dele))}")
    L.append(f"- **Zostawię:** {len(keep)} znalezionych pozycji, ok. {fmt_size(sum(r['size'] for r in keep))}")
    prot_all = list(protected or [])
    for c in cats:
        prot_all += c.protected
    L.append(f"- **Chronione:** {len(prot_all)} miejsc, których program nigdy nie rusza")
    L.append("")
    L.append("Oceny: **Bezpieczne** = program odtworzy to sam · **Do przejrzenia** = zwykle zbędne, "
             "ale decyzja należy do człowieka · **Nie ruszaj** = system i dane programów · "
             "**Twoje pliki** = nigdy nie usuwane.")
    L.append("")

    seen_text: dict = {}

    def table(items, with_reason):
        L.append("| Pozycja | Rozmiar | Ocena | Co to jest i dlaczego | Gdzie |" + (" Powód zostawienia |" if with_reason else ""))
        L.append("|---|---:|---|---|---|" + ("---|" if with_reason else ""))
        for r in items:
            text = an.text(f"{r['what']} - {r['why']}" if r["what"] and r["why"] else f"{r['what']}{r['why']}".strip())
            lab, where = _mask(an, r)
            if text and text in seen_text:
                shown = f"↑ jak „{_cell(seen_text[text])}”"
            else:
                seen_text[text] = lab
                shown = _cell(text)
            where = where if len(where) <= 70 else where[:67] + "…"
            line = (f"| {_cell(lab)} | {fmt_size(r['size'])} | "
                    f"{kb.RATING_LABEL.get(r['rating'], r['rating'])} | {shown} | `{_cell(where)}` |")
            if with_reason:
                line += f" {_cell(an.text(r['reason']))} |"
            L.append(line)
        L.append("")

    L.append("## Podział wg dysków")
    L.append("")
    L.append("| Dysk / partycja | Usunę | Zostawię (znalezione) |")
    L.append("|---|---:|---:|")
    per_disk: dict = {}
    for r in rows:
        d = per_disk.setdefault(r["disk"] or "(nieznany)", [0, 0, 0, 0])
        i = 0 if r["decision"] == DECISION_DELETE else 2
        d[i] += 1
        d[i + 1] += r["size"]
    for name, (nd, sd, nk, sk) in per_disk.items():
        L.append(f"| {_cell(an.path(name))} | {nd} poz., {fmt_size(sd)} | {nk} poz., {fmt_size(sk)} |")
    L.append("")

    L.append(f"## {DECISION_DELETE} - zaznaczone do usunięcia")
    L.append("")
    if dele:
        table(dele, False)
    else:
        L.append("_Nic nie jest zaznaczone._")
        L.append("")

    L.append(f"## {DECISION_KEEP} - znalezione, ale nie zaznaczone")
    L.append("")
    if keep:
        table(keep, True)
    else:
        L.append("_Brak._")
        L.append("")

    L.append(f"## {DECISION_PROTECTED} - program nigdy tego nie usuwa")
    L.append("")
    if prot_all:
        L.append("| Miejsce | Rozmiar | Powód |")
        L.append("|---|---:|---|")
        for p in prot_all:
            L.append(f"| {_cell(an.path(p.label))} | {fmt_size(p.size)} | {_cell(p.reason)} |")
        L.append("")

    L.extend(_folder_listing(an))
    if scan is not None:
        L.extend(_scan_section(scan, an))
    if disks:
        L.append("## Dyski i partycje")
        L.append("")
        L.append("| Dysk / partycja | Typ | System plików | Punkt montowania | Zajęte | Rozmiar |")
        L.append("|---|---|---|---|---:|---:|")
        shown: set = set()
        for d in disks:
            L.append(f"| **{_cell(d.name)}** {_cell(d.model)} | {d.kind} | | | | {fmt_size(d.size)} |")
            for p in d.parts:
                key = (p.fstype, p.mount, p.used)
                if p.mount and key in shown:  # btrfs na kilku partycjach: 'zajete' dotyczy calego systemu plikow
                    used = "↑ ten sam system plików"
                else:
                    used = fmt_size(p.used) if p.mount else "—"
                    shown.add(key)
                L.append(f"| &nbsp;&nbsp;{_cell(p.name)} {_cell(p.label)} | | {_cell(p.fstype)} | "
                         f"{_cell(an.path(p.mount))} | {used} | {fmt_size(p.size)} |")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def _folder_listing(an: Anon, names=("Downloads", "Pobrane"), limit: int = 150) -> list:
    """Wszystkie pliki z folderow 'do przejrzenia' (np. Pobrane) - do sprawdzenia ocen."""
    from .core import list_folder
    out: list = []
    for name in names:
        path = os.path.join(str(HOME), name)
        if not os.path.isdir(path):
            continue
        items, extra, err = list_folder(path, limit=limit)
        if err or not items:
            continue
        out += [f"## Zawartość ~/{name} (do {limit} największych pozycji)", "",
                "| Nazwa | Rozmiar | Zmieniony | Ocena | Rozpoznane jako |", "|---|---:|---|---|---|"]
        for it in items:
            shown = an.shown(it.path, it.verdict.rating, it.is_dir)
            shown = re.split(r"[\\/]", shown)[-1]
            out.append(f"| {'📁 ' if it.is_dir else ''}{_cell(shown)} | "
                       f"{('≥ ' if not it.exact else '') + fmt_size(it.size) if it.size >= 0 else '—'} | "
                       f"{time.strftime('%Y-%m-%d', time.localtime(it.mtime))} | "
                       f"{kb.RATING_LABEL.get(it.verdict.rating, it.verdict.rating)} | {_cell(it.verdict.title)} |")
        if extra:
            out.append(f"| … i {extra} więcej | | | | |")
        out.append("")
    return out


def _scan_section(scan, an: Anon) -> list:
    L = ["## Przegląd dysku (pełne skanowanie)", ""]
    nf, nd = f"{scan.nfiles:,}".replace(",", " "), f"{scan.ndirs:,}".replace(",", " ")
    L.append(f"Przeskanowano `{an.path(scan.root)}`: {nf} plików w {nd} katalogach, "
             f"{fmt_size(scan.total)}; tryb: {'administrator' if scan.mode == 'admin' else 'użytkownik'}; "
             f"czas {scan.seconds} s; niedostępnych miejsc: {scan.errors}.")
    L.append("")
    L.append("**Podział wg oceny**")
    L.append("")
    L.append("| Ocena | Rozmiar |")
    L.append("|---|---:|")
    for r in kb.RATINGS:
        L.append(f"| {kb.RATING_LABEL[r]} | {fmt_size(scan.by_rating.get(r, 0))} |")
    L.append("")
    L.append("**Podział wg typu plików**")
    L.append("")
    L.append("| Typ | Rozmiar | Plików |")
    L.append("|---|---:|---:|")
    for name, (b, n) in sorted(scan.by_type.items(), key=lambda kv: -kv[1][0]):
        L.append(f"| {name} | {fmt_size(b)} | {n} |")
    L.append("")
    L.append("**Największe katalogi**")
    L.append("")
    L.append("| Katalog | Rozmiar | Ocena | Rozpoznane jako |")
    L.append("|---|---:|---|---|")
    nodes = sorted(scan.nodes.items(), key=lambda kv: -kv[1][0])
    shown = 0
    for path, (size, _f, rating, title, depth) in nodes:
        if path == scan.root or depth > 2:
            continue
        L.append(f"| {_cell(an.shown(path, rating, True))} | {fmt_size(size)} | "
                 f"{kb.RATING_LABEL.get(rating, rating)} | {_cell(title)} |")
        shown += 1
        if shown >= 25:
            break
    L.append("")
    L.append("**Największe pliki** (po ocenie, żeby sprawdzić, czy program ocenia trafnie)")
    L.append("")
    L.append("| Plik | Rozmiar | Ocena | Rozpoznane jako |")
    L.append("|---|---:|---|---|")
    per: dict = {}
    for size, path, _mt, rating, title in scan.top_files:
        if per.get(rating, 0) >= 12:
            continue
        per[rating] = per.get(rating, 0) + 1
        L.append(f"| {_cell(an.shown(path, rating))} | {fmt_size(size)} | "
                 f"{kb.RATING_LABEL.get(rating, rating)} | {_cell(title)} |")
    L.append("")
    return L


def _mask(an, r) -> tuple:
    """(nazwa, miejsce) pozycji do raportu; dla 'Twoich plikow' bez nazw plikow i folderow (jak deklaruje naglowek raportu)."""
    if r["rating"] != kb.MINE:
        return an.path(r["label"]), an.path(r["target"])
    parts = [an.shown(t, r["rating"]) for t in str(r["target"]).split(" ; ")]
    where = " ; ".join(parts)
    label = re.split(r"[\\/]", parts[0])[-1] if len(parts) == 1 and parts[0] else "Twoje pliki"
    return label, where


def build_csv(cats, protected=None, anon: Anon | None = None) -> str:
    an = anon or Anon()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(["decyzja", "kategoria", "pozycja", "rozmiar_bajty", "ocena", "propozycja_programu",
                "co_to_jest", "dlaczego", "ostrzezenie_lub_powod", "cel_lub_polecenie",
                "administrator", "regula", "dysk"])
    for r in _rows(cats):
        lab, where = _mask(an, r)
        w.writerow([fsutil.csv_safe(x) for x in
                    [r["decision"], r["category"], lab, r["size"], r["rating"],
                     "usunąć" if r["suggested"] else "zostawić", an.text(r["what"]), an.text(r["why"]),
                     an.text(r["warn"] or r["reason"]), where, "tak" if r["root"] else "nie",
                     r["rule"], an.path(r["disk"])]])
    prot = list(protected or [])
    for c in cats:
        prot += c.protected
    for p in prot:
        w.writerow([DECISION_PROTECTED, "", an.path(p.label), p.size, p.rating, "", "", p.reason,
                    "", an.path(p.path), "", ""])
    return buf.getvalue()


def default_filename(ext: str) -> str:
    return f"tidydisk-raport-{time.strftime('%Y%m%d-%H%M')}.{ext}"
