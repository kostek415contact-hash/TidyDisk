"""Ustawienia programu (plik JSON w ~/.config/tidydisk/settings.json, dostep tylko dla Ciebie).

Wszystkie wartosci maja domyslne, a wczytane dane sa sprawdzane (typ, zakres) - zly wpis w pliku
nigdy nie psuje programu. Bez zaleznosci od Qt.
"""
from __future__ import annotations

import json
import math
import os
import urllib.parse

from . import osal, rules

FILE = "~/.config/tidydisk/settings.json" if osal.SYSTEM == "linux" else str(osal.config_dir() / "settings.json")
LEGACY_AI_FILE = "~/.config/tidydisk/ai.json" if osal.SYSTEM == "linux" else str(osal.config_dir() / "ai.json")

# (klucz, domyslna wartosc, minimum, maksimum) - dla liczb; dla reszty min/max = None
SPEC = {
    # ogolne
    "trash_mine": (True, None, None),
    "review_each": (True, None, None),
    "review_safe_together": (True, None, None),  # przy review_each: pozycje "Bezpieczne" w jednym oknie zamiast po kolei
    "dry_run": (False, None, None),
    "anonymize": (True, None, None),
    "show_private_names": (False, None, None),
    "show_log": (False, None, None),
    "search_mode": ("assisted", None, None),  # algorithm | assisted | ai_only
    "theme": ("fedora", None, None),  # wyglad: fedora | modern | modern-light | system
    "language": ("auto", None, None),  # auto | pl | en (czesc napisow; reszta zostaje po polsku)
    "auto_analysis": (True, None, None),
    # algorytm (bez AI)
    "min_score": (45, 20, 90),
    "auto_score": (75, 50, 99),
    "dup_min_mb": (2, 1, 1024),
    "dup_budget_s": (45, 5, 600),
    "analysis_depth": (3, 1, 6),
    "scan_parallel": (1, 1, 4),  # ile miejsc (dom, dyski) skanowac rownolegle (1 = po kolei; pomiar: na goracym cache rownolegle bywa wolniejsze)
    # AI - polaczenie
    "ai_url": ("", None, None),
    "ai_key": ("", None, None),
    "ai_model": ("", None, None),
    "ai_timeout_s": (600, 30, 3600),
    # AI - zachowanie
    "ai_auto": (True, None, None),
    "ai_inspect": (True, None, None),
    "tray": (True, None, None),  # zamkniecie okna w trakcie pracy = praca w tle (ikona w zasobniku)
    "ai_cache_days": (30, 0, 365),  # jak dlugo pamietac oceny AI (0 = wylaczone)
    "ai_parallel": (2, 1, 8),  # ile zapytan o foldery naraz
    "ai_skip_inside": (True, None, None),  # nie oceniaj wnetrza folderow uznanych za 'caly do usuniecia'
    "ai_mine": (True, None, None),  # czy AI moze samo zaznaczac pozycje z \"Twoich plikow\"
    "ai_stage_folders": (True, None, None),
    "ai_stage_verify": (True, None, None),
    "ai_risk": ("niskie", None, None),  # 'niskie' | 'srednie': jakie ryzyko model moze zaznaczyc sam
    "ai_temperature": (0.1, 0.0, 1.0),
    "ai_batch_files": (8, 2, 30),
    "ai_verify_batch": (1, 1, 8),  # ile pozycji recenzent ocenia w jednym zapytaniu
    "ai_batch_folders": (25, 5, 60),
    "ai_pool_limit": (200, 20, 1000),
    "ai_folder_min_mb": (50, 1, 10240),
    "ai_folder_limit": (300, 20, 1500),
    # prompty: puste = domyslny. Edytowalna jest czesc z ZASADAMI; format odpowiedzi (JSON) jest stały.
    "prompt_triage": ("", None, None),
    "prompt_folders": ("", None, None),
    "prompt_verify": ("", None, None),
    "prompt_ask": ("", None, None),
    "prompt_extra": ("", None, None),  # dodatkowe zasady uzytkownika dopisywane do kazdego promptu
    # ochrona
    "protected_paths": ([], None, None),
}
for _k in rules.KEYS:  # reguly tak/nie: co wolno proponowac (domyslnie wszystko)
    SPEC["rule_" + _k] = (True, None, None)
