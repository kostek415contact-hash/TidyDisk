"""Skan wszystkich miejsc (dom + dyski danych) bez Qt: wspolny dla okna i trybu w tle (Etap B)."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import changes, core, scanner, settings
from .progress import load_scanstats, save_scanstats


def scan_all(cfg: dict, cancel=None, report=None, on_merge=None):
    """Zwraca polaczony ScanResult (albo None). report(n, t, path, ri, nroots, root_opis, base, nazwy_etapow, etap, tekst, ulamek)
    jest wolane przy postepie; ulamek 0..1 albo -1 gdy nieznany."""
    cancel = cancel or (lambda: False)
    pure = cfg["search_mode"] == "ai_only"  # tylko AI: zadnego oceniania, duplikatow ani wersji
    hc = str(Path.home() / ".local/share/tidydisk/hashcache.json")
    if not pure:
        scanner.load_hash_cache(hc)  # kolejne skany nie licza od nowa skrotow niezmienionych plikow
    roots = []
    for r, _d in core.cleanup_roots():
        if r not in roots:
            roots.append(r)
    names = ["Przeglądanie plików"] if pure else ["Przeglądanie plików", "Pakiety rpm", "Duplikaty"]
    home = str(Path.home())
    hist = load_scanstats()
    wts = [hist.get(r, 0) for r in roots]
    if not all(wts):
        wts = [1] * len(roots)
    wsum = float(sum(wts) or 1)

    lock = threading.Lock()
    frac = [0.0] * len(roots)  # postep kazdego miejsca 0..1 (miejsca skanowane rownolegle)
    counted = [0] * len(roots)  # ile plikow juz sprawdzono w kazdym miejscu
    unknown = [False] * len(roots)

    def overall(ri, st, f_in, hist_total):
        """Ulamek calosci = suma postepow miejsc wg wag; etap 1 = 70%, rpm = 5%, duplikaty = 25%."""
        f_root = 0.0 if f_in is None else ({0: f_in} if pure else {0: 0.7 * f_in, 1: 0.7 + 0.05 * f_in, 2: 0.75 + 0.25 * f_in})[st]
        frac[ri - 1] = max(frac[ri - 1], f_root)
        unknown[ri - 1] = st == 0 and not hist_total
        if any(unknown):
            return -1.0  # nie znam rozmiaru poprzedniego skanu: postep nieokreslony
        return sum(w * f for w, f in zip(wts, frac)) / wsum

    def on_progress(n, t, path, ri, root):
        if report is None:
            return
        shown = ("~" + root[len(home):]) if root.startswith(home) else root
        with lock:  # wywolania z kilku watkow wchodza do okna po kolei
            if path == "@rpm":
                st, txt, f_in = 1, "sprawdzam, które pakiety rpm są już zainstalowane", 0.0
            elif path == "@dup":
                st = 2
                txt = f"porównuję pliki o tym samym rozmiarze - grupa {n} z {t}" if t else "szukam duplikatów …"
                f_in = (n / t) if t else 0.0
            else:
                st = 0
                counted[ri - 1] = n
                b = sum(counted) - n
                cur = ("~" + path[len(home):]) if path.startswith(home) else path
                txt = f"sprawdzono {b + n:,} plików, teraz: …{cur[-48:]}".replace(",", " ")
                f_in = min(1.0, n / hist[root]) if hist.get(root) else None
            report(n, t, path, ri, len(roots), shown, sum(counted) - counted[ri - 1], names, st, txt,
                   overall(ri, st, f_in, hist.get(root, 0)))

    def one(ri, root):
        return scanner.scan(
            root, core.KB, max_depth=cfg["analysis_depth"], min_score=settings.effective_min_score(cfg),
            dup_min=cfg["dup_min_mb"] * 1024 * 1024, dup_budget=float(cfg["dup_budget_s"]),
            progress=lambda n, t, p, ri=ri, root=root: on_progress(n, t, p, ri, root),
            cancel=cancel, advise=not pure,
            **({"top_n": 10**6, "keep_min": 1024 * 1024} if pure else {}),
        )

    par = max(1, min(int(cfg.get("scan_parallel", 1) or 1), len(roots) or 1))
    results: list = []
    if par == 1:
        for ri, root in enumerate(roots, 1):
            if cancel():
                break
            results.append(one(ri, root))
    elif roots:
        with ThreadPoolExecutor(max_workers=par) as ex:  # miejsca (dom, osobne dyski) skanujemy rownolegle; wynik w tej samej kolejnosci
            futs = [ex.submit(one, ri, root) for ri, root in enumerate(roots, 1)]
            for f in futs:
                results.append(f.result())
    if not pure:
        scanner.save_hash_cache(hc)
    if not cancel():
        for r, res in zip(roots, results):
            hist[r] = max(1, res.nfiles)
        save_scanstats(hist)
    if on_merge is not None:
        on_merge()
    merged = scanner.merge_results(results, 10**6 if pure else 1000) if results else None
    if merged is not None and not cancel():
        try:
            changes.record(merged.nodes)
        except Exception:  # noqa: BLE001 - porownanie jest dodatkiem, nie moze przerwac skanu
            pass
    return merged
