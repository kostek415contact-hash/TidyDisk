"""Logika TidyDisk: skanowanie, usuwanie, operacje roota. Bez zalezności od Qt."""
from __future__ import annotations

import ntpath
import os
import re
import shlex
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import disks as disks_mod
from . import kb, kb_windows, osal, winfs
from . import rules, settings

HOME = Path.home()
ENV_C = dict(os.environ, LC_ALL="C")
JOURNAL_KEEP = 200 * 1024 * 1024
BIG_CACHE = 1024**3  # nierozpoznany cache wiekszy niz 1 GB wymaga decyzji czlowieka
PKG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:~-]*$")  # bez wiodacego "-": nazwa nie moze byc opcja dnf

# Katalogi uzytkownika, w ktorych program w ogole wolno cokolwiek kasowac.
ALLOWED_ROOTS = [
    HOME / ".cache",
    HOME / ".var" / "app",
    HOME / ".local" / "share" / "Trash",
]

HINTS = {
    "thumbnails": "Miniatury plików - odtworzą się same",
    "pip": "Cache pip - pakiety pobiorą się ponownie",
    "mozilla": "Cache Firefoksa",
    "google-chrome": "Cache Google Chrome",
    "chromium": "Cache Chromium",
    "mesa_shader_cache": "Cache shaderów - przebuduje się przy grach",
    "nvidia": "Cache shaderów NVIDIA",
    "huggingface": "Pobrane modele - duże, pobiorą się ponownie",
    "torch": "Pobrane modele PyTorch",
    "go-build": "Cache kompilacji Go",
    "yarn": "Cache Yarn",
}


# ----------------------------------------------------------------- model --

@dataclass
class Entry:
    label: str
    size: int
    kind: str  # path | contents | flatpak_user | root_sh | root_pkg
    paths: list = field(default_factory=list)
    cmd: str = ""
    pkgs: list = field(default_factory=list)
    note: str = ""
    checked: bool = False
    root: bool = False
    rating: str = "review"  # safe | review | keep | mine (patrz kb.py)
    what: str = ""  # co to jest
    why: str = ""  # dlaczego taka ocena
    warn: str = ""  # ostrzezenie (np. program dziala) - domyslnie nie zaznaczamy
    rule: str = ""  # reguła z bazy wiedzy (do raportu)
    suggested: bool = False  # co program zaproponowal (przed zmianami uzytkownika)
    disk: str = ""  # na ktorym dysku/partycji lezy (np. "nvme0n1 · btrfs „fedora”")

    user_pick: bool = False  # wybrane recznie w przegladarce plikow (takze 'Twoje pliki')
    trash: bool = False  # przenies do kosza zamiast usuwac na stale (tylko user_pick)
    score: int = 0  # pewnosc algorytmu 0-100 (tylko propozycje z analizy)
    touched: bool = False  # uzytkownik sam zmienil zaznaczenie - AI/algorytm go nie nadpisuje
    ai: str = ""  # werdykt modelu: usunac | zostawic | nie_wiem
    ai_risk: str = ""
    reasons: list = field(default_factory=list)

    @property
    def deletable(self) -> bool:
        """'Nie ruszaj' nigdy; 'Twoje pliki' tylko gdy uzytkownik sam je wybral."""
        if self.rating in (kb.SAFE, kb.REVIEW):
            return True
        return self.rating == kb.MINE and self.user_pick


@dataclass
class Protected:
    """Rzecz, ktorej program swiadomie nie rusza - z powodem."""
    label: str
    reason: str
    size: int = 0
    path: str = ""
    rating: str = "keep"


@dataclass
class Category:
    key: str  # cache | trash | flatpak | system | kernel | packages
    title: str
    desc: str
    root: bool
    entries: list
    protected: list = field(default_factory=list)  # list[Protected]


@dataclass
class CleanResult:
    freed: int = 0
    problems: int = 0
    trashed: int = 0  # bajty przeniesione do kosza (miejsce zwolni dopiero oproznienie kosza)


def fmt_size(n: int) -> str:
    if n <= 0:
        return "—"
    v = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unit == "TB":
            return f"{v:.0f} {unit}" if unit in ("B", "KB") else f"{v:.1f} {unit}"
        v /= 1024
    return "—"


def short(path) -> str:
    return str(path).replace(str(HOME), "~", 1)


def disk_info() -> dict:
    """{punkt_montowania: (zajete, calosc)} dla / i /home (bez duplikatow)."""
    out: dict = {}
    seen: list = []
    mounts = (Path.home().anchor or "C:\\",) if osal.is_windows() else ("/", "/home")
    for mount in mounts:
        try:
            u = shutil.disk_usage(mount)
        except OSError:
            continue
        # btrfs: subwolumeny wygladaja jak osobne dyski - pomijamy duplikaty
        if any(u.total == t and abs(u.free - f) < 256 * 1024 * 1024 for t, f in seen):
            continue
        seen.append((u.total, u.free))
        out[mount] = (u.total - u.free, u.total)
    return out


# ------------------------------------------------------------- filesystem --

def dir_size(path: str) -> int:
    """Rzeczywiste zajecie dysku (bloki), bez podazania za symlinkami."""
    total = 0
    seen: set = set()
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                        total += osal.alloc_size(st)
                    else:
                        if st.st_nlink > 1:
                            key = (st.st_dev, st.st_ino)
                            if key in seen:
                                continue
                            seen.add(key)
                        total += osal.alloc_size(st)
        except OSError:
            pass
    return total


def path_size(path: str) -> int:
    try:
        st = os.lstat(path)
    except OSError:
        return 0
    if os.path.isdir(path) and not os.path.islink(path):
        return dir_size(path) + osal.alloc_size(st)
    return osal.alloc_size(st)


def bad_path(path: str) -> bool:
    """Sciezka niebezpieczna z zasady: nie bezwzgledna albo konczaca sie na '.' / '..' (rozwiazalaby sie gdzie indziej)."""
    return (not isinstance(path, str) or not os.path.isabs(path)
            or os.path.basename(path.rstrip("/")) in ("", ".", ".."))


def is_protected(path: str) -> bool:
    """Chronione przez uzytkownika (Ustawienia -> Ochrona): ani sama sciezka, ani folder ja zawierajacy nie moga zostac usuniete."""
    prot = settings.RUNTIME["protected"]
    return bool(prot) and (settings.touches(path, prot) or settings.touches(os.path.realpath(path), prot))


STEAM_TARGET_RE = re.compile(r"/steamapps/(shadercache|compatdata)/\d+$|/compatibilitytools\.d/[^/]+$")


