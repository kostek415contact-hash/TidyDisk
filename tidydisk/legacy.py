"""Migracja z poprzedniej nazwy programu (Fedora Cleaner -> TidyDisk): ustawienia, dane i timery systemd.

Nic nie jest kasowane bez kopii: katalogi sa PRZENOSZONE (rename) tylko gdy nowy jeszcze nie istnieje."""
from __future__ import annotations

import os
import re
from pathlib import Path

OLD = "fedora-cleaner"
NEW = "tidydisk"
OLD_PKG = "fedora_cleaner"
UNIT_SUFFIXES = ("check", "ai")


def migrate_dirs(home: str | Path | None = None) -> list:
    """Przenosi ~/.config/fedora-cleaner i ~/.local/share/fedora-cleaner pod nowa nazwe. Zwraca liste przeniesionych."""
    if os.environ.get("TIDYDISK_NO_MIGRATE"):
        return []
    h = Path(home) if home else Path.home()
    moved = []
    for base in (".config", ".local/share"):
        old, new = h / base / OLD, h / base / NEW
        try:
            if old.is_dir() and not new.exists():
                os.rename(old, new)
                moved.append(str(new))
        except OSError:
            pass
    return moved


def migrate_units(unit_dir: Path, systemctl=None) -> list:
    """Stare timery systemd (fedora-cleaner-check/-ai) zamienia na nowe (tidydisk-*): przepisuje pliki z nowymi
    nazwami, wylacza stare i wlacza nowe. Zwraca liste nazw przeniesionych jednostek."""
    done = []
    for suf in UNIT_SUFFIXES:
        old_t, old_s = unit_dir / f"{OLD}-{suf}.timer", unit_dir / f"{OLD}-{suf}.service"
        if not old_t.exists():
            continue
        new_name = f"{NEW}-{suf}"
        try:
            for src, ext in ((old_s, "service"), (old_t, "timer")):
                if src.exists() and not (unit_dir / f"{new_name}.{ext}").exists():  # nowszych ustawien nie nadpisujemy
                    text = src.read_text(encoding="utf-8")
                    from . import schedule
                    text = re.sub(r'Environment="?PYTHONPATH=[^\n"]*(?:fedora[-_]cleaner)[^\n"]*"?', lambda _m: f"Environment={schedule._env_line()}", text)
                    for _o in (OLD_PKG, OLD):  # nazwy jednostek/modulu, ale nie czlony sciezek (PYTHONPATH=/home/u/fedora-cleaner)
                        text = re.sub(r"(?<![/\\\w.-])" + re.escape(_o), NEW, text)
                    (unit_dir / f"{new_name}.{ext}").write_text(text, encoding="utf-8")
        except OSError:
            continue
        if systemctl:
            systemctl("disable", "--now", f"{OLD}-{suf}.timer")
        for p in (old_t, old_s):
            p.unlink(missing_ok=True)
        if systemctl:
            systemctl("daemon-reload")
            systemctl("enable", "--now", f"{new_name}.timer")
        done.append(new_name)
    return done
