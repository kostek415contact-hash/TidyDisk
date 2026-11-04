"""Dziennik czyszczen (co, ile, kiedy, jak) i przywracanie z kosza. Czysty Python, tylko lokalnie."""
from __future__ import annotations

import json
import os
import shutil
import time
import urllib.parse
from pathlib import Path

MAX_RUNS = 200
MAX_ITEMS = 500


def default_dir() -> Path:
    return Path.home() / ".local" / "share" / "tidydisk"


def _file(directory) -> Path:
    return Path(directory or default_dir()) / "history.json"


def load(directory=None) -> list:
    try:
        data = json.loads(_file(directory).read_text(encoding="utf-8"))
        return [r for r in data if isinstance(r, dict) and isinstance(r.get("items"), list)] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def record(items: list, freed: int, trashed: int, directory=None, when: float | None = None) -> bool:
    """Dopisuje przebieg czyszczenia (tylko pozycje zakonczone bez bledu). Najnowszy na poczatku."""
    if not items:
        return False
    run = {"ts": int(when if when is not None else time.time()), "freed": int(freed), "trashed": int(trashed),
           "items": [{"label": str(i["label"])[:120], "size": int(i["size"]), "how": i["how"],
                      "paths": [str(p) for p in i["paths"]][:20], "restored": False} for i in items[:MAX_ITEMS]]}
    runs = [run] + load(directory)
    try:
        f = _file(directory)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # zawiera sciezki
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(runs[:MAX_RUNS], fh, ensure_ascii=False)
        os.replace(tmp, f)
        return True
    except OSError:
        return False


def mark_restored(run_ts: int, path: str, directory=None) -> None:
    runs = load(directory)
    for r in runs:
        if r.get("ts") == run_ts:
            for it in r["items"]:
                if path in it.get("paths", []):
                    it["restored"] = True
    try:
        _file(directory).write_text(json.dumps(runs, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def restore_from_trash(path: str, trash_dir=None) -> tuple:
    """Przenosi z kosza (~/.local/share/Trash) z powrotem na pierwotne miejsce: (ok, komunikat)."""
    trash = Path(trash_dir or Path.home() / ".local" / "share" / "Trash")
    info_dir, files_dir = trash / "info", trash / "files"
    best = None
    try:
        names = sorted(os.listdir(info_dir))
    except OSError:
        return False, "Kosz jest pusty lub niedostępny."
    for n in names:
        if not n.endswith(".trashinfo"):
            continue
        try:
            txt = (info_dir / n).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        orig = date = ""
        for ln in txt.splitlines():
            if ln.startswith("Path="):
                orig = urllib.parse.unquote(ln[5:])
            elif ln.startswith("DeletionDate="):
                date = ln[13:]
        if orig == path and (files_dir / n[:-10]).exists() or (orig == path and os.path.islink(files_dir / n[:-10])):
            if best is None or date > best[0]:
                best = (date, n)
    if best is None:
        return False, "Nie ma tego w koszu (mógł zostać opróżniony)."
    src = files_dir / best[1][:-10]
    if os.path.lexists(path):
        return False, "Na tym miejscu jest już plik o tej nazwie."
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.move(str(src), path)
        (info_dir / best[1]).unlink(missing_ok=True)
    except OSError as ex:
        return False, f"Nie udało się przywrócić: {ex.strerror or ex}"
    return True, "Przywrócono."
