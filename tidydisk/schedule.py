"""Harmonogram: timer systemd uzytkownika, ktory co jakis czas sprawdza dysk i wysyla powiadomienie KDE.

Nic nie usuwa, chyba ze wlaczysz --auto-clean (wtedy `clean --yes`: tylko pozycje Bezpieczne, bez AI).
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from . import osal

UNIT = "tidydisk-check"
UNIT_AI = "tidydisk-ai"  # osobny timer: skan + ocena AI w tle (Etap B)
INTERVALS = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}


def unit_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "systemd" / "user"


def package_parent() -> str:
    return str(Path(__file__).resolve().parent.parent)


def _unit_arg(text: str) -> str:
    """Wartosc do pliku jednostki systemd: '%' to znacznik specyfikatora, wiec podwajamy go."""
    return text.replace("%", "%%")


def _env_line() -> str:
    return '"PYTHONPATH=' + _unit_arg(package_parent()).replace('"', '\\"') + '"'


def calendar(every: str, at: str = "") -> str:
    """OnCalendar: 'weekly' albo np. 'Sun *-*-* 03:30:00' gdy podano godzine HH:MM."""
    if not at:
        return INTERVALS[every]
    hh, mm = at.split(":")
    if not (0 <= int(hh) < 24 and 0 <= int(mm) < 60):
        raise ValueError("godzina: HH:MM")
    t = f"{int(hh):02d}:{int(mm):02d}:00"
    return {"daily": f"*-*-* {t}", "weekly": f"Sun *-*-* {t}", "monthly": f"*-*-01 {t}"}[every]


def render_ai(every: str, at: str = "", mode: str = "") -> tuple:
    """(service, timer) dla pracy w tle: `tidydisk ai --notify` o najnizszym priorytecie."""
    cmd = _unit_arg(f"{shlex.quote(sys.executable if sys.executable.startswith('/') else '/usr/bin/python3')} -m tidydisk ai --notify -q --wait-ai 10"
                    + (f" --mode {mode}" if mode else ""))
    # Restart: gdy serwera AI jeszcze nie ma (kod 4) albo wystapil blad, proba za 15 min, najwyzej 4 razy na dobe;
    # TimeoutStopSec + KillMode=mixed: po SIGTERM dajemy czas na zapis pamieci ocen i wyniku
    service = ("[Unit]\nDescription=TidyDisk - skan i ocena AI w tle\nStartLimitIntervalSec=1d\nStartLimitBurst=4\n\n"
               f"[Service]\nType=oneshot\nEnvironment={_env_line()}\nExecStart={cmd}\nNice=19\nIOSchedulingClass=idle\n"
               "TimeoutStartSec=infinity\nTimeoutStopSec=5min\nKillMode=mixed\nRestart=on-failure\nRestartSec=15min\n"
               "SuccessExitStatus=3\n")
    timer = (f"[Unit]\nDescription=TidyDisk - cykliczna ocena AI w tle\n\n[Timer]\nOnCalendar={calendar(every, at)}\n"
             f"Persistent=true\nRandomizedDelaySec=30min\n\n[Install]\nWantedBy=timers.target\n")
    return service, timer


def enable_ai(every: str = "weekly", at: str = "", mode: str = "") -> str:
    if osal.SYSTEM != "linux":
        raise ValueError("Harmonogram (systemd) działa tylko na Linuksie; na Windows użyj Harmonogramu zadań (schtasks).")
    if every not in INTERVALS:
        raise ValueError("every: daily|weekly|monthly")
    d = unit_dir()
    d.mkdir(parents=True, exist_ok=True)
    service, timer = render_ai(every, at, mode)
    (d / f"{UNIT_AI}.service").write_text(service, encoding="utf-8")
    (d / f"{UNIT_AI}.timer").write_text(timer, encoding="utf-8")
    _systemctl("daemon-reload")
    code = _systemctl("enable", "--now", f"{UNIT_AI}.timer")
    return "włączony" if code == 0 else f"pliki zapisane w {d}, ale systemctl zwrócił kod {code}"


def disable_ai() -> str:
    if osal.SYSTEM != "linux":
        raise ValueError("Harmonogram (systemd) działa tylko na Linuksie; na Windows użyj Harmonogramu zadań (schtasks).")
    _systemctl("disable", "--now", f"{UNIT_AI}.timer")
    d = unit_dir()
    for ext in ("service", "timer"):
        (d / f"{UNIT_AI}.{ext}").unlink(missing_ok=True)
    _systemctl("daemon-reload")
    return "wyłączony"


def is_ai_enabled() -> bool:
    return (unit_dir() / f"{UNIT_AI}.timer").exists()


def render(every: str, min_free_gb: int, min_reclaim_gb: int, auto_clean: bool, at: str = "") -> tuple:
    """(tekst_service, tekst_timer)."""
    args = f"notify --min-free {int(min_free_gb)} --min-reclaim {int(min_reclaim_gb)}" + (" --auto-clean" if auto_clean else "")
    cmd = _unit_arg(f"{shlex.quote(sys.executable if sys.executable.startswith('/') else '/usr/bin/python3')} -m tidydisk {args}")
    service = (f"[Unit]\nDescription=TidyDisk - sprawdzenie dysku\n\n[Service]\nType=oneshot\n"
               f"Environment={_env_line()}\nExecStart={cmd}\nNice=19\nIOSchedulingClass=idle\n")
    timer = (f"[Unit]\nDescription=TidyDisk - cykliczne sprawdzenie\n\n[Timer]\nOnCalendar={calendar(every, at)}\n"
             f"Persistent=true\nRandomizedDelaySec=1h\n\n[Install]\nWantedBy=timers.target\n")
    return service, timer


def _systemctl(*a) -> int:
    try:
        return subprocess.run(["systemctl", "--user", *a], capture_output=True, timeout=30).returncode
    except (OSError, subprocess.SubprocessError):
        return 127


WIN_TASK = "TidyDisk-check"


def win_command() -> str:
    """Polecenie dla Harmonogramu zadan: .exe (po zbudowaniu PyInstallerem) albo `python -m tidydisk`."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" -m tidydisk'