def is_safe_target(path: str) -> bool:
    """Czy rodzic sciezki lezy w jednym z dozwolonych katalogow (albo to katalog gry/Protona w bibliotece Steama)."""
    if bad_path(path) or is_protected(path):
        return False
    if STEAM_TARGET_RE.search(path) and not os.path.islink(path) and os.path.isdir(path):
        return True
    parent = Path(os.path.realpath(os.path.dirname(os.path.abspath(path))))
    for root_real in map(Path, _allowed_roots_real()):
        if parent == root_real or root_real in parent.parents:
            return True
    return False


def _allowed_roots_real() -> list:
    """Rozwiazane korzenie, w ktorych wolno kasowac. Korzen, ktory (np. przez symlink ~/.cache -> ~) wskazuje na caly
    katalog domowy, jego przodka albo "/", jest pomijany - inaczej 'dozwolony katalog' obejmowalby wszystko."""
    home = Path(os.path.realpath(str(HOME)))
    out = []
    for root in ALLOWED_ROOTS:
        r = Path(os.path.realpath(root))
        if r == home or r in home.parents or str(r) == os.sep:
            continue
        out.append(str(r))
    return out


def _rm_fd(fd: int, path: str, dev: int, errors: list) -> None:
    """Czysci katalog otwarty jako deskryptor: bez podazania za symlinkami (takze podmienionymi w trakcie)
    i bez wchodzenia w inne systemy plikow (punkty montowania), jak `rm -r --one-file-system`."""
    try:
        os.fchmod(fd, 0o700)
    except OSError:
        pass
    try:
        names = os.listdir(fd)
    except OSError as ex:
        errors.append(f"{path}: {ex.strerror}")
        return
    for name in names:
        full = os.path.join(path, name)
        try:
            st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(st.st_mode):
                if st.st_dev != dev:
                    errors.append(f"{full}: pominięto (inny system plików / punkt montowania)")
                    continue
                sub = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    _rm_fd(sub, full, dev, errors)
                finally:
                    os.close(sub)
                os.rmdir(name, dir_fd=fd)
            else:
                os.unlink(name, dir_fd=fd)
        except OSError as ex:
            errors.append(f"{full}: {ex.strerror}")
        except RecursionError:
            errors.append(f"{full}: pominięto (zbyt głęboko zagnieżdżony katalog)")