RISKS = ("niskie", "srednie")
SEARCH_MODES = ("algorithm", "assisted", "ai_only")
AI_ONLY_MIN_SCORE = 25  # w trybie tylko-AI algorytm podaje szerszą listę kandydatów, ale niczego nie zaznacza
# Stan uzywany przez reszte programu bez czytania pliku przy kazdej pozycji; ustawia go apply().
RUNTIME: dict = {"search_mode": "assisted", "temperature": 0.1, "protected": [], "rules_off": [], "risks": ("niskie",), "ai_mine": True}
PROMPT_MAX = 8000


def local_url(url: str) -> bool:
    """Czy adres wskazuje na ten komputer: http(s) + host 127.0.0.1 / localhost / ::1, bez 'uzytkownik:haslo@'
    (adres w rodzaju http://127.0.0.1:80@obcy.pl prowadzi do obcego hosta)."""
    try:
        u = urllib.parse.urlsplit(url)
        return (u.scheme in ("http", "https") and u.username is None and u.password is None
                and u.hostname in ("127.0.0.1", "localhost", "::1"))
    except ValueError:
        return False


def defaults() -> dict:
    return {k: (list(v[0]) if isinstance(v[0], list) else v[0]) for k, v in SPEC.items()}


def _clean(key: str, value):
    """Zwraca poprawna wartosc albo domyslna, gdy typ/zakres sie nie zgadza."""
    default, lo, hi = SPEC[key]
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, (int, float)) and not isinstance(default, bool) and isinstance(value, float) \
            and not math.isfinite(value):
        return default  # NaN / Infinity z pliku JSON
    if isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        return int(min(max(value, lo), hi))
    if isinstance(default, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        return float(min(max(value, lo), hi))
    if isinstance(default, list):
        if not isinstance(value, list):
            return list(default)
        out = []
        for p in value:
            if isinstance(p, str) and p.strip():
                p = os.path.normpath(os.path.expanduser(p.strip()))
                if p.startswith("/") and p not in out:
                    out.append(p)
        return out
    if key == "ai_risk":
        return value if value in RISKS else default
    if key == "ai_url":
        value = value.strip() if isinstance(value, str) else ""
        return value if (not value or local_url(value)) else ""  # nielokalny adres = brak (wykrywanie samo)
    if key == "theme":
        return value if value in ("fedora", "modern", "modern-light", "system") else default
    if key == "language":
        return value if value in ("auto", "pl", "en") else default
    if key == "search_mode":
        return value if value in SEARCH_MODES else default
    if key.startswith("prompt_"):
        return value.strip()[:PROMPT_MAX] if isinstance(value, str) else default
    return value.strip() if isinstance(value, str) else default


def sanitize(data) -> dict:
    out = defaults()
    if isinstance(data, dict):
        for k in SPEC:
            if k in data:
                out[k] = _clean(k, data[k])
    if out["auto_score"] < out["min_score"]:  # prog zaznaczania nie moze byc nizszy niz prog propozycji
        out["auto_score"] = out["min_score"]
    return out


def path() -> str:
    return os.path.expanduser(os.environ.get("FC_CONFIG") or FILE)  # FC_CONFIG / --config: inny plik ustawien


def load(env: bool = True) -> dict:
    """Ustawienia z pliku (z migracja starego ai.json) i zmiennych FC_AI_URL / FC_AI_KEY / FC_AI_MODEL
    (zmienne tylko przy odczycie: env=False daje to, co naprawde jest w pliku - do zapisu)."""
    data: dict = {}
    for p in (os.path.expanduser(LEGACY_AI_FILE), path()):  # nowszy plik nadpisuje stary
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict):
            continue
        if p.endswith("ai.json"):
            raw = {"ai_url": raw.get("url", ""), "ai_key": raw.get("key", ""), "ai_model": raw.get("model", ""),
                   "ai_auto": raw.get("auto", "1") != "0", "ai_inspect": raw.get("inspect", "1") != "0"}
        data.update(raw)
    try:
        cfg = sanitize(data)
    except (ValueError, TypeError, OverflowError):  # zly wpis nigdy nie moze zatrzymac programu
        cfg = defaults()
    if not env:
        return cfg
    for env, k in (("FC_AI_URL", "ai_url"), ("FC_AI_KEY", "ai_key"), ("FC_AI_MODEL", "ai_model")):
        if os.environ.get(env):
            val = os.environ[env].strip()
            if k != "ai_url" or local_url(val):
                cfg[k] = val
    return cfg


