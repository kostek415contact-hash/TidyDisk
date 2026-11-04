"""Gry (Steam) i kontenery (Podman): pozycje do sprzatania, ktorych nie widac w zwyklych cache.

Czysty Python. Zwraca proste slowniki - Entry buduje core.scan.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

NON_STEAM_MIN = 2 ** 31  # identyfikatory gier spoza Steama (skroty) sa duze - ich prefiksow nie ruszamy


def steam_libraries(home: str) -> list:
    """Foldery steamapps wszystkich bibliotek Steama (bez powtorzen po realpath)."""
    bases = [f"{home}/.local/share/Steam", f"{home}/.steam/steam", f"{home}/.var/app/com.valvesoftware.Steam/.local/share/Steam"]
    found: list = []
    seen: set = set()

    def add(sa: str) -> None:
        real = os.path.realpath(sa)
        if os.path.isdir(real) and real not in seen:
            seen.add(real)
            found.append(real)

    for b in bases:
        add(os.path.join(b, "steamapps"))
        try:
            vdf = Path(b, "steamapps", "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in re.finditer(r'"path"\s+"([^"]+)"', vdf):
            add(os.path.join(m.group(1), "steamapps"))
    return found


def installed_apps(steamapps: str) -> dict:
    """{appid: nazwa gry} z appmanifest_*.acf."""
    out: dict = {}
    try:
        names = os.listdir(steamapps)
    except OSError:
        return out
    for n in names:
        m = re.fullmatch(r"appmanifest_(\d+)\.acf", n)
        if not m:
            continue
        try:
            txt = Path(steamapps, n).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        nm = re.search(r'"name"\s+"([^"]+)"', txt)
        out[m.group(1)] = nm.group(1) if nm else f"gra {m.group(1)}"
    return out


def steam_items(home: str) -> list:
    """[{'label','paths','group','appid','name','installed'}] - shadercache, osierocone compatdata, stare Proton."""
    items: list = []
    libs = steam_libraries(home)
    apps: dict = {}
    for sa in libs:
        apps.update(installed_apps(sa))
    for sa in libs:
        for group in ("shadercache", "compatdata"):
            base = os.path.join(sa, group)
            try:
                dirs = [d for d in os.scandir(base) if d.is_dir(follow_symlinks=False) and d.name.isascii() and d.name.isdigit()]
            except OSError:
                continue
            for d in dirs:
                if int(d.name) >= NON_STEAM_MIN or d.name == "0":
                    continue
                items.append({"group": group, "appid": d.name, "path": d.path, "installed": d.name in apps,
                              "name": apps.get(d.name, f"odinstalowana gra {d.name}")})
    tools: list = []
    for b in (f"{home}/.local/share/Steam/compatibilitytools.d", f"{home}/.steam/root/compatibilitytools.d",
              f"{home}/.var/app/com.valvesoftware.Steam/.local/share/Steam/compatibilitytools.d"):
        try:
            for d in os.scandir(b):
                if d.is_dir(follow_symlinks=False) and not d.is_symlink():
                    tools.append((d.stat().st_mtime, d.path))
        except OSError:
            continue
    tools = sorted({os.path.realpath(p): (m, p) for m, p in tools}.values(), reverse=True)
    for _m, p in tools[1:]:  # najnowsza wersja zostaje
        items.append({"group": "proton", "appid": "", "path": p, "installed": False, "name": os.path.basename(p)})
    return items


APP_ID_RE = re.compile(r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)+$")


def flatpak_app_dirs(home: str, conf_dir: str = "/etc/flatpak/installations.d") -> list:
    """Katalogi 'app' wszystkich instalacji Flatpaka (uzytkownik, system, dodatkowe z installations.d)."""
    bases = [f"{home}/.local/share/flatpak/app", "/var/lib/flatpak/app"]
    try:
        for n in sorted(os.listdir(conf_dir)):
            if n.endswith(".conf"):
                for m in re.finditer(r"^Path=(.+)$", Path(conf_dir, n).read_text(encoding="utf-8", errors="replace"), re.M):
                    bases.append(os.path.join(m.group(1).strip(), "app"))
    except OSError:
        pass
    return bases


def flatpak_orphans(home: str, bases=None, listed=()) -> list:
    """[(id_aplikacji, sciezka)] - ~/.var/app/<id> aplikacji, ktorej nie ma w zadnej instalacji Flatpaka.

    Ostroznie: gdy nie istnieje zaden katalog instalacji, nie wiemy, co jest zainstalowane - zwraca []. Aplikacje
    z `flatpak list` (argument `listed`) tez liczą się jako zainstalowane."""
    bases = flatpak_app_dirs(home) if bases is None else bases
    real = [b for b in bases if os.path.isdir(b)]
    if not real:
        return []
    installed = set(listed)
    for b in real:
        try:
            installed.update(os.listdir(b))
        except OSError:
            return []  # nie da sie odczytac instalacji = nie zgadujemy
    out: list = []
    try:
        for d in os.scandir(os.path.join(home, ".var", "app")):
            if d.is_dir(follow_symlinks=False) and APP_ID_RE.match(d.name) and d.name not in installed:
                out.append((d.name, d.path))
    except OSError:
        return []
    return sorted(out)


_UNITS = {"B": 1, "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12, "KIB": 1024, "MIB": 1024 ** 2, "GIB": 1024 ** 3, "TIB": 1024 ** 4}


def parse_size(text: str) -> int:
    """'1.5GB (66%)' -> bajty; 0 gdy nie da sie odczytac."""
    m = re.match(r"\s*([\d.]+)\s*([KMGT]?i?B)", text, re.I)
    if not m:
        return 0
    try:
        return int(float(m.group(1)) * _UNITS.get(m.group(2).upper(), 0))
    except ValueError:
        return 0


def podman_reclaimable(timeout: int = 15) -> int:
    """Ile zwolni `podman image prune` (nieuzywane obrazy); 0 gdy brak podmana lub nic do zwolnienia."""
    if not shutil.which("podman"):
        return 0
    try:
        r = subprocess.run(["podman", "system", "df", "--format", "{{.Type}}|{{.Reclaimable}}"],
                           capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return 0
    if r.returncode != 0:
        return 0
    for ln in r.stdout.splitlines():
        typ, _, rec = ln.partition("|")
        if typ.strip().lower().startswith("image"):
            return parse_size(rec)
    return 0
