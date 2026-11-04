"""Praca w tle bez okna (Etap B): skan + ocena AI jako zwykle zadanie o niskim priorytecie.

`tidydisk ai` (reczne albo z timera `schedule enable --ai`). Oceny trafiaja do pamieci ai_cache, wiec gdy potem
otworzysz okno i uruchomisz ocene AI, wszystko co juz ocenione pojawia sie od razu. Nic nie usuwa."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import ai, core, fsutil, osal, pipeline, schedule, settings
from .progress import ProgressTracker

DIR = osal.data_dir()
LOCK = DIR / "background.lock"
LASTRUN = DIR / "lastrun.json"
EXIT_OK, EXIT_ERR, EXIT_BUSY, EXIT_NO_AI = 0, 1, 3, 4


def lower_priority() -> None:
    """Niski priorytet CPU i dysku, zeby praca w tle nie zamulala pulpitu."""
    osal.lower_priority()
    exe = shutil.which("ionice")
    if exe:
        try:
            subprocess.run([exe, "-c3", "-p", str(os.getpid())], capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass


def last_run() -> dict:
    try:
        return json.loads(LASTRUN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def describe_last(d: dict | None = None) -> str:
    d = d if d is not None else last_run()
    if not d:
        return ""
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(d.get("time", 0)))
    st = d.get("stats") or {}
    state = "przerwane" if d.get("cancelled") else ("z błędem" if d.get("error") else "zakończone")
    out = (f"Ostatnia praca w tle: {when}, {state}, tryb {d.get('mode')}, plików {d.get('files', 0)}, "
           f"ocen AI z pamięci {st.get('z_pamieci', 0)}, do usunięcia wg AI {st.get('zaznaczone', 0)}.")
    return out + (f" Uwaga: {d['error']}" if d.get("error") else "")


def export_rows(rows: list, dest: str) -> int:
    """Zapisuje wyniki AI do pliku .json albo .csv (wg rozszerzenia); zwraca liczbe wierszy."""
    import csv
    import io
    import json
    if str(dest).lower().endswith(".json"):
        text = json.dumps({"schema": 1, "wyniki": rows}, ensure_ascii=False, indent=1) + "\n"
    else:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["etap", "sciezka", "rozmiar", "werdykt", "ryzyko", "uzasadnienie", "czas"])
        w.writeheader()
        for r in rows:  # komorki zaczynajace sie od =,+,-,@ neutralizujemy (formuly w arkuszu)
            w.writerow({k: ("'" + v if isinstance(v, str) and v[:1] in "=+-@" else v) for k, v in r.items()})
        text = buf.getvalue()
    fsutil.atomic_write(Path(dest), text)
    return len(rows)


def wait_for_ai(minutes: int, cancel, say, sleep=None, step: float = 30.0):
    """Czeka do `minutes` min az lokalny serwer AI odpowie (np. po starcie systemu); przerywalne."""
    sleep = sleep or (lambda sec: ai._sleep_cancel(sec, cancel))
    waited = 0.0
    while True:
        host, models = ai.detect()
        if (host is not None and models) or minutes <= 0 or waited >= minutes * 60 or cancel():
            return host, models
        if waited == 0:
            say(f"Serwer AI jeszcze nie odpowiada - czekam do {minutes} min.")
        sleep(step)
        waited += step


def run(mode: str | None = None, quiet: bool = False, notify: bool = False, say=None, wait_ai: int = 0) -> int:
    say = say or (lambda m: None if quiet else sys.stderr.write(m + "\n"))
    DIR.mkdir(parents=True, exist_ok=True)
    lock = open(LOCK, "w")
    if not osal.try_lock(lock):
        say("Inne przetwarzanie w tle już działa - kończę.")
        return EXIT_BUSY
    stop = {"v": False}
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, lambda *_a: stop.__setitem__("v", True))
        except (ValueError, OSError):
            pass
    lower_priority()
    cfg = settings.apply(settings.load())
    if mode:
        cfg = settings.sanitize({**cfg, "search_mode": mode})
        settings.apply(cfg)
    t0 = time.time()
    cancel = lambda: stop["v"]  # noqa: E731
    tracker = ProgressTracker()
    last_print = [0.0]

    def show(prefix, text, frac):
        if time.monotonic() - last_print[0] < 5:
            return
        last_print[0] = time.monotonic()
        pct, eta = tracker.update(frac)
        say(f"{prefix}{'' if pct is None else f' {pct}%'}{f' · pozostało {eta}' if eta else ''} - {text}")

    scan_error = ""
    try:
        res = pipeline.scan_all(cfg, cancel=cancel,
                                report=lambda n, t, p, ri, nr, root, b, names, st, txt, frac: show("Skan:", f"etap {st + 1}/{len(names)} {txt}", frac))
    except Exception as ex:  # noqa: BLE001 - nienadzorowany przebieg ma zawsze zostawic slad
        res, scan_error = None, f"Błąd skanowania: {ex}"
    info = {"time": int(t0), "mode": cfg["search_mode"], "files": getattr(res, "nfiles", 0), "cancelled": False, "stats": {},
            "advice": len(getattr(res, "advice", []) or [])}
    code = EXIT_OK
    if scan_error:
        info["error"] = scan_error
        say(scan_error)
        code = EXIT_ERR
    elif res is None or stop["v"]:
        info["cancelled"] = True
    elif cfg["search_mode"] != "algorithm":
        try:
            host, models = wait_for_ai(wait_ai, cancel, say)
        except PermissionError:
            host, models = None, []
            info["error"] = "Serwer AI odrzucił klucz API - sprawdź go w Ustawieniach (zakładka AI)."
        except Exception as ex:  # noqa: BLE001
            host, models = None, []
            info["error"] = ai.friendly_error(str(ex))
        if info.get("error"):
            say(info["error"])
            code = EXIT_ERR
        elif host is None or not models:
            info["error"] = "Nie znalazłem lokalnego serwera AI (Unsloth Studio / llama-server) - zapisuję tylko wynik skanu."
            say(info["error"])
            code = EXIT_NO_AI
        else:
            tracker.reset()
            model = ai.pick_model(models)
            say(f"Model: {model}")
            cur = {"t": ""}
            try:
                stats = ai.cascade(model, res.advice, res.nodes, res.top_files, host, str(Path.home()),
                                   roots=[r for r, _d in core.cleanup_roots()],
                                   on_status=lambda t: cur.__setitem__("t", t),
                                   on_progress=lambda d, t: show("AI:", cur["t"] or f"{d} z {t}", d / t if t else 0.0),
                                   cancel=cancel, cfg=cfg)
                info["stats"] = stats
                info["cancelled"] = bool(stats.get("przerwano"))
            except Exception as ex:  # noqa: BLE001
                info["error"] = ai.friendly_error(str(ex))
                code = EXIT_ERR
                say("Błąd oceny AI: " + info["error"])
    info["seconds"] = int(time.time() - t0)
    try:
        fsutil.atomic_write(LASTRUN, json.dumps(info, ensure_ascii=False))
    except OSError:
        pass
    say(describe_last(info))
    if notify and (info.get("error") or (info.get("stats") or {}).get("zaznaczone", 0) > 0):  # bez wyniku nie przeszkadzamy
        schedule.notify("Praca w tle zakończona. " + describe_last(info).replace("Ostatnia praca w tle: ", "") + " Otwórz TidyDisk.")
    return code
