"""Skaner calego dysku: rozmiary katalogow, najwieksze pliki, typy plikow, oceny.

Tylko biblioteka standardowa. Zrodlo tego modulu (razem z kb.py) jest tez
uruchamiane jako administrator przez `pkexec python3 -I -c ...` - patrz
build_admin_source(). Linie z markerem [pkg] sa wtedy usuwane.
"""
from __future__ import annotations

import hashlib
import stat
import heapq
import re
import json
import os
import shutil
import subprocess
import time

from . import kb  # [pkg]

MB = 1024 * 1024
MIN_LISTED = 256 * 1024  # najmniejszy plik na liscie 'najwieksze pliki'
PSEUDO_FS = {
    "proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "cgroup", "cgroup2", "securityfs",
    "debugfs", "tracefs", "configfs", "fusectl", "pstore", "bpf", "mqueue", "hugetlbfs",
    "autofs", "binfmt_misc", "efivarfs", "overlay", "squashfs", "ramfs", "nsfs",
    "fuse.portal", "fuse.gvfsd-fuse", "fuse.kio-fuse", "nfs", "nfs4", "cifs", "smb3",
    "fuse.sshfs", "selinuxfs",
}


LOCAL_FUSE = {"fuse.ntfs-3g", "fuse.exfat", "fuse.bindfs", "fuse.encfs", "fuse.gocryptfs", "fuse.appimage"}  # lokalne - skanujemy



_WIN = os.name == "nt"


def _fwd(path: str) -> str:
    """Wewnatrz skanera sciezki maja postac z '/' (takze na Windows); na koncu wynik wraca do postaci natywnej (_to_native)."""
    return path.replace("\\", "/") if _WIN else path


def _lc(path: str) -> str:
    return path.lower() if _WIN else path  # baza wiedzy Windows trzyma 'home' malymi literami


def _to_native(res: "ScanResult") -> None:
    if not _WIN:
        return
    n = lambda p: p.replace("/", "\\")
    res.root = n(res.root)
    res.nodes = {n(k): v for k, v in res.nodes.items()}
    for t in res.top_files:
        t[1] = n(t[1])
    for a in res.advice:
        a[1] = n(a[1])
    res.keepers = {n(k) for k in res.keepers}


def _alloc(st) -> int:  # jak osal.alloc_size; tu osobno, bo scanner trafia tez do samodzielnego skryptu admina
    blocks = getattr(st, "st_blocks", None)
    return blocks * 512 if blocks is not None else int(st.st_size)

