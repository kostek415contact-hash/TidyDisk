"""Dyski i partycje (lsblk na Linuksie, litery dyskow na Windows). Bez zaleznosci od Qt."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field

LSBLK_COLS = "NAME,PATH,TYPE,SIZE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,ROTA,TRAN,RM,PKNAME"


@dataclass
class Part:
    name: str
    path: str
    size: int
    fstype: str = ""
    label: str = ""
    mounts: list = field(default_factory=list)
    used: int = 0
    free: int = 0
    uuid: str = ""
    group: int = 1  # ile partycji tworzy ten sam system plikow (btrfs na wielu partycjach)
    volume_size: int = 0

    @property
    def mount(self) -> str:
        return self.mounts[0] if self.mounts else ""


@dataclass
class Disk:
    name: str
    path: str
    size: int
    model: str = ""
    kind: str = "Dysk"  # NVMe SSD | SSD | HDD | USB | Wirtualny
    parts: list = field(default_factory=list)


def _usage(mount: str):
    try:
        if not hasattr(os, "statvfs"):  # Windows: brak statvfs
            u = shutil.disk_usage(mount)
            return u.used, u.free
        st = os.statvfs(mount)
    except OSError:
        return 0, 0
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    return max(total - st.f_bfree * st.f_frsize, 0), free


def _kind(dev: dict) -> str:
    name = dev.get("name") or ""
    tran = (dev.get("tran") or "").lower()
    if name.startswith("zram"):
        return "Wirtualny (zram)"
    if dev.get("rm") in (True, 1, "1"):
        return "USB / wymienny"
    if tran == "usb":
        return "USB / wymienny"
    if tran == "nvme" or name.startswith("nvme"):
        return "NVMe SSD"
    if dev.get("rota") in (False, 0, "0"):
        return "SSD"
    if dev.get("rota") in (True, 1, "1"):
        return "HDD"
    return "Dysk"


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _collect(dev: dict, out: list, usage) -> None:
    """Splaszcza drzewo (partycja -> luks/lvm -> ...) do listy partycji."""
    typ = dev.get("type")
    mounts = [m for m in (dev.get("mountpoints") or []) if m]
    kids = dev.get("children") or []
    if typ != "disk" and (mounts or dev.get("fstype") or not kids):
        p = Part(
            name=dev.get("name") or "",
            path=dev.get("path") or "",
            size=_int(dev.get("size")),
            fstype=dev.get("fstype") or "",
            label=dev.get("label") or "",
            uuid=dev.get("uuid") or "",
            mounts=mounts,
        )
        if mounts:
            real = next((m for m in mounts if not m.startswith("[")), mounts[0])
            p.used, p.free = usage(real)
        out.append(p)
    for k in kids:
        _collect(k, out, usage)


def parse_lsblk(text: str, usage=_usage) -> list:
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    disks: list = []
    for dev in data.get("blockdevices", []):
        if dev.get("type") != "disk":
            continue
        d = Disk(
            name=dev.get("name") or "",
            path=dev.get("path") or "",
            size=_int(dev.get("size")),
            model=(dev.get("model") or "").strip(),
            kind=_kind(dev),
        )
        _collect(dev, d.parts, usage)
        if d.parts or d.size:
            disks.append(d)
    _merge_volumes(disks)
    return disks


def _merge_volumes(disks: list) -> None:
    """Partycje o tym samym UUID (btrfs na kilku partycjach) to jeden system plikow:
    dziedzicza punkt montowania i zajetosc od partycji, ktora lsblk pokazal jako zamontowana."""
    by_uuid: dict = {}
    for d in disks:
        for p in d.parts:
            if p.uuid:
                by_uuid.setdefault(p.uuid, []).append(p)
    for group in by_uuid.values():
        if len(group) < 2:
            continue
        donor = next((p for p in group if p.mounts), None)
        total = sum(p.size for p in group)
        for p in group:
            p.group, p.volume_size = len(group), total
            if donor is not None and not p.mounts:
                p.mounts, p.used, p.free = list(donor.mounts), donor.used, donor.free


def mount_labels(found=None) -> dict:
    """{punkt_montowania: opis dysku} np. '/home' -> 'nvme0n1 · btrfs „fedora”'."""
    out: dict = {}
    for d in (found if found is not None else list_disks()):
        for p in d.parts:
            tag = f"{p.fstype} „{p.label}”" if p.label else p.fstype
            text = f"{d.name} · {tag}" if tag else d.name
            for m in p.mounts:
                if m and not m.startswith("["):
                    out.setdefault(m, text)
    return out


_WIN_TYPES = {2: "Wymienny (USB)", 3: "Dysk lokalny", 4: "Sieciowy", 5: "Napęd optyczny", 6: "RAM"}


def list_disks_windows(letters=None, kind_of=None, volume_info=None, usage=_usage) -> list:
    """Windows: kazda litera dysku to jeden 'dysk' z jedna 'partycja'. Parametry (letters, kind_of, volume_info) to
    wtyczki do testow; domyslnie ctypes (GetLogicalDrives, GetDriveTypeW, GetVolumeInformationW)."""
    import ctypes
    k32 = getattr(ctypes, "windll", None)
    k32 = k32.kernel32 if k32 else None
    if letters is None:
        if k32 is None:
            return []
        mask = k32.GetLogicalDrives()
        letters = [chr(65 + i) for i in range(26) if mask & (1 << i)]
    if kind_of is None:
        kind_of = lambda root: k32.GetDriveTypeW(root) if k32 else 3
    if volume_info is None:
        def volume_info(root):
            if k32 is None:
                return "", ""
            name = ctypes.create_unicode_buffer(261)
            fs = ctypes.create_unicode_buffer(261)
            ok = k32.GetVolumeInformationW(root, name, 261, None, None, None, fs, 261)
            return (name.value, fs.value) if ok else ("", "")
    out = []
    for ch in letters:
        root = f"{ch}:\\"
        t = kind_of(root)
        if t not in _WIN_TYPES or t in (5, 6):
            continue
        label, fstype = volume_info(root)
        used, free = usage(root)
        size = used + free
        if size <= 0:
            continue
        part = Part(name=f"{ch}:", path=root, size=size, fstype=fstype, label=label, mounts=[root], used=used, free=free)
        out.append(Disk(name=f"{ch}:", path=root, size=size, model=label, kind=_WIN_TYPES[t], parts=[part]))
    return out


def list_disks() -> list:
    if os.name == "nt":
        return list_disks_windows()
    try:
        r = subprocess.run(
            ["lsblk", "-J", "-b", "-o", LSBLK_COLS],
            capture_output=True, text=True, timeout=20,
            env=dict(os.environ, LC_ALL="C"),
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    return parse_lsblk(r.stdout)