def save(cfg: dict) -> bool:
    """Zapisuje (atomowo, tryb 0600: w pliku moze byc klucz API)."""
    p = path()
    try:
        d = os.path.dirname(p)
        os.makedirs(d, mode=0o700, exist_ok=True)
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
        tmp = p + ".tmp"
        try:
            os.unlink(tmp)  # stary plik tymczasowy (moze miec inne prawa albo byc symlinkiem)
        except OSError:
            pass
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            os.fchmod(f.fileno(), 0o600)
            json.dump(sanitize(cfg), f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
        return True
    except OSError:
        return False


def update(changes: dict) -> dict:
    cfg = load(env=False)
    cfg.update({k: v for k, v in changes.items() if k in SPEC})
    cfg = sanitize(cfg)
    save(cfg)
    apply(cfg)  # zapisane = od razu w mocy (pamiec podreczna ryzyk, regul, ochrony)
    return cfg


def export_text(cfg: dict, with_key: bool = False) -> str:
    data = sanitize(cfg)
    if not with_key:
        data["ai_key"] = ""
    return json.dumps(data, ensure_ascii=False, indent=2)


def import_text(text: str) -> dict:
    """Wczytuje ustawienia z tekstu JSON (blad -> ValueError). Klucz API z importu jest ignorowany, gdy pusty."""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("plik ustawień musi być obiektem JSON")
    cur = load(env=False)
    new = sanitize({**cur, **data})
    new["ai_key"] = cur["ai_key"]  # adresu i klucza AI nie przenosimy z pliku: obcy plik nie moze ich podmienic
    new["ai_url"] = cur["ai_url"]
    return new


def is_protected(p: str, protected: list) -> bool:
    """Czy sciezka lezy w chronionym przez uzytkownika miejscu (albo jest nim)."""
    p = os.path.normpath(p)
    return any(p == q or p.startswith(q.rstrip("/") + "/") for q in protected)


def apply(cfg: dict) -> dict:
    """Wprowadza ustawienia w zycie: progi algorytmu, ochrona sciezek, temperatura modelu."""
    cfg = sanitize(cfg)
    RUNTIME["temperature"] = cfg["ai_temperature"]
    prot = list(cfg["protected_paths"])
    for q in list(prot):  # tez rozwiazane symlinki, bo skan widzi sciezki rzeczywiste
        real = os.path.realpath(q)
        if real not in prot:
            prot.append(real)
    RUNTIME["protected"] = prot
    RUNTIME["rules_off"] = off_rules(cfg)
    RUNTIME["risks"] = ("niskie",) if cfg["ai_risk"] == "niskie" else ("niskie", "srednie")
    RUNTIME["ai_mine"] = bool(cfg["ai_mine"])
    from . import core  # lokalnie: settings.py zostaje bez zaleznosci przy imporcie
    RUNTIME["search_mode"] = cfg["search_mode"]
    core.ADVICE_AUTO = 101 if cfg["search_mode"] == "ai_only" else cfg["auto_score"]  # 101 = algorytm nie zaznacza sam
    return cfg


_TOUCH_CACHE: list = [None, None]  # [krotka chronionych, (zbior, prefiksy, przodkowie)]


def _touch_index(protected) -> tuple:
    key = tuple(protected)
    if _TOUCH_CACHE[0] != key:
        qs = {q.rstrip("/") or "/" for q in key}
        pre = tuple(q + "/" for q in qs)
        anc = set()  # kazdy prefiks q konczacy sie tuz przed '/', czyli sciezki p, dla ktorych q.startswith(p + "/")
        for q in qs:
            k = q.find("/")
            while k >= 0:
                anc.add(q[:k])
                k = q.find("/", k + 1)
        _TOUCH_CACHE[:] = [key, (qs, pre, anc)]
    return _TOUCH_CACHE[1]


def touches(p: str, protected: list) -> bool:
    """Czy usuniecie sciezki dotknelo by chronionego miejsca: sciezka lezy w nim ALBO je zawiera (folder nadrzedny)."""
    p = os.path.normpath(p)
    qs, pre, anc = _touch_index(protected)
    return p in qs or p.startswith(pre) or p.rstrip("/") in anc


def off_rules(cfg: dict) -> list:
    """Klucze regul wylaczonych przez uzytkownika."""
    return [k for k in rules.KEYS if not cfg.get("rule_" + k, True)]


def effective_min_score(cfg: dict) -> int:
    """Najnizsza pewnosc propozycji z uwzglednieniem trybu: w trybie 'tylko AI' szersza lista kandydatow."""
    return min(cfg["min_score"], AI_ONLY_MIN_SCORE) if cfg["search_mode"] == "ai_only" else cfg["min_score"]