def pseudo_mounts(mounts_file: str = "/proc/self/mounts") -> set:
    """Punkty montowania, ktorych nie skanujemy (wirtualne i sieciowe)."""
    out = {"/proc", "/sys", "/dev", "/run"}
    try:
        with open(mounts_file, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and (parts[2] in PSEUDO_FS or (parts[2].startswith("fuse.") and parts[2] not in LOCAL_FUSE)
                                        or parts[2] in ("davfs", "9p", "afs", "ceph", "glusterfs")):
                    out.add(parts[1].replace("\\040", " "))
    except OSError:
        pass
    out.discard("/")
    return out


class ScanResult:
    def __init__(self, root: str = "", mode: str = "user") -> None:
        self.root = root
        self.mode = mode
        self.total = 0
        self.nfiles = 0
        self.ndirs = 0
        self.errors = 0
        self.seconds = 0.0
        self.cancelled = False
        self.nodes: dict = {}  # sciezka -> [rozmiar, plikow, ocena, tytul, glebokosc]
        self.top_files: list = []  # [rozmiar, sciezka, mtime, ocena, tytul]
        self.by_type: dict = {}  # kategoria -> [bajty, liczba]
        self.by_rating: dict = {r: 0 for r in kb.RATINGS}
        # propozycje algorytmu: [wynik, sciezka, rozmiar, mtime, ocena, tytul, [powody], rodzaj, grupa]
        self.advice: list = []
        self.advice_notes: list = []  # np. "limit czasu przy szukaniu duplikatow"
        self.keepers: set = set()  # egzemplarze, ktore detektory (duplikaty/wersje/kopie) zostawiaja - nigdy nie sa proponowane

    def to_dict(self) -> dict:
        return {k: (sorted(v) if isinstance(v, set) else v) for k, v in self.__dict__.items() if not k.startswith("_")}

    @classmethod
    def from_dict(cls, d: dict) -> "ScanResult":
        r = cls()
        r.__dict__.update(d)
        r.keepers = set(r.keepers)
        return r

    def children(self, path: str) -> list:
        """Zapamietane podkatalogi bezposrednie: [(sciezka, rozmiar, plikow, ocena, tytul)]."""
        idx = self.__dict__.get("_index")
        if idx is None or self.__dict__.get("_index_n") != len(self.nodes):
            idx = {}
            for p, (size, files, rating, title, _d) in self.nodes.items():
                if p == self.root or p == "/" or p.rstrip("/\\") == self.root.rstrip("/\\"):
                    continue
                parent = os.path.dirname(p.rstrip("/\\")) or "/"
                idx.setdefault(parent, []).append((p, size, files, rating, title))
            for lst in idx.values():
                lst.sort(key=lambda x: -x[1])
            self._index, self._index_n = idx, len(self.nodes)
        return list(idx.get(path.rstrip("/\\") or "/", []))


# ------------------------------------------------------------------ algorytm --
# Ocena 0-100, jak bardzo warto usunac plik. Suma punktow z kilku sygnalow, kazdy ma powod
# wyswietlany uzytkownikowi. Pliki 'Nie ruszaj' nie dostaja nigdy punktow; 'Twoje pliki'
# trafiaja na liste tylko przy konkretnym sygnale (duplikat, instalator, niedokonczone
# pobieranie) - sam wiek nigdy nie wystarcza.
DAY = 86400
MIN_SCORE = 45  # ponizej nie proponujemy
AUTO_SCORE = 75  # od tej oceny (i nie 'Twoje pliki') zaznaczamy sami
BASE = {kb.SAFE: 55, kb.REVIEW: 25, kb.MINE: 0}
INSTALLER = set("rpm deb appimage run msi exe dmg iso img".split())
ARCHIVE = set("zip 7z rar tar gz tgz xz bz2 zst".split())
PARTIAL = set("part crdownload download".split())
TEMPBAK = set("tmp temp bak old orig swp".split())
COVERED = ("/.cache", "/.var/app", "/.local/share/Trash", "/.local/share/flatpak")


def _age_points(days: float) -> tuple:
    if days < 14:
        return -35, kb.reason("fresh", int(days))
    if days < 60:
        return 0, ""
    if days < 180:
        return 10, kb.reason("stale_days", int(days))
    if days < 365:
        return 18, kb.reason("stale_months", int(days // 30))
    return 25, kb.reason("stale_year", int(days // 30))


def _size_points(size: int) -> tuple:
    gb = size / 1024 ** 3
    if gb >= 10:
        return 15, kb.reason("huge", "%.1f GB" % gb)
    if gb >= 1:
        return 12, kb.reason("big", "%.1f GB" % gb)
    if size >= 100 * MB:
        return 8, kb.reason("big", "%d MB" % (size // MB))
    return 0, ""


def score_item(name: str, rating: str, size: int, mtime: float, atime: float, now: float,
               extra: list | None = None, inbox: bool = True) -> tuple:
    """(wynik, [powody]). `extra` = [(punkty, powod)] z sygnalow zewnetrznych (duplikat itp.)."""
    if rating not in BASE:
        return 0, []
    pts = BASE[rating]
    reasons = []
    if rating == kb.SAFE:
        reasons.append(kb.reason("loc_safe"))
    elif rating == kb.REVIEW:
        reasons.append(kb.reason("loc_review"))
    specific = bool(extra)
    for p, why in (extra or []):
        pts += p
        reasons.append(why)
    ext = kb.ext_of(name)
    low = name.lower()
    typ = None
    if ext in PARTIAL:
        typ = (35, kb.reason("partial"))
    elif low.startswith("core.") and ext.isdigit():
        typ = (35, kb.reason("coredump"))
    elif ext in INSTALLER and inbox:
        typ = (30, kb.reason("installer"))
    elif ext in TEMPBAK or low.endswith("~"):
        typ = (25, kb.reason("tempbak"))
    elif ext == "log":
        typ = (15, kb.reason("log"))
    elif ext in ARCHIVE and inbox:
        typ = (15, kb.reason("archive"))
    if typ:
        pts += typ[0]
        reasons.append(typ[1])
        specific = True
    if rating == kb.MINE and not specific:
        return 0, []
    last = max(mtime, min(atime, now))
    ap, areason = _age_points((now - last) / DAY)
    if ap < 0 and extra:
        ap, areason = 0, ""  # kopia jest zbedna niezaleznie od tego, jak swieza
    pts += ap
    if areason:
        reasons.append(areason)
    sp, sreason = _size_points(size)
    pts += sp
    if sreason:
        reasons.append(sreason)
    return max(0, min(99, pts)), reasons


def _stem(name: str) -> str:
    low = name.lower()
    for d in (".tar.gz", ".tar.xz", ".tar.bz2", ".tar.zst"):
        if low.endswith(d):
            return name[: -len(d)]
    return name.rsplit(".", 1)[0] if "." in name.strip(".") else name


HASH_CACHE: dict = {}  # "sciezka|rozmiar|mtime_ns|czesciowy" -> skrot; trzymany miedzy skanami
_HASH_USED: set = set()
HASH_CACHE_MAX = 200000


def load_hash_cache(path: str) -> None:
    HASH_CACHE.clear()
    _HASH_USED.clear()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            HASH_CACHE.update({k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)})
    except (OSError, ValueError):
        pass


def save_hash_cache(path: str) -> None:
    """Zapisuje tylko wpisy uzyte w tym skanie (stare pliki odpadaja same)."""
    keep = {k: v for k, v in HASH_CACHE.items() if k in _HASH_USED}
    if len(keep) > HASH_CACHE_MAX:
        keep = dict(list(keep.items())[-HASH_CACHE_MAX:])
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(keep, f)
        os.replace(tmp, path)
    except OSError:
        pass


EDGE = 65536  # poczatek i koniec pliku w skrocie czesciowym
SAMPLES = 6  # + tyle probek po 4 KB rownomiernie w srodku (pliki z wypelnionym poczatkiem/koncem: obrazy dyskow, torrenty)
SAMPLE_LEN = 4096


# Flagi i pread: na Windows ich nie ma (skaner jest tez osadzany w skrypcie roota, wiec bez importu osal)
_O_FLAGS = getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)


def _pread(fd: int, n: int, offset: int) -> bytes:
    if hasattr(os, "pread"):
        return os.pread(fd, n, offset)
    os.lseek(fd, offset, os.SEEK_SET)
    return os.read(fd, n)


def _file_hash(path: str, size: int, partial: bool) -> str:
    h = hashlib.blake2b(digest_size=16)
    fd = os.open(path, os.O_RDONLY | _O_FLAGS)  # bez symlinkow i FIFO (podmiana w trakcie skanu)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise OSError("nie jest zwyklym plikiem")
        # 'p2' = obecna definicja skrotu czesciowego (stare wpisy '1' sie nie zgadzaja i po prostu odpadaja)
        key = f"{path}|{st.st_size}|{st.st_mtime_ns}|{'p2' if partial else 0}"  # zmiana rozmiaru lub czasu = nowy skrot
        cached = HASH_CACHE.get(key)
        if cached:
            _HASH_USED.add(key)
            return cached
        if partial:
            n = st.st_size
            offs = [0] + [n * k // (SAMPLES + 1) for k in range(1, SAMPLES + 1)] + [max(n - EDGE, 0)]
            for i, off in enumerate(offs):
                h.update(_pread(fd, EDGE if i in (0, len(offs) - 1) else SAMPLE_LEN, off))
        else:
            try:
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_SEQUENTIAL)
            except (AttributeError, OSError):
                pass
            while True:
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    break
                h.update(chunk)
    finally:
        os.close(fd)
    HASH_CACHE[key] = h.hexdigest()
    _HASH_USED.add(key)
    return HASH_CACHE[key]


def find_duplicates(by_size: dict, budget: float, notes: list, on_step=None) -> list:
    """Grupy identycznych plikow: [[(sciezka, mtime, ocena), ...], ...] (>= 2 w grupie).

    Najpierw rozmiar, potem skrot poczatku i konca, na koncu pelny skrot - dopiero on
    uznaje pliki za identyczne. Limit czasu `budget` sekund."""
    deadline = time.monotonic() + budget
    groups = []
    todo = sum(1 for f in by_size.values() if len(f) >= 2)
    step = 0
    for size, files in sorted(by_size.items(), key=lambda kv: -kv[0]):
        if len(files) < 2:
            continue
        step += 1
        if on_step is not None:
            on_step(step, todo)
        if time.monotonic() > deadline:
            notes.append("Szukanie duplikatów przerwane po limicie czasu - część dużych plików nie była sprawdzona.")
            break
        quick: dict = {}
        for f in files:
            try:
                quick.setdefault(_file_hash(f[0], size, True), []).append(f)
            except OSError:
                continue
        for cand in quick.values():
            if len(cand) < 2:
                continue
            full: dict = {}
            for f in cand:
                try:
                    full.setdefault(_file_hash(f[0], size, False), []).append(f)
                except OSError:
                    continue
            groups.extend(g for g in full.values() if len(g) >= 2)
    return groups


def _pick_original(group: list) -> tuple:
    """Ktory egzemplarz zostaje: najpierw 'Twoje pliki', potem starszy, potem krotsza sciezka."""
    order = {kb.MINE: 0, kb.REVIEW: 1, kb.SAFE: 2}
    best = min(group, key=lambda f: (order.get(f[2], 3), f[1], len(f[0])))
    return best, [f for f in group if f is not best]


def _installed_rpms(paths: list) -> dict:
    """{sciezka_rpm: nazwa_pakietu} dla plikow .rpm, ktorych pakiet jest juz zainstalowany."""
    out: dict = {}
    if not shutil.which("rpm"):
        return out
    for p in paths[:60]:
        try:
            name = subprocess.run(["rpm", "-qp", "--qf", "%{NAME}", p], capture_output=True,
                                  text=True, timeout=10).stdout.strip()
            if name and subprocess.run(["rpm", "-q", name], capture_output=True,
                                       timeout=10).returncode == 0:
                out[p] = name
        except (OSError, subprocess.SubprocessError):
            continue
    return out


# Drzewa zarzadzane przez inne programy: tam identyczne pliki sa celowe (warstwy kontenerow,
# prefiksy Wine/Proton, pakiety Unity, rejestr Cargo, srodowiska jezykow). Nigdy nic stad nie proponujemy.
MANAGED = (
    "/containers/storage/", "/compatdata/", "/compatibilitytools.d/", "/steamapps/common/",
    "/steamapps/workshop/", "/Library/PackageCache/", "/Library/Bee/", "/.cargo/", "/.rustup/",
    "/node_modules/", "/.git/", "/site-packages/", "/dist-packages/", "/.venv/", "/venv/",
    "/.var/app/", "/.local/share/flatpak/", "/.wine/", "/.steam/", "/.local/share/Steam/",
    "/.gradle/", "/.m2/", "/.npm/", "/.nuget/", "/.pyenv/", "/.nvm/", "/.sdkman/",
    "/.platformio/", "/.espressif/", "/.arduino15/", "/.conda/", "/miniconda3/", "/anaconda3/",
    "/.local/share/containers/", "/.local/share/virtualenv/", "/.pub-cache/", "/.bun/",
    "/Editor/Data/", "/PlaybackEngines/",
)
CODE = set("dll so jar class pyc pyo o a ko dylib lib pdb map js mjs ts py h hpp c cc cpp rs go java cs "
           "json xml yaml yml toml ini cfg conf sh bat lua".split())
INBOX = ("Downloads", "Pobrane", "Desktop", "Pulpit")
_INBOX_LC = {i.lower() for i in INBOX}


_MANAGED_RE = re.compile("|".join(re.escape(m) for m in MANAGED))


def _managed(path: str) -> bool:
    return _MANAGED_RE.search(path) is not None


def _in_inbox(path: str, home: str) -> bool:
    """Plik lezy w Pobranych/Pulpicie (najwyzej 3 poziomy w glab) - tam instalatory sa naprawde 'do uzycia raz'."""
    if not _lc(path).startswith(home + "/"):
        return False
    parts = path[len(home) + 1:].split("/")
    return bool(parts) and (parts[0] in INBOX or (_WIN and parts[0].lower() in _INBOX_LC)) and len(parts) <= 4


ARTIFACTS = {
    # nazwa folderu: (plik/folder obok, wymagane razem, nazwa projektu)
    "Library": (("ProjectSettings", "Assets"), "Unity"),
    "Temp": (("ProjectSettings", "Assets"), "Unity"),
    "Obj": (("ProjectSettings", "Assets"), "Unity"),
    "Logs": (("ProjectSettings", "Assets"), "Unity"),
    "target": (("Cargo.toml",), "Rust"),
    ".pio": (("platformio.ini",), "PlatformIO"),
    "build": (("CMakeLists.txt", "sdkconfig"), "ESP-IDF"),
}


def project_artifact(path: str) -> str:
    """Nazwa projektu (Unity, Rust, PlatformIO, ESP-IDF), jesli `path` to wygenerowany folder takiego projektu
    (rozpoznany po plikach obok), inaczej ''. Otwarty projekt Unity (blokada w Temp) jest pomijany."""
    spec = ARTIFACTS.get(os.path.basename(path))
    if spec is None or "/.Trash-" in path or "/Trash/" in path:  # w koszu to juz nie jest projekt
        return ""
    parent = os.path.dirname(path)
    if not all(os.path.exists(os.path.join(parent, need)) for need in spec[0]):
        return ""
    if spec[1] == "Unity":
        if not os.path.isfile(os.path.join(parent, "ProjectSettings", "ProjectVersion.txt")):
            return ""
        if os.path.exists(os.path.join(parent, "Temp", "UnityLockfile")):
            return ""  # projekt jest teraz otwarty w edytorze
    return spec[1]


COPY_RE = re.compile(r"\s*\((\d{1,2})\)$")
NUM_RE = re.compile(r"(?<![A-Za-z0-9])[vV]?(\d+(?:\.\d+)*)(?![A-Za-z0-9])")
DATE_RE = re.compile(r"(?:19|20)\d{2}[-_.]\d{1,2}[-_.]\d{1,2}|\d{1,2}[-_.]\d{1,2}[-_.](?:19|20)\d{2}")
SET_WORD = re.compile(r"(disc|disk|cd|dvd|part|pt|vol|volume|season|sezon|ep|episode|chapter|cz|tom|seria|page|strona|rev|build)[\s._-]*$", re.I)
VERSIONED = set("rpm deb appimage run msi exe dmg iso img zip 7z rar tar gz tgz xz bz2 zst jar apk".split())


_YEAR_RE = re.compile(r"(19|20)\d{2}")
_DIGITS_TO_LETTERS = str.maketrans("0123456789-_.", "abcdefghijxyz")


def _version_token(stem: str, m) -> bool:
    """Czy ten numer w nazwie to numer WERSJI (a nie czesc zestawu 'Disc 2', rok, data, 32/64 bit)."""
    tok = m.group(1)
    if tok in ("32", "64", "86", "128") or SET_WORD.search(stem[: m.start()]):
        return False
    parts = tok.split(".")
    if any(len(p) >= 8 for p in parts) or _YEAR_RE.fullmatch(tok):
        return False
    return True


def version_key(name: str):
    """(klucz_rodziny, krotka_wersji, rodzaj) albo None. Rodzina = nazwa z numerami WERSJI zamienionymi na '#'
    (instalator-1.2.8.exe i instalator-1.2.9.exe to jedna rodzina; 'Disc 1' i 'Disc 2', lata i daty - nie).
    Rodzaj: 'ver' (numer wersji), 'copy' (sufiks '(N)' dodany przez przegladarke) lub 'plain' (bez numeru)."""
    ext = kb.ext_of(name)
    stem = name[: -len(ext) - 1] if ext and name.lower().endswith("." + ext) else name
    if stem.lower().endswith(".tar"):
        stem = stem[:-4]
    m = COPY_RE.search(stem)
    if m:
        return stem[: m.start()].lower() + "." + ext, (0, int(m.group(1))), "copy"
    stem = DATE_RE.sub(lambda d: "d" + d.group(0).translate(_DIGITS_TO_LETTERS), stem)  # data = staly tekst, nie numer wersji
    nums: list = []

    def sub(m):
        if _version_token(stem, m):
            nums.append(m.group(1))
            return "#"
        return m.group(0)

    key = NUM_RE.sub(sub, stem).lower() + "." + ext
    if not nums:
        return key, (1,), "plain"
    ver = [1]
    for tok in nums:
        ver += [int(p) for p in tok.split(".") if p.isdigit() and len(p) < 8]
    while len(ver) > 2 and ver[-1] == 0:  # 1.1.0 == 1.1
        ver.pop()
    return key, tuple(ver), "ver"


def old_versions(files: list) -> list:
    """files = [(nazwa, sciezka, ...)] z jednego katalogu -> [(plik, powod, sciezka_zostajacego)] dla starszych wersji
    i numerowanych kopii. Zostaje najnowsza wersja (albo oryginal bez sufiksu)."""
    fam: dict = {}
    for f in files:
        if kb.ext_of(f[0]) not in VERSIONED:
            continue
        vk = version_key(f[0])
        if vk is not None:
            fam.setdefault(vk[0], []).append((vk[1], vk[2], f))
    out = []
    for members in fam.values():
        if len(members) < 2 or len({m[0] for m in members}) < 2:
            continue
        keep = max(members, key=lambda m: (m[0], m[2][3]))
        if all(m[1] != "ver" for m in members) and len({m[2][2] for m in members}) > 1:
            keep = max(members, key=lambda m: m[2][3])  # kopia o innym rozmiarze bywa nowszym pobraniem: zostaje nowszy plik
        for ver, kind, f in members:
            if f is keep[2] or (ver == keep[0] and kind == keep[1]):
                continue
            out.append((f, kb.reason("copyname" if kind == "copy" else "oldver", keep[2][0]), keep[2][1]))
    return out


def _covered(path: str, home: str) -> bool:
    return any(_lc(path).startswith(home + c) for c in COVERED) or path.startswith("/var/cache")


def scan(root: str, kbase: "kb.KnowledgeBase", progress=None, cancel=None,
         max_depth: int = 3, keep_min: int = 64 * MB, top_n: int = 1000,
         skip=None, mode: str = "user", advise: bool = True, dup_budget: float = 45.0,
         dup_min: int = 2 * MB, now: float | None = None, min_score: int | None = None) -> ScanResult:
    ms = MIN_SCORE if min_score is None else min_score
    res = ScanResult(root, mode)
    t0 = time.monotonic()
    now = time.time() if now is None else now
    skip = pseudo_mounts() if skip is None else skip
    seen: set = set()
    heap: list = []  # (rozmiar, sciezka, mtime)
    cands: list = []  # [wynik, sciezka, rozmiar, mtime, ocena, tytul, powody, rodzaj]
    by_size: dict = {}  # rozmiar -> [(sciezka, mtime, ocena)] do szukania duplikatow
    rpms: list = []
    n_dup_files = 0
    root = _fwd(root).rstrip("/") or "/"
    root_v = kbase.classify(root)
    home = kbase.home
    stack: list = []

    def push(path: str, depth: int, verdict, mtime: float) -> None:
        try:
            it = os.scandir(path)
        except OSError:
            res.errors += 1
            return
        res.ndirs += 1
        # [sciezka, glebokosc, ocena, rozmiar, plikow, iterator, archiwa, nazwy_podkatalogow, mtime, pliki_z_wersja]
        stack.append([path, depth, verdict, 0, 0, it, [], set(), mtime, [], _managed(path + "/")])

    try:
        root_mtime = os.lstat(root).st_mtime
    except OSError:
        root_mtime = now
    push(root, 0, root_v, root_mtime)
    tick = 0
    while stack:
        fr = stack[-1]
        path, depth, verdict, _s, _f, it = fr[:6]
        try:
            entry = next(it)
        except (StopIteration, OSError):
            try:
                it.close()
            except OSError:
                pass
            stack.pop()
            size, files = fr[3], fr[4]
            if depth <= max_depth or size >= keep_min:
                res.nodes[path] = [size, files, verdict.rating, verdict.title, depth]
            if advise:
                # archiwa i pakiety rpm ocenione dopiero tu: wiemy, co lezy obok
                for name, p, blocks, mt, at in fr[6]:
                    extra = []
                    if _stem(name) in fr[7]:
                        extra.append((30, kb.reason("extracted", _stem(name))))
                    if kb.ext_of(name) == "rpm":
                        rpms.append(p)
                    sc, why = score_item(name, verdict.rating, blocks, mt, at, now, extra, _in_inbox(p, home))
                    if sc >= ms and blocks >= 32 * 1024:
                        fv = kbase.classify_file(p, verdict)
                        cands.append([sc, p, blocks, int(mt), fv.rating, fv.title, why, "file"])
                for (name, p, blocks, mt, at), why_old, keeper in old_versions(fr[9]):  # starsze wersje i numerowane kopie
                    res.keepers.add(keeper)
                    sc, why = score_item(name, verdict.rating, blocks, mt, at, now,
                                         [(35 if "starsza" in why_old else 25, why_old)], _in_inbox(p, home))
                    if sc >= ms and blocks >= 32 * 1024:
                        fv = kbase.classify_file(p, verdict)
                        cands.append([sc, p, blocks, int(mt), fv.rating, fv.title, why, "file"])
                # katalogi projektow (node_modules, .venv, __pycache__ ...) poza miejscami z kategorii
                rule = kbase.match_here(path)
                if (rule is not None and rule[0].startswith("**/") and rule[1] in (kb.SAFE, kb.REVIEW)
                        and size >= 16 * MB and not _covered(path, home) and ".Trash-" not in path
                        and not _managed(os.path.dirname(path) + "/")):
                    sc, why = score_item(os.path.basename(path), rule[1], size, fr[8], 0, now,
                                         [(25, kb.reason("recreatable"))])
                    if sc >= ms:
                        cands.append([sc, path, size, int(fr[8]), rule[1], rule[2], why, "dir"])
                elif rule is None and size >= 64 * MB and os.path.basename(path) in ARTIFACTS:
                    proj = project_artifact(path)
                    if proj:  # folder odtwarzalny z zrodel, nawet gdy lezy wsrod 'Twoich plikow'
                        sc, why = score_item(os.path.basename(path), kb.REVIEW, size, fr[8], 0, now,
                                             [(25, kb.reason("recreatable")), (20, kb.reason("project", proj))])
                        if sc >= ms:
                            cands.append([sc, path, size, int(fr[8]), kb.REVIEW,
                                          f"Folder projektu {proj} do odtworzenia", why, "dir"])
            if stack:
                stack[-1][3] += size
                stack[-1][4] += files
            continue
        tick += 1
        if tick % 2000 == 0:
            if cancel is not None and cancel():
                res.cancelled = True
                break
            if progress is not None:
                progress(res.nfiles, res.total, path)
        try:
            st = entry.stat(follow_symlinks=False)
            is_dir = entry.is_dir(follow_symlinks=False)
        except OSError:
            res.errors += 1
            continue
        epath = _fwd(entry.path)
        blocks = _alloc(st)
        if is_dir:
            if epath in skip:
                continue
            fr[3] += blocks
            fr[7].add(entry.name)
            res.by_rating[verdict.rating] += blocks
            push(epath, depth + 1, kbase.classify_dir(epath, verdict), st.st_mtime)
            continue
        if st.st_nlink > 1:
            key = (st.st_dev, st.st_ino)
            if key in seen:
                continue
            seen.add(key)
        fr[3] += blocks
        fr[4] += 1
        res.nfiles += 1
        res.total += blocks
        rating, category = kb.rating_and_category(entry.name, verdict.rating)
        res.by_rating[rating] += blocks
        cat = res.by_type.setdefault(category, [0, 0])
        cat[0] += blocks
        cat[1] += 1
        if blocks >= MIN_LISTED:
            item = (blocks, epath, int(st.st_mtime))
            if len(heap) < top_n:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)
        if advise and verdict.rating in (kb.REVIEW, kb.MINE) and not fr[10]:
            ext = kb.ext_of(entry.name)
            code = ext in CODE or (ext == "exe" and not _in_inbox(epath, home))
            mt = st.st_mtime
            if not code and ext in VERSIONED:
                fr[9].append((entry.name, epath, blocks, mt, st.st_atime))
            if code:
                pass
            elif ext in ARCHIVE or ext == "rpm":
                fr[6].append((entry.name, epath, blocks, mt, st.st_atime))
            else:
                sc, why = score_item(entry.name, rating, blocks, mt, st.st_atime, now,
                                     inbox=_in_inbox(epath, home))
                if sc >= ms and blocks >= 32 * 1024:
                    fv = kbase.classify_file(epath, verdict)
                    cands.append([sc, epath, blocks, int(mt), fv.rating, fv.title, why, "file"])
            if not code and st.st_size >= dup_min and n_dup_files < 300000:
                by_size.setdefault(st.st_size, []).append((epath, st.st_mtime, verdict.rating))
                n_dup_files += 1
    for fr in stack:  # po przerwaniu
        try:
            fr[5].close()
        except OSError:
            pass
    res.total = sum(v[0] for k, v in res.nodes.items() if k == root) or res.total
    for blocks, p, mtime in sorted(heap, reverse=True):
        fv = kbase.classify_file(p)
        res.top_files.append([blocks, p, mtime, fv.rating, fv.title])

    if advise and not res.cancelled:
        if progress is not None:
            progress(res.nfiles, res.total, "@rpm")
        by_path = {c[1]: c for c in cands}
        installed = _installed_rpms(rpms)
        for p, pkg in installed.items():
            c = by_path.get(p)
            if c is not None:
                c[0] = min(99, c[0] + 40)
                c[6].append(kb.reason("rpm_installed", pkg))
        if progress is not None:
            progress(0, 0, "@dup")
        on_step = (lambda i, t: progress(i, t, "@dup")) if progress is not None else None
        for group in find_duplicates(by_size, dup_budget, res.advice_notes, on_step):
            orig, copies = _pick_original(group)
            res.keepers.add(orig[0])
            for p, mt, rt in copies:
                if rt == kb.KEEP:
                    continue
                try:
                    st = os.lstat(p)
                except OSError:
                    continue
                name = os.path.basename(p)
                where = os.path.dirname(orig[0])
                where = ("~" + where[len(home):]) if _lc(where).startswith(home) else where
                sc, why = score_item(name, rt, _alloc(st), st.st_mtime, st.st_atime, now,
                                     [(50, kb.reason("dup", os.path.basename(orig[0]), where))],
                                     _in_inbox(p, home))
                fv = kbase.classify_file(p)
                old = by_path.get(p)
                if old is not None:  # ten sam plik ocenily tez inne sygnaly - polacz
                    old[0] = min(99, max(old[0], sc) + 5)
                    old[6] = why + [w for w in old[6] if w not in why]
                    old[7] = "file"
                    continue
                if sc >= ms:
                    c = [sc, p, _alloc(st), int(st.st_mtime), fv.rating, fv.title, why, "dup"]
                    cands.append(c)
                    by_path[p] = c
        dirs = [c[1] + "/" for c in cands if c[7] == "dir"]
        if dirs:  # pliki wewnatrz proponowanego katalogu sa juz w nim zawarte
            dirs_t = tuple(dirs)
            cands = [c for c in cands if c[7] == "dir" or not c[1].startswith(dirs_t)]
        cands = [c for c in cands if c[1] not in res.keepers]  # zostawiany egzemplarz jednego detektora nie jest kasowany przez inny
        merged: dict = {}
        for c in cands:  # ten sam plik z kilku sygnalow (np. instalator + starsza wersja) = jedna pozycja
            o = merged.get(c[1])
            if o is None:
                merged[c[1]] = c
            else:
                best, other = (c, o) if c[0] > o[0] else (o, c)
                best[6] = best[6] + [w for w in other[6] if w not in best[6]]
                merged[c[1]] = best
        cands = list(merged.values())
        cands.sort(key=lambda c: (-c[0], -c[2]))
        res.advice = [c + [""] for c in cands[:1500]]
    res.seconds = round(time.monotonic() - t0, 1)
    _to_native(res)
    return res


def merge_results(results: list, top_limit: int = 1000) -> ScanResult:
    """Laczy wyniki skanow kilku miejsc (np. dom + dyski danych) w jeden."""
    out = ScanResult(root=results[0].root if len(results) == 1 else "", mode=results[0].mode)
    best: dict = {}
    for r in results:
        out.total += r.total
        out.nfiles += r.nfiles
        out.ndirs += r.ndirs
        out.errors += r.errors
        out.seconds += r.seconds
        out.cancelled = out.cancelled or r.cancelled
        out.nodes.update(r.nodes)
        out.top_files += r.top_files
        for k, (b, n) in r.by_type.items():
            c = out.by_type.setdefault(k, [0, 0])
            c[0] += b
            c[1] += n
        for k, v in r.by_rating.items():
            out.by_rating[k] = out.by_rating.get(k, 0) + v
        for a in r.advice:
            if a[1] not in best or a[0] > best[a[1]][0]:
                best[a[1]] = a
        out.advice_notes += r.advice_notes
        out.keepers |= r.keepers
    out.top_files.sort(key=lambda f: -f[0])
    out.top_files = out.top_files[:top_limit]
    for p in out.keepers:
        best.pop(p, None)
    out.advice = sorted(best.values(), key=lambda a: (-a[0], -a[2]))[:1500]
    out.seconds = round(out.seconds, 1)
    if len(results) > 1:
        out.root = ""
    return out


ADMIN_SCRIPT = "/usr/local/lib/tidydisk/admin_scan.py"  # instalacja z install.sh
ADMIN_SCRIPT_PKG = "/usr/libexec/tidydisk/admin_scan.py"  # instalacja z pakietu RPM


def find_admin_script(version: str = ""):
    """(sciezka, ok, powod): pierwszy poprawny skaner administratora (pakiet RPM ma pierwszenstwo)."""
    why = "brak zainstalowanego skanera administratora"
    for p in (ADMIN_SCRIPT_PKG, ADMIN_SCRIPT):
        ok, w = admin_script_ok(p, version)
        if ok:
            return p, True, ""
        if os.path.exists(p):
            why = w
    return ADMIN_SCRIPT, False, why


def admin_script_ok(path: str = ADMIN_SCRIPT, version: str = ""):
    """(ok, powod): skrypt skanu administratora musi nalezec do roota, nie byc zapisywalny
    dla innych i miec wersje zgodna z programem - inaczej kod z katalogu uzytkownika
    dostalby uprawnienia roota."""
    try:
        if os.path.realpath(path) != path:
            return False, f"{path} nie może leżeć za dowiązaniem symbolicznym"
        for p in (path, os.path.dirname(path)):
            st = os.lstat(p)
            if st.st_uid != 0 or (st.st_mode & 0o022) or os.path.islink(p):
                return False, f"{p} musi należeć do roota i nie być zapisywalny dla innych"
        with open(path, encoding="utf-8") as f:
            head = f.readline()
            if head.startswith("#!"):  # skrypt wykonywalny (pkexec + regula polkit): znacznik wersji w drugiej linii
                head = f.readline()
    except OSError:
        return False, "brak zainstalowanego skanera administratora"
    if version and head.strip() != f"# tidydisk-admin {version}":
        return False, "skaner administratora jest w innej wersji niż program"
    return True, ""


def build_admin_source(root: str, home: str, data_mounts=(), argv: bool = False, version: str = "") -> str:
    """Samowystarczalny kod Pythona (kb + scanner + main) do `python3 -I -c`
    (albo, z argv=True, do pliku wywolywanego z argumentami: root home mounts_json)."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "kb.py"), encoding="utf-8") as f:
        kb_src = f.read()
    with open(os.path.abspath(__file__), encoding="utf-8") as f:
        sc_src = f.read().split("def build_admin_source")[0]
    sc_src = "".join(ln for ln in sc_src.splitlines(True) if "# [pkg]" not in ln)
    # drugi kod z `from __future__` musi byc na poczatku modulu: usuwamy z obu
    kb_src = kb_src.replace("from __future__ import annotations\n", "")
    sc_src = sc_src.replace("from __future__ import annotations\n", "")
    if argv:  # wywolanie z argumentami: sprawdzamy je, bo skrypt dziala jako root
        args = ("try:\n"
                "    _root, _home, _mounts = _sys.argv[1], _sys.argv[2], json.loads(_sys.argv[3])\n"
                "    assert os.path.isabs(_root) and os.path.isdir(_root) and os.path.isabs(_home)\n"
                "    assert isinstance(_mounts, list) and all(isinstance(m, str) and os.path.isabs(m) for m in _mounts)\n"
                "except (IndexError, ValueError, AssertionError, RecursionError):\n"
                "    _sys.exit(2)\n")
    else:
        args = f"_root, _home, _mounts = {root!r}, {home!r}, {list(data_mounts)!r}\n"
    main = (
        "\nimport sys as _sys\n" + args +
        "_kb = kb.KnowledgeBase(_home, _mounts)\n"
        "def _prog(n, total, path):\n"
        "    print('P %d' % n, flush=True)\n"
        "_res = scan(_root, _kb, _prog, max_depth=4, keep_min=32 * 1024 * 1024, mode='admin', advise=False)\n"
        "print('J ' + json.dumps(_res.to_dict()), flush=True)\n"
    )
    return (
        ("#!/usr/bin/python3 -I\n" if argv else "")
        + (f"# tidydisk-admin {version}\n" if version else "")
        + "from __future__ import annotations\n"
        "import sys, types\n"
        "kb = types.ModuleType('kb')\n"
        "sys.modules['kb'] = kb\n"
        f"exec(compile({kb_src!r}, 'kb.py', 'exec'), kb.__dict__)\n"
        + sc_src
        + main
    )


def parse_admin_line(line: str):
    """('P', n) | ('J', ScanResult) | None"""
    line = line.strip()
    if line.startswith("P "):
        try:
            return "P", int(line[2:])
        except ValueError:
            return None
    if line.startswith("J "):
        try:
            return "J", ScanResult.from_dict(json.loads(line[2:]))
        except ValueError:
            return None
    return None
