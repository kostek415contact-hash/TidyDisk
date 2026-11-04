"""Tryb tekstowy (bez Qt): `tidydisk status|scan|analyze|clean|report|notify|schedule|ai|config|rules|history`.

Do terminala, SSH, harmonogramu i skryptow. Czyszczenie bez nadzoru rusza WYLACZNIE pozycje ocenione
jako Bezpieczne z kategorii wbudowanych (cache, dzienniki...), nigdy nie uzywa AI i nigdy nie dotyka
'Twoich plikow' ani propozycji z analizy. Opcje zawezaja zakres (--only, --exclude, --older-than, --min-size, --disk),
nigdy go nie rozszerzaja.

Kody wyjscia: 0 ok, 1 blad (np. czesc pozycji nie zostala usunieta), 2 zle uzycie, 3 inna praca w tle juz dziala,
4 brak serwera AI.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time

from . import __version__, core, osal, export, fsutil, history, kb, rules, schedule, settings, snapshots, spacelog

EXIT_OK, EXIT_ERR, EXIT_USAGE, EXIT_BUSY, EXIT_NO_AI = 0, 1, 2, 3, 4


def _entry(e) -> dict:
    return {"label": e.label, "size": e.size, "rating": e.rating, "checked": bool(e.checked), "root": bool(e.root),
            "warn": e.warn, "paths": list(e.paths)[:5], "what": e.what}


def run_cfg(overrides: dict | None = None, rule_spec: str = "") -> dict:
    """Ustawienia z pliku + nadpisania z wiersza polecen (tylko na ten przebieg, niczego nie zapisuje).
    rule_spec: '+iso,-video' wlacza/wylacza reguly (klucze: tidydisk rules)."""
    cfg = settings.load()
    for k, v in (overrides or {}).items():
        if v is not None:
            cfg[k] = v
    for tok in [t.strip() for t in rule_spec.split(",") if t.strip()]:
        key, on = (tok[1:], tok[0] != "-") if tok[0] in "+-" else (tok, True)
        if key not in rules.KEYS:
            raise ValueError(f"nieznana reguła «{key}» (lista: tidydisk rules)")
        cfg["rule_" + key] = on
    return settings.apply(cfg)


def collect(status=lambda _m: None, cfg: dict | None = None) -> dict:
    """Skanuje kategorie wbudowane i zwraca dane do wydruku/JSON."""
    settings.apply(cfg if cfg is not None else settings.load())
    cats = core.scan(status)
    disks = {m: {"used": u, "total": t} for m, (u, t) in core.disk_info().items()}
    out_cats = []
    safe = 0
    for c in cats:
        ents = [_entry(e) for e in c.entries]
        safe += sum(e["size"] for e in ents if e["rating"] == kb.SAFE and e["checked"] and not e["warn"])
        out_cats.append({"key": c.key, "title": c.title, "root": c.root, "entries": ents})
    spacelog.record({m: (d["used"], d["total"]) for m, d in disks.items()}, safe)
    return {"version": __version__, "time": int(time.time()), "disks": disks, "categories": out_cats,
            "safe_reclaimable": safe}, cats


def _entry_disk_ok(e, disk: str) -> bool:
    if not disk:
        return True
    if disk.startswith("/"):
        mounts = core.read_mounts()
        return any(core.mount_of(p, mounts) == disk.rstrip("/") or disk == "/" and core.mount_of(p, mounts) == "/" for p in e.paths)
    return disk.lower() in (e.disk or "").lower()


def _age_days(e) -> float | None:
    """Wiek wpisu w dniach (najmlodszy z jego sciezek) albo None, gdy nie da sie ustalic."""
    ages = []
    for p in e.paths:
        try:
            ages.append((time.time() - os.lstat(p).st_mtime) / 86400)
        except OSError:
            continue
    return min(ages) if ages else None


def unattended_selection(cats: list, with_root: bool, only=None, exclude=(), older_than: float = 0,
                         min_size: int = 0, disk: str = "") -> list:
    """Pozycje, ktore wolno ruszyc bez pytania: Bezpieczne, zaznaczone, bez ostrzezenia o dzialajacym programie.
    Filtry tylko zawezaja: only = klucze kategorii, exclude = sciezki do pominiecia, older_than = dni, min_size = bajty."""
    sel = []
    only = set(only or [])
    for c in cats:
        if only and c.key not in only:
            continue
        for e in c.entries:
            if e.rating != kb.SAFE or not e.checked or e.warn or not e.deletable or e.user_pick:
                continue
            if e.root and not with_root:
                continue
            if e.size < min_size or not _entry_disk_ok(e, disk):
                continue
            if exclude and any(settings.touches(p, list(exclude)) for p in e.paths):
                continue
            if older_than:
                age = _age_days(e)
                if age is None or age < older_than:
                    continue
            sel.append(e)
    return sel


def _print_scan(data: dict, out, only=None) -> None:
    for m, d in data["disks"].items():
        out.write(f"Dysk {m}: zajęte {core.fmt_size(d['used'])} z {core.fmt_size(d['total'])}\n")
    for c in data["categories"]:
        if not c["entries"] or (only and c["key"] not in only):
            continue
        out.write(f"\n{c['title']}{' (administrator)' if c['root'] else ''}  [{c['key']}]\n")
        for e in sorted(c["entries"], key=lambda x: -x["size"])[:30]:
            mark = "[x]" if e["checked"] else "[ ]"
            out.write(f"  {mark} {core.fmt_size(e['size']):>9}  {e['label']}{'  ⚠ ' + e['warn'] if e['warn'] else ''}\n")


def _csv_rows(rows: list, fields: list, out) -> None:
    w = csv.writer(out)
    w.writerow(fields)
    for r in rows:
        w.writerow([";".join(map(str, r[f])) if isinstance(r[f], list) else r[f] for f in fields])


def _coerce(key: str, text: str):
    default = settings.SPEC[key][0]
    if isinstance(default, bool):
        if text.lower() in ("1", "true", "tak", "yes", "on"):
            return True
        if text.lower() in ("0", "false", "nie", "no", "off"):
            return False
        raise ValueError("oczekiwano tak/nie (1/0)")
    if isinstance(default, int):
        return int(text)
    if isinstance(default, float):
        return float(text)
    if isinstance(default, list):
        return [x for x in text.split(":") if x]
    return text


def _cmd_config(a, out) -> int:
    cfg = settings.load(env=False)
    if a.action == "path":
        out.write(settings.path() + "\n")
    elif a.action == "list":
        for k in settings.SPEC:
            v = cfg[k]
            out.write(f"{k} = {'(ustawiony)' if k == 'ai_key' and v else v if not k.startswith('prompt_') else '(tekst)'}\n")
    elif a.action == "get":
        if a.key not in settings.SPEC:
            sys.stderr.write(f"Nieznany klucz: {a.key}\n")
            return EXIT_USAGE
        out.write(("(ustawiony)" if a.key == "ai_key" and cfg[a.key] else str(cfg[a.key])) + "\n")
    elif a.action == "set":
        if a.key not in settings.SPEC:
            sys.stderr.write(f"Nieznany klucz: {a.key}\n")
            return EXIT_USAGE
        if a.key == "ai_key":
            sys.stderr.write("Klucza API nie ustawiam z wiersza poleceń (trafiłby do historii powłoki) - użyj zmiennej FC_AI_KEY "
                             "albo okna Ustawienia → AI.\n")
            return EXIT_USAGE
        try:
            new = settings.update({a.key: _coerce(a.key, a.value)})
        except ValueError as ex:
            sys.stderr.write(f"Zła wartość: {ex}\n")
            return EXIT_USAGE
        out.write(f"{a.key} = {new[a.key]}\n")
    elif a.action == "export":
        out.write(settings.export_text(cfg) + "\n")
    elif a.action == "import":
        try:
            with open(a.key, encoding="utf-8") as f:
                new = settings.import_text(f.read())
        except (OSError, ValueError) as ex:
            sys.stderr.write(f"Nie wczytano: {ex}\n")
            return EXIT_ERR
        settings.save(new)
        out.write("Ustawienia wczytane (adres i klucz AI bez zmian).\n")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tidydisk", description="TidyDisk - tryb tekstowy",
                                epilog="Kody wyjścia: 0 ok, 1 błąd, 2 złe użycie, 3 praca w tle już działa, 4 brak serwera AI.")
    p.add_argument("-V", "--version", action="version", version=f"TidyDisk {__version__}")
    p.add_argument("-q", "--quiet", action="store_true", help="bez komunikatów o postępie (stderr)")
    p.add_argument("--config", help="inny plik ustawień (zamiast ~/.config/tidydisk/settings.json)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(s, disk=True, rules_opt=True):
        if disk:
            s.add_argument("--disk", default="", help="tylko ten dysk: punkt montowania (/mnt/dane) albo fragment nazwy")
        if rules_opt:
            s.add_argument("--rules", default="", help="reguły na ten przebieg, np. +iso,-video (lista: rules)")

    for name, hlp in (("status", "wolne miejsce na dyskach"), ("scan", "co można wyczyścić (kategorie wbudowane)"),
                      ("analyze", "propozycje algorytmu dla plików i folderów"), ("clean", "wyczyść bezpieczne pozycje")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("--json", action="store_true", help="wynik w JSON")
        if name == "status":
            s.add_argument("--exit-code", action="store_true", help="kod 1, gdy któryś dysk ma mniej wolnego miejsca niż --min-free")
            s.add_argument("--min-free", type=int, default=10, metavar="GB", help="próg dla --exit-code (domyślnie 10 GB)")
        if name in ("scan", "analyze"):
            s.add_argument("--format", choices=["text", "json", "csv"], default="text")
        if name != "status":
            common(s)
        if name in ("scan", "clean"):
            s.add_argument("--only", action="append", default=[], metavar="KATEGORIA", help="tylko ta kategoria (klucz widoczny w scan); można powtarzać")
        if name == "analyze":
            s.add_argument("--mode", choices=list(settings.SEARCH_MODES), help="dokładność na ten przebieg (CLI nie ma AI: ai_only nic nie proponuje)")
            s.add_argument("--min-score", type=int, help="najniższa pewność propozycji (0-100)")
            s.add_argument("--depth", type=int, help="głębokość analizy folderów")
            s.add_argument("--limit", type=int, default=100, help="ile propozycji pokazać w tekście")
        if name == "clean":
            s.add_argument("--yes", action="store_true", help="naprawdę usuń (bez tego tylko pokazuję plan)")
            s.add_argument("--dry-run", action="store_true", help="tylko symulacja (silniejsze niż --yes)")
            s.add_argument("--force", action="store_true", help="pozwól --yes mimo włączonej w ustawieniach symulacji")
            s.add_argument("--root", action="store_true", help="także operacje administratora (pkexec)")
            s.add_argument("--exclude", action="append", default=[], metavar="ŚCIEŻKA", help="pomiń ścieżkę; można powtarzać")
            s.add_argument("--older-than", type=float, default=0, metavar="DNI", help="tylko pozycje niezmieniane od tylu dni")
            s.add_argument("--min-size", type=float, default=0, metavar="MB", help="tylko pozycje od tego rozmiaru")
            s.add_argument("--plan", metavar="PLIK", help="zapisz plan (JSON) do przejrzenia i nic nie usuwaj")
            s.add_argument("--apply", metavar="PLIK", help="wykonaj tylko to z planu, co nadal jest bezpieczne (skan od nowa)")
    r = sub.add_parser("report", help="raport HTML lub JSON z całego obrazu")
    r.add_argument("--json", action="store_true")
    r.add_argument("-o", "--output", help="plik wyjściowy (domyślnie stdout)")
    n = sub.add_parser("notify", help="sprawdź dysk i wyślij powiadomienie (dla harmonogramu)")
    n.add_argument("--min-free", type=int, default=20, help="GB wolnego, poniżej którego ostrzegam")
    n.add_argument("--min-reclaim", type=int, default=5, help="GB do odzyskania, od których informuję")
    n.add_argument("--auto-clean", action="store_true", help="po sprawdzeniu wyczyść bezpieczne pozycje (bez administratora)")
    n.add_argument("--stdout-only", action="store_true", help="tylko wypisz tekst (bez notify-send)")
    n.add_argument("--cooldown", type=float, default=0, metavar="DNI", help="nie powiadamiaj częściej niż co tyle dni")
    n.add_argument("--disk", default="", help="liczy wolne miejsce tylko na tym dysku (punkt montowania)")
    sc = sub.add_parser("schedule", help="harmonogram (timer systemd użytkownika)")
    sc.add_argument("action", choices=["enable", "disable", "status"])
    sc.add_argument("--every", choices=sorted(schedule.INTERVALS), default="weekly")
    sc.add_argument("--time", default="", metavar="HH:MM", help="godzina uruchomienia (domyślnie losowa pora)")
    sc.add_argument("--ai", action="store_true", help="timer pracy w tle: skan + ocena AI (zamiast sprawdzenia dysku)")
    sc.add_argument("--mode", choices=list(settings.SEARCH_MODES), default="", help="dokładność pracy w tle (z --ai)")
    sc.add_argument("--min-free", type=int, default=20)
    sc.add_argument("--min-reclaim", type=int, default=5)
    sc.add_argument("--auto-clean", action="store_true")
    b = sub.add_parser("ai", aliases=["background"], help="praca w tle: skan + ocena AI bez okna (nic nie usuwa)")
    b.add_argument("--mode", choices=["assisted", "ai_only"], help="dokładność (domyślnie z ustawień)")
    b.add_argument("--notify", action="store_true", help="powiadomienie pulpitu po zakończeniu")
    b.add_argument("--last", action="store_true", help="pokaż wynik ostatniej pracy w tle i wyjdź")
    b.add_argument("-q", "--quiet", action="store_true", dest="quiet_ai", help="bez komunikatów o postępie (jak -q przed poleceniem)")
    b.add_argument("--wait-ai", type=int, default=0, metavar="MIN", help="poczekaj do MIN minut na serwer AI (np. tuż po starcie systemu)")
    b.add_argument("--export", metavar="PLIK", help="zapisz zapamiętane wyniki AI do pliku .csv albo .json i wyjdź")
    sub.add_parser("changes", help="co się zmieniło od poprzedniego skanu (nowe i rosnące duże foldery)")
    dg = sub.add_parser("diag", help="zrzut diagnostyczny (bez klucza API) do wysłania razem z raportem")
    dg.add_argument("--out", help="zapisz do pliku zamiast na stdout")
    dg.add_argument("--no-ai", action="store_true", help="nie sprawdzaj serwera AI")
    c = sub.add_parser("config", help="ustawienia z terminala")
    c.add_argument("action", choices=["path", "list", "get", "set", "export", "import"])
    c.add_argument("key", nargs="?", help="klucz (get/set) albo plik (import)")
    c.add_argument("value", nargs="?", help="wartość (set)")
    sub.add_parser("rules", help="lista reguł, które można wyłączyć (--rules +klucz,-klucz)")
    h = sub.add_parser("history", help="ostatnie czyszczenia")
    h.add_argument("--json", action="store_true")
    h.add_argument("--limit", type=int, default=10)
    return p


def main(argv=None) -> int:
    p = build_parser()
    a = p.parse_args(argv)
    out = sys.stdout
    if osal.SYSTEM == "linux" and a.cmd not in ("schedule",):
        from . import schedule as _sch
        _sch.migrate_legacy_units()  # po zmianie nazwy: stare timery fedora-cleaner-* -> tidydisk-*
    if a.config:
        os.environ["FC_CONFIG"] = os.path.abspath(os.path.expanduser(a.config))
    err = (lambda _m: None) if a.quiet else (lambda m: sys.stderr.write(m + "\n"))

    if a.cmd == "config":
        if a.action in ("get", "import", "set") and not a.key:
            p.error("podaj klucz (lub plik dla import)")
        if a.action == "set" and a.value is None:
            p.error("podaj wartość")
        return _cmd_config(a, out)

    if a.cmd == "rules":
        cfg = settings.load()
        for r in rules.RULES:
            out.write(f"{'[x]' if cfg.get('rule_' + r[0], True) else '[ ]'} {r[0]:<12} {r[1]}\n")
        return EXIT_OK

    if a.cmd == "history":
        runs = history.load()[: max(1, a.limit)]
        if a.json:
            json.dump(runs, out, ensure_ascii=False, indent=2)
            out.write("\n")
        else:
            for r in runs:
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(r.get("ts", 0)))
                out.write(f"{when}  zwolniono {core.fmt_size(r.get('freed', 0))}, {len(r.get('items', []))} pozycji\n")
            if not runs:
                out.write("Brak zapisanych czyszczeń.\n")
        return EXIT_OK

    if a.cmd == "changes":
        from . import changes
        out.write(changes.describe(home=str(core.HOME)) + "\n")
        return EXIT_OK

    if a.cmd == "diag":
        from . import diag
        text = diag.build(detect_ai=not a.no_ai)
        if a.out:
            fsutil.atomic_write(a.out, text, 0o600)
            out.write(f"Zapisano: {a.out}\n")
        else:
            out.write(text)
        return EXIT_OK

    if a.cmd in ("ai", "background"):
        from . import background
        if a.last:
            out.write((background.describe_last() or "Brak zapisanej pracy w tle.") + "\n")
            return EXIT_OK
        if a.export:
            from . import ai_cache
            try:
                n = background.export_rows(ai_cache.AICache(settings.load()["ai_cache_days"] or 30).rows(), a.export)
            except OSError as ex:
                out.write(f"Nie zapisano: {ex}\n")
                return EXIT_ERR
            out.write(f"Zapisano {n} wyników AI do {a.export}\n")
            return EXIT_OK
        return background.run(a.mode, quiet=a.quiet or a.quiet_ai, notify=a.notify, wait_ai=max(0, min(a.wait_ai, 120)))

    if a.cmd == "schedule":
        try:
            if a.action == "enable":
                if a.ai:
                    out.write("Harmonogram AI w tle " + schedule.enable_ai(a.every, a.time, a.mode) + "\n")
                else:
                    out.write("Harmonogram " + schedule.enable(a.every, a.min_free, a.min_reclaim, a.auto_clean, a.time) + "\n")
            elif a.action == "disable":
                if a.ai:
                    out.write("Harmonogram AI w tle " + schedule.disable_ai() + "\n")
                else:
                    out.write("Harmonogram " + schedule.disable() + "\n")
            else:
                out.write("Harmonogram sprawdzania dysku jest " + ("włączony" if schedule.is_enabled() else "wyłączony") + "\n")
                out.write("Harmonogram AI w tle jest " + ("włączony" if schedule.is_ai_enabled() else "wyłączony") + "\n")
                from . import background
                last = background.describe_last()
                if last:
                    out.write(last + "\n")
        except ValueError as ex:
            sys.stderr.write(f"{ex}\n")
            return EXIT_USAGE
        return EXIT_OK

    if a.cmd == "notify":
        data, cats = collect()
        disks = {m: d for m, d in data["disks"].items() if not a.disk or m == a.disk.rstrip("/") or m == a.disk}
        free = min((d["total"] - d["used"] for d in disks.values()), default=0)
        text = schedule.should_notify(free, data["safe_reclaimable"], a.min_free, a.min_reclaim)
        if text:
            state = os.path.expanduser("~/.local/share/tidydisk/notify.json")
            last = 0.0
            try:
                with open(state, encoding="utf-8") as f:
                    last = float(json.load(f).get("last", 0))
            except (OSError, ValueError, TypeError, AttributeError):
                pass
            if not (a.cooldown and time.time() - last < a.cooldown * 86400):
                if not a.stdout_only:
                    schedule.notify(text + " Otwórz TidyDisk.")
                out.write(text + "\n")
                try:
                    fsutil.atomic_write(state, json.dumps({"last": time.time()}))
                except OSError:
                    pass
        if a.auto_clean:
            cfg = settings.load()
            sel = unattended_selection(cats, False)
            dry = bool(cfg.get("dry_run"))  # symulacja z ustawien obowiazuje tez w harmonogramie
            journal: list = []
            res = core.run_clean(sel, dry, lambda _m: None, journal)
            if not dry:
                history.record(journal, res.freed, res.trashed)
            out.write(f"Auto-czyszczenie{' (symulacja z ustawień)' if dry else ''}: zwolniono ok. {core.fmt_size(res.freed)}.\n")
        return EXIT_OK

    if a.cmd == "report":
        data, _cats = collect()
        text = json.dumps(data, ensure_ascii=False, indent=2) if a.json else export.to_html(data, spacelog.load())
        if a.output:
            with open(a.output, "w", encoding="utf-8") as f:
                f.write(text)
            out.write(f"Zapisano: {a.output}\n")
        else:
            out.write(text)
        return EXIT_OK

    if a.cmd == "status":
        settings.apply(settings.load())
        spacelog.record(core.disk_info())
        data = {"schema": 1, "version": __version__, "time": int(time.time()),
                "disks": {m: {"used": u, "total": t, "free": t - u} for m, (u, t) in core.disk_info().items()}}
        if a.json:
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write("\n")
        else:
            for m, d in data["disks"].items():
                out.write(f"{m}: wolne {core.fmt_size(d['free'])} z {core.fmt_size(d['total'])}\n")
            snap = snapshots.detect()
            if snap["text"]:
                out.write(snap["text"] + "\n")
            from . import background
            last = background.describe_last()
            if last:
                out.write(last + "\n")
        if a.exit_code and any(d["free"] < a.min_free * 1024 ** 3 for d in data["disks"].values()):
            return EXIT_ERR
        return EXIT_OK

    try:
        ov = {}
        if a.cmd == "analyze":
            ov = {"search_mode": a.mode, "min_score": a.min_score, "analysis_depth": a.depth}
        cfg = run_cfg(ov, a.rules)
    except ValueError as ex:
        sys.stderr.write(f"{ex}\n")
        return EXIT_USAGE

    if a.cmd == "analyze":
        from . import scanner
        results = []
        seen: set = set()
        for root, _disk in core.cleanup_roots():
            if root in seen or (a.disk and a.disk.rstrip("/") != root and a.disk.lower() not in (_disk or "").lower()):
                continue
            seen.add(root)
            results.append(scanner.scan(root, core.KB, max_depth=cfg["analysis_depth"], min_score=settings.effective_min_score(cfg),
                                        dup_min=cfg["dup_min_mb"] * 1024 * 1024, dup_budget=float(cfg["dup_budget_s"]),
                                        advise=cfg["search_mode"] != "ai_only"))  # tylko AI: CLI nie ma AI, wiec nie proponuje
        res = scanner.merge_results(results) if results else None
        rows = []
        for adv in (res.advice if res else []):
            e = core.advice_entry(adv)
            if e is not None:
                rows.append({"score": adv[0], "path": adv[1], "size": adv[2], "rating": adv[4], "title": adv[5],
                             "reasons": adv[6]})
        fmt = "json" if a.json else a.format
        if fmt == "json":
            json.dump({"schema": 1, "version": __version__, "advice": rows}, out, ensure_ascii=False, indent=2)
            out.write("\n")
        elif fmt == "csv":
            _csv_rows(rows, ["score", "size", "rating", "title", "path", "reasons"], out)
        else:
            for r in rows[:a.limit]:
                out.write(f"{r['score']:>3}%  {core.fmt_size(r['size']):>9}  {r['path']}\n")
            if cfg["search_mode"] == "ai_only":
                out.write("Tryb „Bardzo dokładny” działa tylko z AI - użyj `tidydisk ai` albo okna programu.\n")
            out.write(f"\n{len(rows)} propozycji (pokazuję {min(len(rows), a.limit)}). Decyzja należy do Ciebie - użyj okna programu.\n")
        return EXIT_OK

    as_json = a.json or getattr(a, "format", "text") == "json"
    status = err if not as_json else (lambda _m: None)
    data, cats = collect(status, cfg)
    if a.disk:
        for c in data["categories"]:
            c["entries"] = [e for e in c["entries"] if a.disk.lower() in " ".join(e["paths"]).lower()
                            or _disk_label_match(cats, c["key"], e, a.disk)]
    if a.cmd == "scan":
        only = set(a.only)
        if as_json:
            if only:
                data["categories"] = [c for c in data["categories"] if c["key"] in only]
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write("\n")
        elif getattr(a, "format", "text") == "csv":
            rows = [dict(category=c["key"], label=e["label"], size=e["size"], rating=e["rating"], checked=e["checked"],
                         path=(e["paths"] or [""])[0]) for c in data["categories"] if not only or c["key"] in only for e in c["entries"]]
            _csv_rows(rows, ["category", "label", "size", "rating", "checked", "path"], out)
        else:
            _print_scan(data, out, only)
        return EXIT_OK

    # clean
    sel = unattended_selection(cats, a.root, only=a.only, exclude=a.exclude, older_than=a.older_than,
                               min_size=int(a.min_size * 1024 * 1024), disk=a.disk)
    if a.plan and a.apply:
        err("--plan i --apply wykluczają się.")
        return EXIT_USAGE
    if a.plan:
        fsutil.atomic_write(a.plan, json.dumps(plan_document(cats, sel), ensure_ascii=False, indent=2) + "\n")
        err(f"Plan zapisany: {a.plan} ({len(sel)} pozycji, ok. {core.fmt_size(sum(e.size for e in sel))}). Nic nie usunięto.")
        return EXIT_OK
    if a.apply:
        try:
            plan = load_plan(a.apply)
        except ValueError as ex:
            err(str(ex))
            return EXIT_USAGE
        sel, skipped = apply_plan(cats, sel, plan)
        for why in skipped:
            err("Pominięto " + why)
    total = sum(e.size for e in sel)
    sim = a.dry_run or not a.yes
    if a.yes and not a.dry_run and cfg.get("dry_run") and not a.force:
        sim = True
        err("W ustawieniach włączona jest symulacja - --yes jej nie przebija (użyj --force albo wyłącz symulację).")
    if sim:
        err(f"Plan (symulacja, nic nie usuwam): {len(sel)} pozycji, ok. {core.fmt_size(total)}")
        core.run_clean(sel, True, err)
        return EXIT_OK
    journal: list = []
    res = core.run_clean(sel, False, err, journal)
    history.record(journal, res.freed, res.trashed)
    summary = {"freed": res.freed, "problems": res.problems, "items": len(journal)}
    if as_json:
        json.dump(summary, out)
        out.write("\n")
    else:
        out.write(f"Zwolniono ok. {core.fmt_size(res.freed)} ({len(journal)} pozycji, błędy: {res.problems}).\n")
    return EXIT_ERR if res.problems else EXIT_OK


PLAN_SCHEMA = 1
PLAN_GROWTH = 1.25  # pozycja, ktora od planu urosla bardziej, nie jest juz tym, co ogladal czlowiek
PLAN_SLACK = 1024 * 1024


def plan_document(cats: list, sel: list) -> dict:
    """Plan do przejrzenia: tylko opis pozycji (kategoria, nazwa, sciezki, rozmiar). Polecen ani pakietow nie zapisujemy -
    plan nie moze byc nosnikiem polecen wykonywanych potem jako administrator."""
    key = {id(e): c.key for c in cats for e in c.entries}
    return {"schema": PLAN_SCHEMA, "version": __version__, "time": int(time.time()),
            "items": [{"category": key.get(id(e), ""), "label": e.label, "size": e.size, "root": bool(e.root),
                       "paths": list(e.paths)} for e in sel]}


def load_plan(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, ValueError) as ex:
        raise ValueError(f"nie można wczytać planu: {ex}") from None
    items = plan.get("items") if isinstance(plan, dict) else None
    if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA or not isinstance(items, list) or not all(
            isinstance(i, dict) and isinstance(i.get("label"), str) and isinstance(i.get("category"), str)
            and isinstance(i.get("size"), int) and isinstance(i.get("paths"), list) for i in items):
        raise ValueError("to nie jest plan TidyDisk (zły schemat)")
    return plan


def apply_plan(cats: list, sel: list, plan: dict) -> tuple:
    """(do_wykonania, pominiete_powody). Wykonujemy tylko pozycje, ktore sa i w planie, i w swiezym wyborze `sel`
    (te same zasady bezpieczenstwa co zwykle `clean`), o tych samych sciezkach i nieznacznie wiekszym rozmiarze."""
    key = {id(e): c.key for c in cats for e in c.entries}
    fresh = {(key.get(id(e), ""), e.label): e for e in sel}
    run, skipped = [], []
    for it in plan["items"]:
        e = fresh.get((it["category"], it["label"]))
        if e is None:
            skipped.append(f"{it['label']}: nie jest już bezpieczną, zaznaczoną pozycją")
        elif list(e.paths) != it["paths"]:
            skipped.append(f"{it['label']}: zmieniły się ścieżki")
        elif e.size > it["size"] * PLAN_GROWTH + PLAN_SLACK:
            skipped.append(f"{it['label']}: urosła od planu ({core.fmt_size(it['size'])} -> {core.fmt_size(e.size)})")
        else:
            run.append(e)
    return run, skipped


def _disk_label_match(cats: list, key: str, entry_dict: dict, disk: str) -> bool:
    for c in cats:
        if c.key == key:
            for e in c.entries:
                if e.label == entry_dict["label"] and _entry_disk_ok(e, disk):
                    return True
    return False


if __name__ == "__main__":
    sys.exit(main())
