"""Pamiec ocen AI miedzy uruchomieniami (Etap A): przerwana ocena nie przepada, a kolejna pomija to, co juz ocenione.

Klucz = etap | podpis (model + prompty + tryb) | sciezka | rozmiar | znacznik zmiany (mtime pliku / liczba plikow folderu).
Zmiana modelu, promptu, trybu albo pliku = nowa ocena. Plik jest prywatny (0600) i trzyma tylko sciezki i krotkie uzasadnienia."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

from . import fsutil, osal

PATH = osal.data_dir() / "aicache.json"
MAX_ENTRIES = 300_000


def signature(*parts) -> str:
    return hashlib.sha1("\x1f".join(str(p) for p in parts).encode("utf-8", "replace")).hexdigest()[:12]


class AICache:
    def __init__(self, days: int = 30, path: Path | None = None) -> None:
        self.days = int(days)
        self.path = Path(path) if path else PATH
        self.data: dict = {}
        self.dirty = False
        self.hits = 0
        self._last = time.monotonic()
        self._lock = threading.Lock()
        self._written = None  # podpis pliku po naszym ostatnim zapisie
        self.load()

    def _disk_sig(self):
        try:
            st = os.stat(self.path)
        except OSError:
            return None
        return (st.st_ino, st.st_mtime_ns, st.st_size)

    @staticmethod
    def key(stage: str, sig: str, path: str, size: int, stamp) -> str:
        return f"{stage}|{sig}|{path}|{int(size)}|{int(stamp or 0)}"

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            items = raw.get("e", {}) if isinstance(raw, dict) else {}
            if not isinstance(items, dict):
                items = {}
        except FileNotFoundError:
            items = {}
        except (OSError, ValueError):
            items = {}
            try:  # uszkodzony plik zostaje do obejrzenia, zamiast zostac po cichu nadpisany
                self.path.replace(self.path.with_name(self.path.name + ".bad"))
            except OSError:
                pass
        limit = time.time() - self.days * 86400
        self.data = {k: v for k, v in items.items()
                     if isinstance(v, list) and len(v) >= 4 and isinstance(v[3], (int, float)) and v[3] >= limit}

    def get(self, stage: str, sig: str, path: str, size: int, stamp):
        if self.days <= 0:
            return None
        v = self.data.get(self.key(stage, sig, path, size, stamp))
        if v is None:
            return None
        self.hits += 1
        return (v[0], v[1], v[2])

    def put(self, stage: str, sig: str, path: str, size: int, stamp, verdict: tuple) -> None:
        if self.days <= 0:
            return
        with self._lock:
            self.data[self.key(stage, sig, path, size, stamp)] = [verdict[0], verdict[1], str(verdict[2])[:160], time.time()]
            self.dirty = True
        if time.monotonic() - self._last > 20:
            self.flush()

    def flush(self, force: bool = False) -> None:
        if self.days <= 0:
            return  # pamiec wylaczona (0 dni): nie nadpisujemy pliku pustym
        with self._lock:
            if not (self.dirty or force):
                return
            if len(self.data) > MAX_ENTRIES:  # najstarsze wypadaja
                keep = sorted(self.data.items(), key=lambda kv: -kv[1][3])[:MAX_ENTRIES]
                self.data = dict(keep)
            try:
                sig = self._disk_sig()
                if sig is None:
                    disk = {}
                elif sig == self._written:
                    disk = {}  # plik to nasz ostatni zapis: wszystkie jego wpisy sa juz w self.data
                else:
                    disk = AICache(self.days, self.path).data  # wpisy zapisane w miedzyczasie przez inny proces
                merged = {**disk, **self.data}
                if len(merged) > MAX_ENTRIES:
                    merged = dict(sorted(merged.items(), key=lambda kv: -kv[1][3])[:MAX_ENTRIES])
                self.data = merged
                fsutil.atomic_write(self.path, json.dumps({"v": 1, "e": self.data}, ensure_ascii=True, separators=(",", ":")))
                self._written = self._disk_sig()
                self.dirty = False
            except OSError:
                pass
            self._last = time.monotonic()

    def rows(self) -> list[dict]:
        """Wpisy pamieci podrecznej jako lista slownikow (do eksportu CSV/JSON), najnowsze pierwsze."""
        out = []
        for k, v in self.data.items():
            try:
                stage, sig, rest = k.split("|", 2)
                path, size, stamp = rest.rsplit("|", 2)
            except ValueError:
                continue
            out.append({"etap": stage, "sciezka": path, "rozmiar": int(size) if size.lstrip("-").isdigit() else 0,
                        "werdykt": v[0], "ryzyko": v[1], "uzasadnienie": v[2], "czas": int(v[3])})
        return sorted(out, key=lambda r: -r["czas"])

    def clear(self) -> None:
        with self._lock:
            self.data = {}
            self.dirty = False
            try:
                self.path.unlink()
            except OSError:
                pass

    def __len__(self) -> int:
        return len(self.data)
