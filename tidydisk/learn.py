"""Uczenie sie z decyzji uzytkownika (czysty Python, bez zaleznosci, tylko lokalnie).

Model: regresja logistyczna uczona SGD na cechach pliku (rozszerzenie, folder najwyzszego poziomu,
ocena, sygnaly algorytmu, rozmiar, bazowa pewnosc). Przy kazdym prawdziwym czyszczeniu zapisujemy,
co zaznaczyles (usunieto) i czego nie ruszyles mimo wysokiej pewnosci. Z czasem pewnosc
koryguje sie o Twoje przyzwyczajenia. Dane leza w ~/.local/share/tidydisk/ i nigdzie nie wychodza.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from pathlib import Path

from . import fsutil, kb, osal

MAX_SAMPLES = 5000
MIN_SAMPLES = 8  # ponizej tylu przykladow model nic nie zmienia
FULL_AT = 60  # przy tylu przykladach korekta ma pelna sile
MAX_SHIFT = 30  # najwiekszy wplyw modelu na pewnosc (punkty)
PRIOR_SLOPE = 0.07  # waga bazowej pewnosci: p ~ sigmoid(0.07 * (score - 60))

_NUM = re.compile(r"\d+")
# kod powodu (kb.REASONS) -> nazwa cechy w learn.json (nazwy zostaja jak byly, zeby nie psuc zapisanej nauki)
KEYWORDS = (
    ("dup", "dup"), ("installer", "installer"), ("partial", "partial"), ("extracted", "extracted"),
    ("rpm_installed", "rpm_installed"), ("archive", "archive"), ("tempbak", "temp"), ("coredump", "coredump"),
    ("oldver", "oldver"), ("copyname", "copyname"), ("log", "log"), ("recreatable", "recreatable"), ("loc_review", "loc_review"), ("loc_safe", "loc_safe"),
)


def sigmoid(x: float) -> float:
    x = max(-30.0, min(30.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def features(path: str, size: int, rating: str, score: int, reasons: list, home: str) -> dict:
    """Rzadki wektor cech: {nazwa: wartosc}."""
    f: dict = {"bias": 1.0, "score": (score - 60) / 20.0, "rating=" + rating: 1.0}
    name = os.path.basename(path)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name.strip(".") else ""
    if ext and len(ext) <= 8:
        f["ext=" + ext] = 1.0
    if osal.is_windows():
        path, home = path.replace("\\", "/"), home.replace("\\", "/")
    rel = path[len(home) + 1:] if path.startswith(home + "/") else path.lstrip("/")
    parts = rel.split("/")
    if parts and parts[0]:
        f["top=" + _NUM.sub("#", parts[0])[:30]] = 1.0
    if len(parts) > 1:
        f["dir2=" + _NUM.sub("#", parts[0])[:20] + "/" + _NUM.sub("#", parts[1])[:20]] = 1.0
    f["size"] = max(0.0, min(math.log10(max(size, 1)) - 6.0, 4.0)) / 2.0  # 1 MB -> 0, 10 GB -> 2
    for code, key in KEYWORDS:
        if kb.has_reason(reasons, code):
            f["sig=" + key] = 1.0
    return f


class Learner:
    def __init__(self, directory) -> None:
        self.dir = Path(directory)
        self.samples: list = []  # [(cechy, etykieta, waga)]
        self.w: dict = {}
        self.ignored: list = []
        self._load()

    # -- zapis / odczyt
    def _load(self) -> None:
        try:
            data = json.loads((self.dir / "learn.json").read_text(encoding="utf-8"))
            self.ignored = [str(p) for p in data.get("ignored", [])]
            good = []
            for s in data.get("samples", []):  # jeden zly sampel nie kasuje reszty ani listy "nie proponuj"
                try:
                    f, y, w = s[0], int(s[1]), float(s[2])
                except (ValueError, TypeError, IndexError, KeyError):
                    continue
                if isinstance(f, dict) and math.isfinite(w) and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in f.values()):
                    good.append((f, y, w))
            self.samples = good[-MAX_SAMPLES:]
        except (OSError, ValueError, TypeError, IndexError, AttributeError):
            self.samples, self.ignored = [], []
        self.train()

    def save(self) -> bool:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            fsutil.atomic_write(self.dir / "learn.json", json.dumps(
                {"samples": self.samples[-MAX_SAMPLES:], "ignored": self.ignored, "saved": int(time.time())}, ensure_ascii=True))
            return True
        except (OSError, ValueError):
            return False

    # -- model
    def train(self, epochs: int = 120, lr: float = 0.15, l2: float = 0.01) -> None:
        w = {"score": PRIOR_SLOPE * 20.0}  # start = sama bazowa pewnosc
        w["bias"] = 0.0
        n = len(self.samples)
        if n < MIN_SAMPLES:
            self.w = w
            return
        data = self.samples
        for ep in range(epochs):
            step = lr / (1.0 + ep * 0.05)
            for feats, y, weight in data:
                z = sum(w.get(k, 0.0) * v for k, v in feats.items())
                err = (y - sigmoid(z)) * weight
                for k, v in feats.items():
                    w[k] = w.get(k, 0.0) + step * (err * v - l2 * w.get(k, 0.0))
        self.w = w

    def p_delete(self, feats: dict) -> float:
        return sigmoid(sum(self.w.get(k, 0.0) * v for k, v in feats.items()))

    @staticmethod
    def p_prior(feats: dict) -> float:
        return sigmoid(PRIOR_SLOPE * 20.0 * feats.get("score", 0.0))

    def strength(self) -> float:
        n = len(self.samples)
        return 0.0 if n < MIN_SAMPLES else min(1.0, n / FULL_AT)

    def adjust(self, score: int, feats: dict) -> tuple:
        """(nowa_pewnosc, zmiana). Nigdy nie podnosi pewnosci 'Twoich plikow' ponad bazowa (to robi tylko uzytkownik)."""
        k = self.strength()
        if not k:
            return score, 0
        shift = int(round(MAX_SHIFT * k * 2 * (self.p_delete(feats) - self.p_prior(feats))))
        shift = max(-MAX_SHIFT, min(MAX_SHIFT, shift))
        if feats.get("rating=mine"):
            shift = min(shift, 0)
        return max(0, min(99, score + shift)), shift

    # -- uczenie sie
    def record(self, positives: list, negatives: list, weak: float = 0.5) -> int:
        """Zapisuje decyzje: positives = (cechy) usuniete, negatives = (cechy) zostawione mimo propozycji."""
        for f in positives:
            self.samples.append((f, 1, 1.0))
        for f in negatives:
            self.samples.append((f, 0, weak))
        self.samples = self.samples[-MAX_SAMPLES:]
        self.train()
        self.save()
        return len(positives) + len(negatives)

    # -- 'nie proponuj wiecej'
    def ignore(self, path: str) -> None:
        if path not in self.ignored:
            self.ignored.append(path)
            self.save()

    def is_ignored(self, path: str) -> bool:
        return any(path == p or path.startswith(p.rstrip("/\\") + "/") or (osal.is_windows() and path.startswith(p.rstrip("/\\") + "\\"))
                   for p in self.ignored)

    # -- podglad nauki
    SKIP = ("bias", "score", "size")

    def learned(self, n: int = 15, min_count: int = 3) -> list:
        """[(cecha, waga, liczba_przykladow)] - czego model nauczyl sie najmocniej.
        waga > 0: zwykle usuwasz, waga < 0: zwykle zostawiasz."""
        count: dict = {}
        for feats, _y, _w in self.samples:
            for k in feats:
                if k not in self.SKIP and not k.startswith("rating="):
                    count[k] = count.get(k, 0) + 1
        rows = [(k, self.w.get(k, 0.0), c) for k, c in count.items() if c >= min_count]
        rows.sort(key=lambda r: -abs(r[1]))
        return rows[:n]

    def drop_feature(self, name: str) -> int:
        """Wyrzuca jedna cechę ze wszystkich zapamiętanych decyzji (model uczy się bez niej)."""
        hit = 0
        for feats, _y, _w in self.samples:
            if name in feats:
                del feats[name]
                hit += 1
        if hit:
            self.train()
            self.save()
        return hit

    def forget(self) -> None:
        self.samples, self.ignored, self.w = [], [], {}
        self.train()
        self.save()
