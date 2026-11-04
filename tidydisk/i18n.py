"""Tlumaczenia: klucz = polski tekst zrodlowy (jak w gettext), katalogi w locale/<jezyk>.json.
tr("Tekst") zwraca tlumaczenie albo - gdy go nie ma - oryginal, wiec brakujacy wpis niczego nie psuje."""
from __future__ import annotations

import json
import locale
import os
from pathlib import Path

DIR = Path(__file__).resolve().parent / "locale"
LANGUAGES = ("auto", "pl", "en")
_cat: dict = {}
_lang = ["pl"]


def system_language() -> str:
    code = (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "")
    if not code:
        try:
            code = locale.getlocale()[0] or ""
        except ValueError:
            code = ""
    return "pl" if code.lower().startswith("pl") else "en"


def set_language(lang: str) -> str:
    """Ustawia jezyk ('auto' = jezyk systemu); zwraca faktycznie uzyty ('pl' to jezyk zrodlowy, bez katalogu)."""
    global _cat
    lang = system_language() if lang == "auto" else lang
    lang = lang if lang in LANGUAGES else "pl"
    _lang[0] = lang
    _cat = {}
    if lang != "pl":
        try:
            raw = json.loads((DIR / f"{lang}.json").read_text(encoding="utf-8"))
            _cat = {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            _cat = {}
    return lang


def tr(text: str) -> str:
    return _cat.get(text, text)


def current() -> str:
    return _lang[0]
