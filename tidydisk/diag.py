"""Zrzut diagnostyczny: jeden plik tekstowy do wyslania razem z raportem. Bez klucza API i bez nazwy uzytkownika."""
from __future__ import annotations

import json
import platform
import shutil
import sys
import time
from pathlib import Path

from . import __version__, ai, ai_cache, background, schedule, settings


def build(detect_ai: bool = True) -> str:
    home = str(Path.home())
    L = [f"TidyDisk {__version__} - zrzut diagnostyczny", time.strftime("%Y-%m-%d %H:%M"), ""]
    L.append(f"System: {platform.platform()}")
    L.append(f"Python: {sys.version.split()[0]}")
    try:
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
        L.append(f"PyQt6: {PYQT_VERSION_STR}, Qt: {QT_VERSION_STR}")
    except ImportError:
        L.append("PyQt6: brak (tryb terminala)")
    try:
        du = shutil.disk_usage(home)
        L.append(f"Dysk domowy: wolne {du.free // 2**30} GB z {du.total // 2**30} GB")
    except OSError:
        pass
    L += ["", "Ustawienia (bez klucza API; długie prompty skrócone):"]
    cfg = json.loads(settings.export_text(settings.load()))
    for k, v in cfg.items():
        if isinstance(v, str) and len(v) > 80:
            cfg[k] = v[:80] + f"… ({len(v)} znaków)"
    L.append(json.dumps(cfg, ensure_ascii=False, indent=2))
    L += ["", "Ostatnia praca w tle:", background.describe_last() or "brak",
          json.dumps(background.last_run(), ensure_ascii=False)]
    L += ["", f"Harmonogram powiadomień: {'włączony' if schedule.is_enabled() else 'wyłączony'}; "
              f"ocena AI w tle: {'włączona' if schedule.is_ai_enabled() else 'wyłączona'}"]
    try:
        L.append(f"Pamięć ocen AI: {len(ai_cache.AICache(int(cfg.get('ai_cache_days', 30))))} wpisów")
    except Exception as ex:  # noqa: BLE001
        L.append(f"Pamięć ocen AI: błąd ({ex})")
    if detect_ai:
        try:
            host, models = ai.detect(1.0)
            L.append(f"Serwer AI: {host or 'nie znaleziono'}; modele: {', '.join((models or [])[:5]) or '-'}")
        except PermissionError:
            L.append("Serwer AI: odrzucił klucz API")
        except Exception as ex:  # noqa: BLE001
            L.append(f"Serwer AI: błąd ({ex})")
    return "\n".join(L).replace(home, "~") + "\n"
