"""Podglad zawartosci pozycji przed usunieciem: zdjecie, tekst, wideo, audio, archiwum, PDF, folder.

Czysty Python (bez Qt): `info(path)` zwraca opis, a rysowanie robi widgets.PreviewWidget.
Czyta tylko poczatek pliku, nie podaza za dowiazaniami i nie pokazuje plikow wygladajacych na poufne.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unicodedata

from . import ai

IMAGE = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tif", "tiff", "ico", "ppm", "pgm"}
VIDEO = {"mp4", "mkv", "webm", "avi", "mov", "m4v", "flv", "wmv", "mpg", "mpeg", "ts"}
AUDIO = {"mp3", "flac", "ogg", "oga", "wav", "m4a", "opus", "aac", "wma"}
TEXT_MAX = 6000
DIR_MAX = 40


def _ext(path: str) -> str:
    name = os.path.basename(path)
    return name.rsplit(".", 1)[-1].lower() if "." in name.strip(".") else ""


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return str(n)


def is_secret(path: str) -> bool:
    full = unicodedata.normalize("NFKD", path).casefold()
    return any(h in os.path.basename(full) for h in ai.SECRET_HINTS) or any(d in full for d in ai.SECRET_DIRS)


def _open_regular(path: str):
    """(fd, stat) tylko dla zwyklego pliku; bez symlinkow i FIFO."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        raise OSError("nie jest zwyklym plikiem")
    return fd, st


def _run(cmd: list, timeout: int = 8) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def video_meta(path: str) -> str:
    if not shutil.which("ffprobe"):
        return ""
    out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                "stream=width,height,codec_name:format=duration", "-of", "default=nw=1", path])
    kv = dict(ln.split("=", 1) for ln in out.splitlines() if "=" in ln)
    parts = []
    if kv.get("width") and kv.get("height"):
        parts.append(f"{kv['width']}×{kv['height']}")
    if kv.get("codec_name"):
        parts.append(kv["codec_name"])
    try:
        sec = int(float(kv.get("duration", "")))
        parts.append(f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}")
    except ValueError:
        pass
    return "  ·  ".join(parts)


def video_thumb(path: str, outdir: str) -> str:
    """Klatka z wideo jako PNG (pusty tekst, gdy brak ffmpeg lub blad)."""
    if not shutil.which("ffmpeg"):
        return ""
    png = os.path.join(outdir, "thumb.png")
    for ss in ("00:00:03", "00:00:00"):
        _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", ss, "-i", path, "-frames:v", "1",
              "-vf", "scale=480:-2", png], 10)
        if os.path.isfile(png) and os.path.getsize(png) > 0:
            return png
    return ""


def new_tempdir() -> str:
    return tempfile.mkdtemp(prefix="fc-preview-")


def info(path: str) -> dict:
    """{'kind': image|video|audio|text|archive|pdf|dir|binary|secret|none, 'title', 'meta', 'text'}"""
    out = {"kind": "none", "title": os.path.basename(path.rstrip("/")) or path, "meta": "", "text": ""}
    try:
        st = os.lstat(path)
    except OSError:
        out["text"] = "Nie ma już tego pliku."
        return out
    if stat.S_ISLNK(st.st_mode):
        out["text"] = "To dowiązanie symboliczne - nie podglądam, dokąd prowadzi."
        return out
    if stat.S_ISDIR(st.st_mode):
        out["kind"] = "dir"
        try:
            with os.scandir(path) as it:
                rows = []
                for n, e in enumerate(it):
                    if n >= 400:
                        break
                    try:
                        s = e.stat(follow_symlinks=False)
                        rows.append((stat.S_ISDIR(s.st_mode), e.name, s.st_size))
                    except OSError:
                        rows.append((False, e.name, 0))
        except OSError:
            out["text"] = "Nie można odczytać folderu."
            return out
        rows.sort(key=lambda r: (not r[0], r[1].lower()))
        out["meta"] = f"{len(rows)}{'+' if len(rows) >= 400 else ''} pozycji w środku"
        out["text"] = "\n".join(("📁 " if d else "   ") + n + ("" if d else f"   ({_human(sz)})")
                                for d, n, sz in rows[:DIR_MAX]) + ("\n…" if len(rows) > DIR_MAX else "")
        return out
    if not stat.S_ISREG(st.st_mode):
        out["text"] = "To nie jest zwykły plik."
        return out
    out["meta"] = _human(st.st_size)
    if is_secret(path):
        out["kind"] = "secret"
        out["text"] = "Nazwa lub miejsce wskazuje na dane poufne - nie pokazuję zawartości."
        return out
    ext = _ext(path)
    if ext in IMAGE:
        out["kind"] = "image"
        return out
    if ext in VIDEO:
        out["kind"] = "video"
        vm = video_meta(path)
        out["meta"] += ("  ·  " + vm) if vm else ""
        return out
    if ext in AUDIO:
        out["kind"] = "audio"
        if shutil.which("ffprobe"):
            tags = _run(["ffprobe", "-v", "error", "-show_entries", "format_tags=title,artist,album:format=duration",
                         "-of", "default=nw=1", path])
            out["text"] = tags.strip()
        return out
    if ext == "pdf" and shutil.which("pdftotext"):
        txt = _run(["pdftotext", "-l", "1", "-q", path, "-"], 8)
        out["kind"] = "pdf"
        out["text"] = " ".join(txt.split())[:TEXT_MAX] or "PDF bez tekstu na pierwszej stronie."
        return out
    pk = ai.peek(path, st.st_size)
    if pk.get("w_archiwum"):
        out["kind"] = "archive"
        extra = pk.get("plikow_w_archiwum")
        out["meta"] += f"  ·  {extra} plików" if extra else ""
        out["text"] = "\n".join(pk["w_archiwum"]) + ("\n…" if (extra or 0) > len(pk["w_archiwum"]) else "")
        return out
    try:
        fd, _st = _open_regular(path)
        with os.fdopen(fd, "rb") as f:
            head = f.read(TEXT_MAX)
    except OSError:
        out["text"] = "Nie można odczytać pliku."
        return out
    if head and b"\x00" not in head[:2048]:
        out["kind"] = "text"
        out["text"] = head.decode("utf-8", "replace")
        if st.st_size > TEXT_MAX:
            out["text"] += "\n…"
        return out
    out["kind"] = "binary"
    out["text"] = (pk.get("typ") or "plik binarny") + (f"\n{pk['pakiet']}" if pk.get("pakiet") else "")
    return out