def win_task_args(every: str, at: str, min_free_gb: int, min_reclaim_gb: int, command: str | None = None) -> list:
    """Argumenty `schtasks /Create` (bez 'schtasks'). Sprawdzanie dysku z powiadomieniem, nic nie usuwa."""
    if every not in INTERVALS:
        raise ValueError("every: daily|weekly|monthly")
    hh, mm = (at or "10:00").split(":")
    if not (0 <= int(hh) < 24 and 0 <= int(mm) < 60):
        raise ValueError("godzina: HH:MM")
    sc = {"daily": ["/SC", "DAILY"], "weekly": ["/SC", "WEEKLY", "/D", "SUN"], "monthly": ["/SC", "MONTHLY", "/D", "1"]}[every]
    tr = f"{command or win_command()} notify --min-free {int(min_free_gb)} --min-reclaim {int(min_reclaim_gb)}"
    return ["/Create", "/TN", WIN_TASK, "/TR", tr, *sc, "/ST", f"{int(hh):02d}:{int(mm):02d}", "/F"]


def _schtasks(*a) -> int:
    try:
        return subprocess.run(["schtasks", *a], capture_output=True, timeout=30).returncode
    except (OSError, subprocess.SubprocessError):
        return 127


def enable(every: str = "weekly", min_free_gb: int = 20, min_reclaim_gb: int = 5, auto_clean: bool = False, at: str = "") -> str:
    if osal.is_windows():
        if auto_clean:
            raise ValueError("Automatyczne czyszczenie w harmonogramie nie jest jeszcze dostępne na Windows (tylko sprawdzanie i powiadomienie).")
        code = _schtasks(*win_task_args(every, at, min_free_gb, min_reclaim_gb))
        return "włączony" if code == 0 else f"schtasks zwrócił kod {code}"
    if osal.SYSTEM != "linux":
        raise ValueError("Harmonogram (systemd) działa tylko na Linuksie; na Windows użyj Harmonogramu zadań (schtasks).")
    if every not in INTERVALS:
        raise ValueError("every: daily|weekly|monthly")
    d = unit_dir()
    d.mkdir(parents=True, exist_ok=True)
    service, timer = render(every, min_free_gb, min_reclaim_gb, auto_clean, at)
    (d / f"{UNIT}.service").write_text(service, encoding="utf-8")
    (d / f"{UNIT}.timer").write_text(timer, encoding="utf-8")
    _systemctl("daemon-reload")
    code = _systemctl("enable", "--now", f"{UNIT}.timer")
    return "włączony" if code == 0 else f"pliki zapisane w {d}, ale systemctl zwrócił kod {code}"


def disable() -> str:
    if osal.is_windows():
        _schtasks("/Delete", "/TN", WIN_TASK, "/F")
        return "wyłączony"
    if osal.SYSTEM != "linux":
        raise ValueError("Harmonogram (systemd) działa tylko na Linuksie; na Windows użyj Harmonogramu zadań (schtasks).")
    _systemctl("disable", "--now", f"{UNIT}.timer")
    d = unit_dir()
    for ext in ("service", "timer"):
        (d / f"{UNIT}.{ext}").unlink(missing_ok=True)
    _systemctl("daemon-reload")
    return "wyłączony"


def is_enabled() -> bool:
    if osal.is_windows():
        return _schtasks("/Query", "/TN", WIN_TASK) == 0
    return (unit_dir() / f"{UNIT}.timer").exists()


def should_notify(free: int, safe: int, min_free_gb: int, min_reclaim_gb: int) -> str:
    """Tekst powiadomienia albo '' gdy nic do zglaszania."""
    gb = 1024 ** 3
    low = free < min_free_gb * gb
    plenty = safe >= min_reclaim_gb * gb
    if low and plenty:
        return f"Mało miejsca ({free / gb:.0f} GB wolne). Można bezpiecznie odzyskać ok. {safe / gb:.1f} GB."
    if low:
        return f"Mało miejsca: wolne {free / gb:.0f} GB."
    if plenty:
        return f"Można bezpiecznie odzyskać ok. {safe / gb:.1f} GB."
    return ""


def notify(text: str) -> bool:
    """Powiadomienie pulpitu (KDE/GNOME) przez notify-send; na Windows dymek w zasobniku przez PowerShell."""
    if osal.is_windows():
        ps = ("Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
              "$n=New-Object System.Windows.Forms.NotifyIcon; $n.Icon=[System.Drawing.SystemIcons]::Information; "
              "$n.Visible=$true; $n.ShowBalloonTip(10000,'TidyDisk',$env:TIDYDISK_MSG,'Info'); Start-Sleep 11; $n.Dispose()")
        try:
            return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=40, capture_output=True,
                                  env=dict(os.environ, TIDYDISK_MSG=text)).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    exe = shutil.which("notify-send")
    if not exe:
        return False
    try:
        return subprocess.run([exe, "-a", "TidyDisk", "-i", "tidydisk", "TidyDisk", text],
                              timeout=10, capture_output=True).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def migrate_legacy_units() -> list:
    """Wywolywane przy starcie programu: stare timery 'fedora-cleaner-*' -> 'tidydisk-*' (po aktualizacji programu)."""
    from . import legacy
    try:
        return legacy.migrate_units(unit_dir(), _systemctl)
    except OSError:
        return []