def _open_dir_nofollow(path: str) -> int:
    """Otwiera katalog o JUZ ROZWIAZANEJ sciezce (realpath), krok po kroku z O_NOFOLLOW od korzenia: jesli ktorykolwiek
    skladnik zostal w miedzyczasie podmieniony na symlink, otwarcie sie nie uda (zamiast skasowac cos poza celem)."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.split("/"):
            if not part:
                continue
            nfd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nfd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _allowed_parent(parent_real: str) -> bool:
    """Czy juz rozwiazany (bez symlinkow) katalog lezy w dozwolonym korzeniu; czyste porownanie napisow, bez dotykania dysku."""
    for r in _allowed_roots_real():
        r = r.rstrip("/")
        if parent_real == r or parent_real.startswith(r + "/"):
            return True
    return False


def rm_tree(path: str, errors: list) -> None:
    if osal.is_windows():
        _win_remove(path, errors, False)
        return
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as ex:
        errors.append(f"{path}: {ex.strerror}")
        return
    try:
        _rm_fd(fd, path, os.fstat(fd).st_dev, errors)
    finally:
        os.close(fd)
    try:
        os.rmdir(path)
    except OSError as ex:
        errors.append(f"{path}: {ex.strerror}")


def is_user_target(path: str) -> tuple:
    """Czy wolno usunac plik wybrany recznie: (ok, powod_odmowy).

    Tylko w katalogu domowym i na dyskach danych, nigdy cale katalogi glowne i nigdy
    miejsca ocenione jako 'nie ruszaj' (ustawienia, klucze, system)."""
    if osal.is_windows():
        return win_check(path, user=True)
    if bad_path(path):
        return False, "nieprawidłowa ścieżka"
    path = os.path.normpath(path)  # bez koncowego '/', '//' i './': inaczej "~/.ssh/" omijalo ochrone "~/.ssh"
    if is_protected(path):
        return False, "chronione w Ustawieniach"
    real = os.path.realpath(os.path.dirname(os.path.abspath(path)))
    full = os.path.join(real, os.path.basename(path))
    roots = [os.path.realpath(str(HOME))] + [os.path.realpath(m) for m in KB.data_mounts]
    if full in roots:
        return False, "to cały katalog domowy lub dysk"
    if not any(full.startswith(r.rstrip("/") + "/") for r in roots):
        return False, "poza katalogiem domowym i dyskami danych"
    v = KB.classify(full)
    if v.rating == kb.KEEP:
        return False, f"chronione ({v.title})"
    return True, ""


def trash_path(path: str, errors: list) -> None:
    """Przenosi do kosza (mozna przywrocic) przez `gio trash`."""
    if os.path.isdir(path) and not os.path.islink(path):
        kept = holds_keep(path)
        if kept:
            errors.append(f"pominięto (w środku jest {kept} - nie ruszam): {path}")
            return
    if osal.is_windows():
        ok, why = win_check(path, user=True)
        if not ok:
            errors.append(f"pominięto ({why}): {path}")
        else:
            winfs.recycle(ntpath.normpath(path), errors)
        return
    path = os.path.normpath(path)
    if not shutil.which("gio"):
        errors.append(f"{path}: brak polecenia gio - nie mogę przenieść do kosza")
        return
    code, _out = run_text(["gio", "trash", "--", path], 120)
    if code != 0:
        errors.append(f"{path}: gio trash zakończył z kodem {code}")


def dedupe_selection(entries: list) -> list:
    """Usuwa duplikaty: ta sama sciezka lub plik wewnatrz tez zaznaczonego folderu."""
    out = []
    exact: set = set()  # przyjete sciezki
    norm: set = set()  # to samo bez koncowego '/': kandydaci na przodka
    win = osal.is_windows()
    for e in sorted(entries, key=lambda x: len(x.paths[0]) if (x.kind == "path" and x.paths) else 0):
        if e.kind == "path" and e.paths:
            p = e.paths[0]
            if p in exact:
                continue
            q = p.replace("\\", "/").lower() if win else p
            k, covered = q.find("/"), False
            while k >= 0:  # przodkowie p to prefiksy p[:k] konczace sie tuz przed '/'
                if q[:k] in norm:
                    covered = True
                    break
                k = q.find("/", k + 1)
            if covered:
                continue
            exact.add(p)
            norm.add(q.rstrip("/"))
        out.append(e)
    return out


def cleanup_roots() -> list:
    """Miejsca do pelnego przegladu/sprzatania: [(sciezka, opis_dysku)] - dom i dyski danych."""
    mounts = read_mounts()
    labels = disks_mod.mount_labels()
    home = str(HOME)
    roots = [(home, labels.get(mount_of(home, mounts), ""))]
    for m in data_mounts(mounts):
        roots.append((m, labels.get(m, m)))
    return roots


def file_entry(item: "FolderItem", disk: str) -> Entry:
    """Pozycja sprzatania dla pliku/folderu z przegladarki."""
    v = item.verdict
    return Entry(
        label=item.name, size=max(item.size, 0), kind="path", paths=[item.path],
        note=short(item.path), rating=v.rating, what=f"{v.title} - {v.what}", why=v.why, rule=v.rule,
        disk=disk, user_pick=True, trash=True,
        checked=False, suggested=False,  # z przegladarki nic nie zaznaczamy samodzielnie
    )


def ai_only() -> bool:
    return settings.RUNTIME.get("search_mode") == "ai_only"


def score_label(score: int) -> str:
    """W trybie 'tylko AI' nie ma pewnosci algorytmu: 80/55 to tylko zapis ryzyka podanego przez model."""
    return "ryzyko niskie" if score >= 80 else "ryzyko średnie"


def confidence_text(score: int) -> str:
    return f"Ocena AI ({score_label(score)})" if ai_only() else f"Pewność {score}%"


ADVICE_AUTO = 75  # od tej pewnosci zaznaczamy sami (nie dotyczy 'Twoich plikow')


def advice_entry(a: list, disk: str = "") -> "Entry | None":
    """Pozycja sprzatania z propozycji algorytmu [wynik, sciezka, rozmiar, mtime, ocena, tytul, powody, rodzaj]."""
    score, path, size, rating, title, reasons = a[0], a[1], a[2], a[4], a[5], a[6]
    if rating == kb.KEEP or not (is_user_target(path)[0] or is_safe_target(path)):
        return None
    if not rules.allowed(path, reasons, rating, "dir" if (len(a) > 7 and a[7] == "dir") else "file", settings.RUNTIME["rules_off"]):
        return None  # wylaczone w Ustawienia -> Reguly
    why = f"{confidence_text(int(score))}: " + "; ".join(reasons)
    return Entry(
        label=os.path.basename(path.rstrip("/")) or path, size=max(int(size), 0), kind="path",
        paths=[path], note=short(path), rating=rating, what=title, why=why, rule="analiza",
        disk=disk, user_pick=True, trash=True, score=int(score), reasons=list(reasons),
        checked=score >= ADVICE_AUTO and rating != kb.MINE, suggested=score >= ADVICE_AUTO and rating != kb.MINE,
    )


KEEP_NAMES = {".git", ".ssh", ".gnupg"}


def holds_keep(path: str, depth: int = 8, budget: int = 100000) -> str:
    """Nazwa chronionego elementu w srodku folderu (.git/.ssh/.gnupg albo cokolwiek, co baza wiedzy ocenia jako 'Nie ruszaj')
    albo ''. Gdy folder jest zbyt duzy/glebokii, zeby go przejrzec, zwraca komunikat odmowy (bezpiecznie: 'nie wiem' = nie usuwamy)."""
    todo, seen = [(path, 0)], 0
    win = osal.is_windows()
    while todo:
        if seen >= budget:
            return "zbyt dużo elementów, żeby sprawdzić, czy nic chronionego nie ma w środku"
        p, d = todo.pop()
        try:
            with os.scandir(p) as it:
                for e in it:
                    seen += 1
                    if e.name.lower() in KEEP_NAMES:
                        return e.name
                    if e.is_dir(follow_symlinks=False):
                        if d >= depth:
                            return "zbyt głęboko zagnieżdżone foldery, żeby sprawdzić, czy nic chronionego nie ma w środku"
                        v = KB.classify(e.path)
                        if v.rating == kb.KEEP:
                            return v.title
                        todo.append((e.path, d + 1))
        except OSError:
            continue
    return ""


def win_check(path: str, user: bool = False) -> tuple:
    """Kontrola celu usuwania na Windows: (ok, powod_odmowy). Dziala na napisach i realpath, bez dir_fd (ktorego Windows nie ma)."""
    if winfs.bad_path(path):
        return False, "nieprawidłowa ścieżka"
    path = ntpath.normpath(path)
    if is_protected(path):
        return False, "chronione w Ustawieniach"
    if winfs.is_drive_root(path) or kb_windows.norm(path) == KB.home:
        return False, "to cały dysk lub katalog domowy"
    if not winfs.same_real(path):
        return False, "ścieżka prowadzi przez dowiązanie lub junction"
    v = KB.classify(path)
    if v.rating == kb.KEEP:
        return False, f"chronione ({v.title})"
    n = kb_windows.norm(path)
    if not (n.startswith(KB.home + "/") or any(n.startswith(m + "/") for m in KB.data_mounts)):
        return False, "poza katalogiem domowym i dyskami danych"
    if not user and v.rating not in (kb.SAFE, kb.REVIEW):
        return False, "nie jest oznaczone jako zbędne"
    return True, ""


def _win_remove(path: str, errors: list, user: bool) -> None:
    ok, why = win_check(path, user)
    if not ok:
        errors.append(f"pominięto ({why}): {path}")
        return
    path = ntpath.normpath(path)
    if user and os.path.isdir(path):
        kept = holds_keep(path)
        if kept:
            errors.append(f"pominięto (w środku jest {kept} - nie ruszam): {path}")
            return
    winfs.remove_item(path, errors)


def remove_path(path: str, errors: list, user: bool = False) -> None:
    if osal.is_windows():
        _win_remove(path, errors, user)
        return
    if bad_path(path):
        errors.append(f"pominięto (nieprawidłowa ścieżka): {path}")
        return
    path = os.path.normpath(path)
    if is_protected(path):
        errors.append(f"pominięto (chronione w Ustawieniach): {path}")
        return
    if not user and not is_safe_target(path):
        errors.append(f"pominięto (poza dozwolonymi katalogami): {path}")
        return
    # Od tej chwili dzialamy na JEDNEJ, raz rozwiazanej sciezce rodzica i kasujemy wzgledem jego deskryptora (dir_fd):
    # podmiana skladnika na symlink po sprawdzeniu konczy sie bledem, a nie skasowaniem czegos poza celem.
    real_parent = os.path.realpath(os.path.dirname(os.path.abspath(path)))
    name = os.path.basename(path)
    target = os.path.join(real_parent, name)
    if not user and not (_allowed_parent(real_parent) or (STEAM_TARGET_RE.search(target) and os.path.isdir(target))):
        errors.append(f"pominięto (poza dozwolonymi katalogami): {path}")
        return
    if user:
        if os.path.isdir(target) and not os.path.islink(target):
            kept = holds_keep(target)
            if kept:
                errors.append(f"pominięto (w środku jest {kept} - nie ruszam): {path}")
                return
        ok, why = is_user_target(target)  # ponowna kontrola na rozwiazanej sciezce
        if not ok:
            errors.append(f"pominięto ({why}): {path}")
            return
    try:
        pfd = _open_dir_nofollow(real_parent)
    except FileNotFoundError:
        return
    except OSError as ex:
        errors.append(f"{path}: {ex.strerror} (katalog nadrzędny zmienił się w trakcie - pominięto)")
        return
    try:
        try:
            st = os.stat(name, dir_fd=pfd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if stat.S_ISDIR(st.st_mode):
            if st.st_dev != os.fstat(pfd).st_dev:
                errors.append(f"{path}: pominięto (punkt montowania / inny system plików)")
                return
            sub = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=pfd)
            try:
                _rm_fd(sub, target, st.st_dev, errors)
            finally:
                os.close(sub)
            os.rmdir(name, dir_fd=pfd)
        else:
            os.unlink(name, dir_fd=pfd)
    except FileNotFoundError:
        pass
    except OSError as ex:
        errors.append(f"{path}: {ex.strerror}")
    finally:
        os.close(pfd)


_EXPLORER_CACHE = re.compile(r"^(thumbcache|iconcache)_.*\.db$", re.IGNORECASE)


def remove_contents(directory: str, errors: list) -> None:
    try:
        with os.scandir(directory) as it:
            children = [c.path for c in it]
    except FileNotFoundError:
        return
    except OSError as ex:
        errors.append(f"{directory}: {ex.strerror}")
        return
    if osal.is_windows() and kb_windows.norm(directory).endswith("/microsoft/windows/explorer"):
        children = [c for c in children if _EXPLORER_CACHE.match(os.path.basename(c))]  # tylko pliki cache, nie caly folder
    for c in children:
        remove_path(c, errors)


# ------------------------------------------------------------------ scan --

@dataclass
class FolderItem:
    name: str
    path: str
    is_dir: bool
    size: int  # -1 = nieznany
    exact: bool
    mtime: int
    verdict: object  # kb.Verdict


def dir_size_budget(path: str, seconds: float) -> tuple:
    """Rozmiar katalogu z limitem czasu: (rozmiar, czy_policzony_w_calosci)."""
    import time
    deadline = time.monotonic() + seconds
    total, stack, n = 0, [path], 0
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    n += 1
                    if n % 500 == 0 and time.monotonic() > deadline:
                        return total, False
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    total += osal.alloc_size(st)
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
            if time.monotonic() > deadline:
                return total, False
        except OSError:
            pass
    return total, True


def list_folder(path: str, sizes: dict | None = None, limit: int = 3000, budget: float = 1.2):
    """Zawartosc folderu na zywo: WSZYSTKIE pliki i podkatalogi z ocena.

    sizes - znane rozmiary katalogow (ze skanu). Pozostale liczymy w limicie czasu `budget`.
    Zwraca (lista_FolderItem, liczba_pominietych_ponad_limit, blad_lub_pusty_tekst).
    """
    sizes = sizes or {}
    parent_v = KB.classify(path)
    items: list = []
    try:
        entries = list(os.scandir(path))
    except OSError as ex:
        return [], 0, ex.strerror or str(ex)
    for e in entries:
        try:
            st = e.stat(follow_symlinks=False)
            is_dir = e.is_dir(follow_symlinks=False)
        except OSError:
            continue
        if is_dir:
            v = KB.classify_dir(e.path, parent_v)
            known = sizes.get(e.path)
            items.append(FolderItem(e.name, e.path, True, known if known is not None else -1,
                                    known is not None, int(st.st_mtime), v))
        else:
            v = KB.classify_file(e.path, parent_v)
            items.append(FolderItem(e.name, e.path, False, osal.alloc_size(st), True, int(st.st_mtime), v))
    unknown = [i for i in items if i.is_dir and i.size < 0]
    for it in unknown:  # bez skanu: policz w limicie czasu (kazdy katalog po rowno)
        part = budget / max(len(unknown), 1)
        it.size, it.exact = dir_size_budget(it.path, part)
    items.sort(key=lambda i: (-i.size, i.name.lower()))
    extra = max(len(items) - limit, 0)
    return items[:limit], extra, ""


def run_text(cmd: list, timeout: int = 60) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=ENV_C
        )
        return r.returncode, r.stdout
    except Exception:
        return -1, ""


def journal_usage() -> int:
    _, out = run_text(["journalctl", "--disk-usage"], 20)
    m = re.search(r"take up\s+([\d.]+)\s*([KMGT]?)", out)
    if not m:
        return 0
    mult = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}[m.group(2)]
    return int(float(m.group(1)) * mult)


def rotated_logs_size() -> int:
    total = 0
    pat = re.compile(r".*\.(gz|xz|zst|bz2|old|\d)$")
    for dirpath, _dirs, files in os.walk("/var/log", onerror=lambda e: None):
        if dirpath.startswith("/var/log/journal"):
            continue
        for f in files:
            if pat.match(f):
                try:
                    total += osal.alloc_size(os.lstat(os.path.join(dirpath, f)))
                except OSError:
                    pass
    return total


def flatpak_unused(scope: str) -> list:
    _, out = run_text(
        ["flatpak", "uninstall", "--unused", f"--{scope}", "--assumeno"], 40
    )
    names: list = []
    for line in out.splitlines():
        m = re.match(r"^\s*\d+\.\s+(?:\[\S+\]\s+)?([A-Za-z0-9_.\-]+)", line)
        if m and m.group(1) not in names:
            names.append(m.group(1))
    return names


def rpm_sizes() -> dict:
    _, out = run_text(["rpm", "-qa", "--qf", "%{NAME}-%{EVR}.%{ARCH} %{SIZE}\\n"], 60)
    sizes: dict = {}
    for line in out.splitlines():
        try:
            key, val = line.rsplit(" ", 1)
            sizes[re.sub(r"-0:(?=\d)", "-", key)] = int(val)
        except ValueError:
            continue
    return sizes


# nazwa katalogu w ~/.cache  ->  mozliwe nazwy procesow
PROC_MAP = {
    "mozilla": ["firefox"],
    "google-chrome": ["chrome"],
    "chromium": ["chromium"],
    "BraveSoftware": ["brave"],
    "thunderbird": ["thunderbird"],
    "JetBrains": ["idea", "pycharm", "clion", "webstorm", "goland"],
    "code": ["code"],
    "baloo": ["baloo_file"],
}


def running_names() -> set:
    """Nazwy (comm, male litery) dzialajacych procesow uzytkownika."""
    names: set = set()
    if osal.is_windows():
        try:
            r = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, errors="replace", timeout=20, **osal.nowindow())
            for ln in r.stdout.splitlines():
                nm = ln.split('","')[0].strip('"').lower()
                if nm:
                    names.add(nm[:-4] if nm.endswith(".exe") else nm)
        except (OSError, subprocess.SubprocessError):
            pass
        return names
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    if not f.read(1):  # watek jadra - nie jest programem uzytkownika
                        continue
                with open(f"/proc/{pid}/comm", encoding="utf-8", errors="replace") as f:
                    names.add(f.read().strip().lower())
            except OSError:
                continue
    except OSError:
        pass
    return names


def running_warn(name: str, running: set) -> str:
    """Tekst ostrzezenia, jesli program zwiazany z katalogiem cache dziala."""
    cands = [c.lower() for c in PROC_MAP.get(name, [])] + [name.lower()]
    hit = [c for c in cands if c in running]
    if hit:
        return f"Program działa ({hit[0]}) - zamknij go przed czyszczeniem"
    return ""


def running_flatpaks() -> set:
    if not shutil.which("flatpak"):
        return set()
    _, out = run_text(["flatpak", "ps", "--columns=application"], 10)
    return {ln.strip() for ln in out.splitlines() if "." in ln}


def repoquery(args: list) -> list:
    code, out = run_text(["dnf", "repoquery", "-q", *args], 120)
    if code != 0:
        return []
    return [ln.strip() for ln in out.splitlines() if PKG_RE.match(ln.strip())]


DATA_FS = {"ext4", "ext3", "ext2", "xfs", "btrfs", "f2fs", "ntfs", "ntfs3", "fuseblk", "exfat", "vfat"}


def read_mounts(path: str = "/proc/self/mounts") -> list:
    """[(punkt_montowania, system_plikow)]"""
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for ln in f:
                p = ln.split()
                if len(p) >= 3:
                    out.append((p[1].replace("\\040", " "), p[2]))
    except OSError:
        pass
    return out


def data_mounts(mounts=None) -> list:
    """Dodatkowe dyski z danymi (w /mnt, /media, /run/media) - ich zawartosc to 'Twoje pliki'."""
    out = []
    for mp, fs in (mounts if mounts is not None else read_mounts()):
        if fs in DATA_FS and mp.startswith(("/mnt/", "/media/", "/run/media/")):
            out.append(mp)
    return sorted(set(out))


def mount_of(path: str, mounts=None) -> str:
    """Punkt montowania, na ktorym lezy sciezka (najdluzszy pasujacy prefiks)."""
    if osal.is_windows():  # na Windows 'punktem montowania' jest litera dysku: "C:\\" (tak samo jak w disks.list_disks_windows)
        drive = ntpath.splitdrive(path)[0]
        return drive.upper() + "\\" if drive else "/"
    best = "/"
    for mp, _fs in (mounts if mounts is not None else read_mounts()):
        if (path == mp or path.startswith(mp.rstrip("/") + "/")) and len(mp) > len(best):
            best = mp
    return best


KB = kb.KnowledgeBase(HOME, data_mounts(), system=osal.SYSTEM)


def _rate(e: Entry, path: str) -> Entry:
    """Nadaje wpisowi ocene z bazy wiedzy dla podanej sciezki."""
    v = KB.classify(path)
    e.rating, e.rule, e.why = v.rating, v.rule, v.why
    e.what = f"{v.title} - {v.what}" if v.title else v.what
    if v.rule in ("~/.cache/*", "~/.var/app/*/cache") and e.size >= BIG_CACHE and v.rating == kb.SAFE:
        e.rating = kb.REVIEW
        e.why = (f"Duży cache programu, którego nie rozpoznaję (ponad {fmt_size(BIG_CACHE)}). "
                 "Zwykle da się go odtworzyć, ale może to być np. pobrane modele lub dane - "
                 "sprawdź, czym jest, zanim zaznaczysz.")
    return e


def _rate_fixed(e: Entry, rating: str, what: str, why: str, rule: str = "") -> Entry:
    e.rating, e.what, e.why, e.rule = rating, what, why, rule or "(zdefiniowane w programie)"
    return e


def _kernel_ver(nevra: str) -> str:
    m = re.match(r"^.+?-(\d.*)$", nevra)
    return re.sub(r"^\d+:", "", m.group(1)) if m else nevra


def games_entries(running) -> list:
    from . import extras
    out: list = []
    steam_run = running_warn("steam", running)
    for it in extras.steam_items(str(HOME)):
        size = path_size(it["path"])
        if size <= 0:
            continue
        g, name = it["group"], it["name"]
        if g == "shadercache":
            e = Entry(f"Shadery Steam: {name}", size, "path", paths=[it["path"]], note=short(it["path"]))
            _rate_fixed(e, kb.SAFE if not it["installed"] else kb.REVIEW, "Skompilowane shadery gry - Steam zbuduje je od nowa (chwilowe przycięcia przy pierwszym uruchomieniu).",
                        "Gra jest odinstalowana, więc shadery są zbędne." if not it["installed"] else "Gra jest zainstalowana - po usunięciu przebuduje shadery przy starcie.", "steam/shadercache")
            e.checked = not it["installed"] and not steam_run
        elif g == "compatdata":
            if it["installed"]:
                continue  # prefiks zainstalowanej gry to jej zapisy i ustawienia
            e = Entry(f"Prefiks Proton: {name}", size, "path", paths=[it["path"]], note=short(it["path"]))
            _rate_fixed(e, kb.REVIEW, "Prefiks Wine/Proton odinstalowanej gry.",
                        "Gra nie jest już zainstalowana, ale prefiks może zawierać zapisy gry - sprawdź przed usunięciem.", "steam/compatdata")
            e.warn = "może zawierać zapisy gier (np. w Documents/My Games)"
        else:
            e = Entry(f"Stary Proton: {name}", size, "path", paths=[it["path"]], note=short(it["path"]))
            _rate_fixed(e, kb.REVIEW, "Starsza wersja Proton (GE) obok nowszej.",
                        "Gry mogą mieć ją wybraną ręcznie - usuń, jeśli nie jest potrzebna.", "steam/proton")
        e.warn = e.warn or steam_run
        out.append(e)
    reclaim = extras.podman_reclaimable()
    if reclaim > 0:
        e = Entry("Nieużywane obrazy Podmana", reclaim, "podman_prune", note="podman image prune")
        _rate_fixed(e, kb.REVIEW, "Obrazy kontenerów, których nie używa żaden kontener.",
                    "Wykona `podman image prune -f` (tylko nieoznaczone obrazy bez kontenerów; wolumeny z danymi zostają).", "podman")
        out.append(e)
    return sorted(out, key=lambda x: -x.size)


def scan(status=lambda _msg: None) -> list:
    if osal.is_windows():
        from . import scan_windows
        cats = scan_windows.scan(status=status)
        try:
            labels = disks_mod.mount_labels()
        except Exception:  # lista dyskow jest dodatkiem: bez niej pozycje zostaja bez opisu dysku
            labels = {}
        for cat in cats:
            for e in cat.entries:
                if not e.disk:
                    mp = mount_of(e.paths[0] if e.paths else str(HOME))
                    e.disk = labels.get(mp, mp)
        return cats
    cats: list = []
    running = running_names()

    # --- cache uzytkownika
    status("Skanuję ~/.cache …")
    entries = []
    try:
        for e in os.scandir(HOME / ".cache"):
            size = path_size(e.path)
            if size <= 0:
                continue
            ent = _rate(
                Entry(label=e.name, size=size, kind="path", paths=[e.path], note=short(e.path)),
                e.path,
            )
            ent.warn = running_warn(e.name, running)
            ent.checked = ent.rating == kb.SAFE and not ent.warn
            entries.append(ent)
    except OSError:
        pass
    cats.append(
        Category(
            "cache",
            "Cache aplikacji",
            "Dane tymczasowe programów, odtwarzają się same. Programy, które teraz "
            "działają, są oznaczone i nie są zaznaczane.",
            False,
            entries,
        )
    )

    # --- gry (Steam) i kontenery (Podman)
    status("Skanuję gry i kontenery …")
    games = games_entries(running)
    if games:
        cats.append(Category(
            "games", "Gry i kontenery",
            "Cache shaderów Steam, osierocone prefiksy Proton, stare wersje Proton i nieużywane obrazy Podmana. "
            "Prefiksy (compatdata) mogą zawierać zapisy gier - nigdy nie są zaznaczane same.", False, games))

    # --- kosz
    status("Skanuję kosz …")
    trash = HOME / ".local" / "share" / "Trash"
    tpaths = [str(trash / "files"), str(trash / "info")]
    tsize = sum(path_size(p) for p in tpaths)
    tent = []
    if tsize > 0:
        te = _rate(Entry("Opróżnij kosz", tsize, "contents", tpaths, note=short(trash)), str(trash))
        te.why = "Usunięcie jest nieodwracalne - dlatego nie zaznaczam tego sam. Sprawdź kosz."
        tent.append(te)
    cats.append(Category("trash", "Kosz", "Pliki przeniesione do kosza.", False, tent))

    # --- flatpak
    status("Skanuję Flatpak …")
    fentries = []
    frun = running_flatpaks()
    try:
        for e in os.scandir(HOME / ".var" / "app"):
            cdir = os.path.join(e.path, "cache")
            size = path_size(cdir)
            if size > 0:
                ent = _rate(
                    Entry(f"Cache: {e.name}", size, "contents", [cdir], note=short(cdir)), cdir
                )
                if e.name in frun:
                    ent.warn = "Aplikacja działa - zamknij ją przed czyszczeniem"
                ent.checked = ent.rating == kb.SAFE and not ent.warn
                fentries.append(ent)
    except OSError:
        pass
    if shutil.which("flatpak"):
        from . import extras
        _, listed = run_text(["flatpak", "list", "--app", "--columns=application"], 30)
        for oid, opath in extras.flatpak_orphans(str(HOME), listed=listed.split()):
            osize = path_size(opath)
            if osize > 0:
                oe = Entry(f"Dane odinstalowanej aplikacji: {oid}", osize, "path", [opath], note=short(opath))
                _rate_fixed(oe, kb.REVIEW, "Dane aplikacji Flatpak, której nie ma już w systemie.",
                            "Aplikacji nie widać w żadnej instalacji Flatpaka, ale jej katalog w ~/.var/app został. "
                            "Mogą tam być Twoje zapisy i profile - nie zaznaczam tego sam.", "flatpak/orphan")
                oe.warn = "może zawierać Twoje zapisy i profile - sprawdź przed usunięciem"
                fentries.append(oe)
        why = ("Flatpak sam uznał, że żadna aplikacja ich nie używa. Pobiorą się ponownie, "
               "gdy będą potrzebne - dlatego nie zaznaczam tego sam.")
        names = flatpak_unused("user")
        if names:
            fentries.append(_rate_fixed(
                Entry(f"Nieużywane runtime'y (użytkownik): {len(names)}", 0, "flatpak_user",
                      note=", ".join(names)),
                kb.REVIEW, "Runtime'y Flatpak - biblioteki dla aplikacji, których już nie ma.", why))
        names = flatpak_unused("system")
        if names:
            fentries.append(_rate_fixed(
                Entry(f"Nieużywane runtime'y (system): {len(names)}", 0, "root_sh",
                      cmd="flatpak uninstall --unused --system -y --noninteractive",
                      note=", ".join(names), root=True),
                kb.REVIEW, "Runtime'y Flatpak - biblioteki dla aplikacji, których już nie ma.", why))
    cats.append(
        Category(
            "flatpak",
            "Flatpak",
            "Cache aplikacji Flatpak i runtime'y, których żadna aplikacja już nie używa.",
            False,
            fentries,
            protected=[Protected(
                "Dane i ustawienia aplikacji Flatpak (~/.var/app/*/data, config)",
                "To Twoje zapisy, profile i ustawienia - program ich nie usuwa.",
                path="~/.var/app")],
        )
    )

    # --- system
    status("Skanuję pliki systemowe …")
    sysent = []
    if shutil.which("dnf"):
        dsize = sum(
            path_size(p)
            for p in ("/var/cache/libdnf5", "/var/cache/dnf", "/var/cache/PackageKit")
            if os.path.exists(p)
        )
        sysent.append(_rate(Entry(
            "Cache DNF", dsize, "root_sh", cmd="dnf clean all",
            note="Pobrane metadane pakietów (/var/cache/libdnf5)", checked=True, root=True),
            "/var/cache/libdnf5"))
    if shutil.which("apt-get"):  # Debian, Ubuntu, Mint: pobrane paczki .deb
        asize = sum(path_size(p) for p in ("/var/cache/apt/archives",) if os.path.exists(p))
        sysent.append(_rate(Entry(
            "Cache APT", asize, "root_sh", cmd="apt-get clean",
            note="Pobrane pakiety .deb (/var/cache/apt/archives)", checked=True, root=True),
            "/var/cache/apt"))
    jt = journal_usage()
    if jt > JOURNAL_KEEP:
        sysent.append(_rate(Entry(
            f"Dziennik systemd - przytnij do 200 MB (jest {fmt_size(jt)})",
            jt - JOURNAL_KEEP, "root_sh", cmd="journalctl --vacuum-size=200M",
            note="Usuwa najstarsze wpisy dziennika", root=True),
            "/var/log/journal"))
        sysent[-1].why = ("Przycinam do 200 MB najnowszych wpisów. Tracisz starą historię "
                          "diagnostyczną, więc nie zaznaczam tego sam.")
    cd = "/var/lib/systemd/coredump"
    if os.path.isdir(cd):
        csize = path_size(cd)
        if csize > 0 or not os.access(cd, os.R_OK | os.X_OK):
            sysent.append(_rate(Entry(
                "Zrzuty pamięci po awariach (coredump)", csize, "root_sh",
                cmd=f"find {cd} -type f -delete", note=cd, checked=True, root=True), cd))
    lsize = rotated_logs_size()
    if lsize > 0:
        sysent.append(_rate_fixed(Entry(
            "Stare, zarchiwizowane logi w /var/log", lsize, "root_sh",
            cmd=("find /var/log -xdev -path /var/log/journal -prune -o -type f "
                 r"\( -name '*.gz' -o -name '*.xz' -o -name '*.zst' -o -name '*.bz2' "
                 r"-o -name '*.old' -o -name '*.[0-9]' \) -print -delete"),
            note="Pliki *.gz, *.xz, *.old, *.1 …", checked=True, root=True),
            kb.SAFE, "Zarchiwizowane logi - stare kopie dzienników usług.",
            "Rotacja logów już je zastąpiła nowymi; aktualnych logów nie dotykam.",
            "/var/log/*.gz|xz|zst|bz2|old|N"))
    cats.append(
        Category(
            "system", "System",
            "Wykonywane jako administrator - jedno okienko z hasłem na całość.",
            True, sysent,
            protected=[Protected("Aktualne logi, /etc, /usr, /boot, /var/lib",
                                 "Należą do systemu - program ich nigdy nie rusza.", path="/")],
        )
    )

    # --- jadra i pakiety
    if shutil.which("dnf"):
        status("Szukam starych jąder …")
        sizes = rpm_sizes()
        running_k = osal.kernel_release()
        groups: dict = {}
        for nevra in repoquery(["--installed", "--installonly", "--latest-limit=-2"]):
            if running_k in nevra:
                continue
            groups.setdefault(_kernel_ver(nevra), []).append(nevra)
        kent = []
        for ver, pk in groups.items():
            ent = Entry(
                f"Jądro {ver}",
                sum(sizes.get(re.sub(r"-0:(?=\d)", "-", p), 0) for p in pk),
                "root_pkg", pkgs=pk, note="Usuwa: " + ", ".join(pk), root=True)
            kent.append(_rate_fixed(
                ent, kb.REVIEW, "Stare jądro Linuksa wraz z modułami.",
                "Zostają dwa najnowsze i to, na którym działasz - to starsze nie jest już "
                "potrzebne. Nie zaznaczam sam, bo to usuwanie pakietów.", "(jądra: poza 2 najnowszymi)"))
        kprot = [Protected(f"Jądro {running_k}", "Działa teraz - usunięcie zepsułoby system.",
                           rating=kb.KEEP)]
        newest: dict = {}
        for nevra in repoquery(["--installed", "--installonly", "--latest-limit=2"]):
            if running_k in nevra:
                continue
            ver = _kernel_ver(nevra)
            newest[ver] = newest.get(ver, 0) + sizes.get(re.sub(r"-0:(?=\d)", "-", nevra), 0)
        for ver, size in newest.items():
            kprot.append(Protected(f"Jądro {ver}", "Jedno z dwóch najnowszych - zapas na wypadek problemów.",
                                   size, rating=kb.KEEP))
        cats.append(Category("kernel", "Stare jądra",
                             "Zostają dwa najnowsze i to, na którym działasz.", True, kent,
                             protected=kprot))

        status("Szukam niepotrzebnych pakietów …")
        uent = []
        for nevra in repoquery(["--unneeded"]):
            ent = Entry(nevra, sizes.get(re.sub(r"-0:(?=\d)", "-", nevra), 0), "root_pkg",
                        pkgs=[nevra], note="Zależność, której nic już nie wymaga", root=True)
            uent.append(_rate_fixed(
                ent, kb.REVIEW, "Pakiet doinstalowany jako zależność innego programu.",
                "dnf uważa, że nic go już nie wymaga. Nazwa nie mówi, czy używasz go ręcznie, "
                "więc przejrzyj listę.", "(dnf repoquery --unneeded)"))
        cats.append(Category(
            "packages", "Niepotrzebne pakiety",
            "Doinstalowane zależności, których nic już nie wymaga. "
            "Przejrzyj listę i zaznacz tylko to, czego na pewno nie potrzebujesz.",
            True, uent,
            protected=[Protected("Pakiety zainstalowane przez Ciebie", "dnf ich nie uznaje za "
                                 "niepotrzebne - nie pojawiają się na liście.")]))
    status("Sprawdzam inne dyski …")
    found = disks_mod.list_disks()
    labels = disks_mod.mount_labels(found)
    mounts = read_mounts()
    KB.data_mounts = data_mounts(mounts)
    cats.extend(volume_trash_categories(found, labels))
    for cat in cats:
        for e in cat.entries:
            if not e.disk:
                where = "/" if e.root else str(HOME)
                mp = mount_of(where, mounts)
                e.disk = labels.get(mp, mp)
            e.suggested = e.checked
    return cats


def volume_trash_categories(found: list, labels: dict) -> list:
    """Kosze (.Trash-UID) na dodatkowych, zamontowanych dyskach."""
    uid = os.getuid()
    out: list = []
    seen: set = set()
    for d in found:
        for p in d.parts:
            for mp in p.mounts:
                if mp in seen or not mp.startswith(("/mnt/", "/media/", "/run/media/")):
                    continue
                seen.add(mp)
                trash = os.path.join(mp, f".Trash-{uid}")
                try:
                    st = os.lstat(trash)
                except OSError:
                    continue
                if not os.path.isdir(trash) or os.path.islink(trash) or st.st_uid != uid:
                    continue
                paths = [os.path.join(trash, "files"), os.path.join(trash, "info")]
                size = sum(path_size(x) for x in paths)
                if size <= 0:
                    continue
                allow_root(trash)
                e = _rate(Entry(f"Opróżnij kosz na dysku {mp}", size, "contents", paths, note=trash), trash)
                e.why = "Usunięcie jest nieodwracalne - dlatego nie zaznaczam tego sam. Sprawdź kosz."
                e.disk = labels.get(mp, mp)
                out.append(Category("trash", f"Kosz na dysku {mp}",
                                    f"Kosz użytkownika na osobnym dysku ({e.disk}).", False, [e]))
    return out


def allow_root(path: str) -> None:
    """Dopuszcza usuwanie w dodatkowym katalogu (tylko .Trash-UID sprawdzone wyzej)."""
    p = Path(path)
    if p not in ALLOWED_ROOTS:
        ALLOWED_ROOTS.append(p)


HOME_PROTECTED = [
    ("Documents", "Dokumenty"), ("Dokumenty", "Dokumenty"), ("Pictures", "Obrazy"),
    ("Obrazy", "Obrazy"), ("Videos", "Wideo"), ("Wideo", "Wideo"), ("Music", "Muzyka"),
    ("Muzyka", "Muzyka"), ("Desktop", "Pulpit"), ("Pulpit", "Pulpit"),
]
HOME_KEEP = [".config", ".ssh", ".gnupg", ".mozilla", ".thunderbird", ".local/share"]


def protected_items(scan_result=None) -> list:
    """Stale chronione miejsca w katalogu domowym (z rozmiarami, jesli jest skan)."""
    out: list = []
    nodes = getattr(scan_result, "nodes", {}) or {}
    for name, title in HOME_PROTECTED:
        p = HOME / name
        if not p.is_dir():
            continue
        v = KB.classify(str(p))
        size = (nodes.get(str(p)) or [0])[0]
        out.append(Protected(f"~/{name}", f"{title} - program nigdy ich nie usuwa.", size,
                             str(p), v.rating))
    for name in HOME_KEEP:
        p = HOME / name
        if not p.exists():
            continue
        v = KB.classify(str(p))
        size = (nodes.get(str(p)) or [0])[0]
        out.append(Protected(f"~/{name}", v.why or v.what, size, str(p), v.rating))
    return out


# -------------------------------------------------------------- czyszczenie --

def build_root_script(entries: list) -> str:
    pkgs: list = []
    others: list = []
    for e in entries:
        if e.kind == "root_pkg":
            for p in e.pkgs:
                if PKG_RE.match(p) and p not in pkgs:
                    pkgs.append(p)
        elif e.kind == "root_sh":
            others.append(f"echo {shlex.quote('== ' + e.label)}")
            others.append("{ " + e.cmd + "\n} || rc=1")
    lines = ["set +e", "rc=0"]  # kod wyjscia = 1, gdy ktorykolwiek krok sie nie powiodl (a nie tylko ostatni)
    if pkgs:
        lines.append("echo '== Usuwanie pakietów'")
        lines.append("dnf remove -y -- " + " ".join(shlex.quote(p) for p in pkgs) + " || rc=1")
    lines.extend(others)
    lines.append("exit $rc")
    return "\n".join(lines)


def run_clean(entries: list, dry: bool, log=lambda _m: None, journal: list | None = None) -> CleanResult:
    res = CleanResult()
    mode = "  [symulacja]" if dry else ""
    for e in [x for x in entries if not x.root]:
        if not e.deletable:
            log(f"→ {e.label}: POMINIĘTO (ocena: {kb.RATING_LABEL.get(e.rating, e.rating)})")
            continue
        log(f"→ {e.label}{mode}")
        if dry:
            for p in e.paths or [e.cmd or e.kind]:
                log(f"    usunąłbym: {p}")
            continue
        errors: list = []
        if e.kind == "path":
            for p in e.paths:
                if e.rule == "analiza" and not rules.allowed(
                        p, e.reasons, e.rating, "dir" if os.path.isdir(p) and not os.path.islink(p) else "file",
                        settings.RUNTIME["rules_off"]):
                    errors.append(f"pominięto (wyłączone w Ustawienia → Reguły): {p}")  # ostatnia blokada, niezalezna od listy
                    continue
                if e.user_pick:
                    ok, why = is_user_target(p)
                    if not ok:
                        errors.append(f"pominięto ({why}): {p}")
                    elif e.trash:
                        trash_path(p, errors)
                    else:
                        remove_path(p, errors, user=True)
                else:
                    remove_path(p, errors)
        elif e.kind == "contents":
            for p in e.paths:
                remove_contents(p, errors)
        elif e.kind == "podman_prune":
            code, out = run_text(["podman", "image", "prune", "-f"], 600)
            log("    " + (out.strip()[-300:] or f"podman zakończył z kodem {code}"))
            if code != 0:
                errors.append(f"podman: kod {code}")
        elif e.kind == "flatpak_user":
            code, out = run_text(
                ["flatpak", "uninstall", "--unused", "--user", "-y", "--noninteractive"],
                600,
            )
            log("    " + (out.strip() or f"flatpak zakończył z kodem {code}"))
            if code != 0:
                errors.append(f"flatpak: kod {code}")
        for er in errors[:20]:
            log(f"    ! {er}")
        if len(errors) > 20:
            log(f"    ! … i {len(errors) - 20} kolejnych błędów")
        if errors:
            res.problems += 1
        elif journal is not None:
            journal.append({"label": e.label, "size": e.size, "paths": list(e.paths or [e.cmd or e.kind]),
                            "how": "trash" if (e.user_pick and e.trash) else ("command" if e.kind == "flatpak_user" else "delete")})
        if errors:
            pass
        elif e.user_pick and e.trash:
            res.trashed += e.size
            log(f"    przeniesiono do kosza ok. {fmt_size(e.size)}")
        else:
            res.freed += e.size
            log(f"    zwolniono ok. {fmt_size(e.size)}")

    root_entries = [x for x in entries if x.root and x.deletable]
    if root_entries:
        script = build_root_script(root_entries)
        if dry:
            log("→ Operacje administratora  [symulacja], wykonałbym:")
            for ln in script.splitlines():
                log("    " + ln)
        else:
            log("→ Operacje administratora (czekam na hasło) …")
            try:
                proc = subprocess.Popen(
                    ["pkexec", "/bin/bash", "-c", script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    log("    " + line.rstrip())
                code = proc.wait()
                if code in (126, 127):
                    log("    ! Anulowano lub brak autoryzacji - nic nie usunięto.")
                    res.problems += 1
                elif code == 0:
                    res.freed += sum(x.size for x in root_entries)
                else:
                    log(f"    ! Polecenia zakończyły się kodem {code}")
                    res.problems += 1
            except FileNotFoundError:
                log("    ! Brak polecenia pkexec (pakiet polkit).")
                res.problems += 1
    return res
