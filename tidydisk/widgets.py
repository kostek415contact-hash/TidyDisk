"""Male widgety, style i watki w tle (PyQt6)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QImage, QImageReader, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from . import ai, core, history, osal, pipeline, preview, scanner, settings, simimg, spacelog, treemap
from .progress import ProgressTracker, fmt_eta, load_scanstats, save_scanstats
from .core import fmt_size

_REEXPORT = (ProgressTracker, fmt_eta, load_scanstats, save_scanstats)  # uzywane jako widgets.* (testy, gui)
from .viewmodel import rating_color, RATING_GLYPH

FRAC_ROLE = int(Qt.ItemDataRole.UserRole.value) + 1

# Kolory biora sie z palety systemowej, wiec styl pasuje do jasnego i ciemnego motywu.
QSS = """
#nav { border: none; background: palette(alternate-base); outline: 0; padding: 8px 6px; }
#nav::item { padding: 0 10px; border-radius: 9px; margin: 2px 6px; }
#nav::item:selected { background: palette(highlight); color: palette(highlighted-text); }
#pagetitle { font-size: 18pt; font-weight: 600; }
#subtitle, #muted { color: palette(placeholder-text); }
#bigtext { font-size: 16pt; font-weight: 600; }
#card { border: 1px solid rgba(128,128,128,70); border-radius: 12px; }
#footer { background: palette(alternate-base); border-radius: 12px; }
#details { border: 1px solid rgba(128,128,128,60); border-radius: 10px; padding: 8px 12px;
           background: palette(alternate-base); }
QProgressBar#meter { border: none; border-radius: 4px; background: rgba(128,128,128,60); }
QProgressBar#meter::chunk { border-radius: 4px; background: palette(highlight); }
QProgressBar#meter[level="warn"]::chunk { background: #e5a50a; }
QProgressBar#meter[level="crit"]::chunk { background: #d9453f; }
QProgressBar#busy { border: none; border-radius: 3px; background: rgba(128,128,128,60); }
QProgressBar#busy::chunk { border-radius: 3px; background: palette(highlight); }
QLabel#banner { border-radius: 10px; padding: 11px 16px; background: rgba(46,160,67,45); }
QLabel#banner[level="warn"] { background: rgba(240,170,20,55); }
QPushButton#primary {
    background: palette(highlight); color: palette(highlighted-text);
    border: none; border-radius: 9px; padding: 10px 18px; font-weight: 600; min-width: 190px;
}
QPushButton#primary:disabled { background: rgba(128,128,128,70); color: rgba(128,128,128,200); }
"""

SEGMENT_COLORS = ["#3584e4", "#2ec27e", "#e5a50a", "#c061cb", "#e66100", "#26a269", "#865e3c"]


def themed(names: list, fallback: QStyle.StandardPixmap) -> QIcon:
    for name in names:
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
    return QApplication.style().standardIcon(fallback)


def app_icon() -> QIcon:
    icon = QIcon.fromTheme("tidydisk")
    if not icon.isNull():
        return icon
    base = Path(__file__).resolve().parent
    for p in (
        base.parent / "data" / "icons" / "256x256" / "tidydisk.png",
        base.parent / "data" / "tidydisk.svg",
        base / "tidydisk.svg",
    ):
        if p.exists():
            return QIcon(str(p))
    return themed(["drive-harddisk"], QStyle.StandardPixmap.SP_DriveHDIcon)


class SizeBarDelegate(QStyledItemDelegate):
    """Rysuje w tle komorki rozmiaru pasek proporcjonalny do najwiekszej pozycji."""

    def paint(self, painter, option, index) -> None:  # noqa: N802
        frac = index.data(FRAC_ROLE)
        if frac:
            painter.save()
            color = option.palette.color(QPalette.ColorRole.Highlight)
            color.setAlpha(70)
            rect = option.rect.adjusted(6, 7, -6, -7)
            rect.setWidth(max(3, int(rect.width() * float(frac))))
            painter.fillRect(rect, color)
            painter.restore()
        super().paint(painter, option, index)


def set_level(widget, level: str) -> None:
    if widget.property("level") != level:
        widget.setProperty("level", level)
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)


class DiskMeter(QWidget):
    def __init__(self, mount: str) -> None:
        super().__init__()
        self.mount = mount
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.label = QLabel()
        self.label.setObjectName("muted")
        self.bar = QProgressBar()
        self.bar.setObjectName("meter")
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        self.bar.setFixedHeight(8)
        lay.addWidget(self.label)
        lay.addWidget(self.bar)
        self.setMinimumWidth(250)

    def set_usage(self, used: int, total: int) -> None:
        frac = used / total if total else 0.0
        self.bar.setValue(int(frac * 1000))
        set_level(self.bar, "crit" if frac >= 0.92 else "warn" if frac >= 0.8 else "ok")
        self.label.setText(
            f"Dysk {self.mount}  ·  wolne {fmt_size(total - used)} z {fmt_size(total)}"
        )


def usage_bar(used: int, total: int) -> QProgressBar:
    bar = QProgressBar()
    bar.setObjectName("meter")
    bar.setTextVisible(False)
    bar.setRange(0, 1000)
    bar.setFixedHeight(8)
    frac = used / total if total else 0.0
    bar.setValue(int(frac * 1000))
    set_level(bar, "crit" if frac >= 0.92 else "warn" if frac >= 0.8 else "ok")
    return bar


class RingWidget(QWidget):
    """Pierscien: jaka czesc znalezionych pozycji zaznaczono do usuniecia (w srodku tekst)."""

    def __init__(self, size: int = 64) -> None:
        super().__init__()
        self.frac = 0.0
        self.text = ""
        self.setFixedSize(size, size)

    def set_value(self, frac: float, text: str = "") -> None:
        self.frac = max(0.0, min(1.0, frac))
        self.text = text
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pad = 6
        r = QRectF(pad, pad, self.width() - 2 * pad, self.height() - 2 * pad)
        pal = self.palette()
        track = QPen(pal.color(QPalette.ColorRole.Mid), 6)
        p.setPen(track)
        p.drawEllipse(r)
        if self.frac > 0:
            arc = QPen(pal.color(QPalette.ColorRole.Highlight), 6)
            arc.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(arc)
            p.drawArc(r, 90 * 16, -int(self.frac * 360 * 16))
        p.setPen(pal.color(QPalette.ColorRole.WindowText))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()


class SegmentBar(QWidget):
    """Pasek calego dysku podzielony na partycje (proporcjonalnie do rozmiaru)."""

    def __init__(self, parts: list) -> None:
        super().__init__()
        self.parts = parts  # [(nazwa, rozmiar)]
        self.setFixedHeight(26)
        self.setMinimumWidth(200)

    def paintEvent(self, _ev) -> None:  # noqa: N802
        total = sum(max(s, 1) for _n, s in self.parts) or 1
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        w, h = self.width(), self.height()
        x = 0.0
        gap = 2.0
        for i, (_name, size) in enumerate(self.parts):
            seg = max(size, 1) / total * w
            color = QColor(SEGMENT_COLORS[i % len(SEGMENT_COLORS)])
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, 0, max(seg - gap, 3), h), 6, 6)
            x += seg
        p.end()


# ------------------------------------------------------------------ watki --

class ScanWorker(QThread):
    """Szuka rzeczy do sprzatania (cache, kosz, flatpak, pakiety ...)."""
    status = pyqtSignal(str)
    done = pyqtSignal(list)

    def run(self) -> None:
        try:
            cats = core.scan(self.status.emit)
        except Exception as ex:  # noqa: BLE001
            self.status.emit(f"Błąd skanowania: {ex}")
            cats = []
        self.done.emit(cats)


class DiskScanWorker(QThread):
    """Przeszukuje wszystkie pliki: jako uzytkownik (dom) albo administrator (caly system)."""
    progress = pyqtSignal(int)
    done = pyqtSignal(object)  # ScanResult albo None
    failed = pyqtSignal(str)

    def __init__(self, admin: bool, root: str = "") -> None:
        super().__init__()
        self.admin = admin
        self.root = root or str(core.HOME)
        self._cancel = False
        self._proc = None

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            if self.admin:
                self._run_admin()
            else:
                res = scanner.scan(
                    self.root, core.KB,
                    progress=lambda n, _t, _p: self.progress.emit(n),
                    cancel=lambda: self._cancel,
                    advise=False,
                )
                self.done.emit(res)
        except Exception as ex:  # noqa: BLE001
            self.failed.emit(f"Błąd skanowania: {ex}")

    def _run_admin(self) -> None:
        from . import __version__
        script, ok, why = scanner.find_admin_script(__version__)
        if not ok:
            self.failed.emit(f"Skan systemu wymaga zainstalowanego skanera administratora: {why}. "
                             "Uruchom w katalogu programu: ./install.sh --admin")
            return
        try:
            proc = subprocess.Popen(
                ["pkexec", script, "/", str(core.HOME),
                 json.dumps(list(core.KB.data_mounts))],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            )
        except FileNotFoundError:
            self.failed.emit("Brak polecenia pkexec (pakiet polkit).")
            return
        result = None
        assert proc.stdout is not None
        for line in proc.stdout:
            parsed = scanner.parse_admin_line(line)
            if parsed is None:
                continue
            if parsed[0] == "P":
                self.progress.emit(parsed[1])
            else:
                result = parsed[1]
        code = proc.wait()
        if result is not None:
            self.done.emit(result)
        elif code in (126, 127):
            self.failed.emit("Anulowano lub brak autoryzacji - skanowanie systemu nie ruszyło.")
        else:
            self.failed.emit(f"Skaner administratora zakończył się kodem {code}.")


class AnalysisWorker(QThread):
    """Analiza wszystkich plikow (dom + dyski danych): algorytm proponuje, co usunac."""
    progress = pyqtSignal(int)
    stage = pyqtSignal(str)  # opis biezacego etapu: numer, miejsce, postep
    fraction = pyqtSignal(float)  # ogolny postep 0..1 albo -1 gdy nieznany
    done = pyqtSignal(object)  # ScanResult (polaczony) albo None
    failed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            cfg = settings.apply(settings.load())

            def report(n, t, path, ri, nroots, root, b, names, st, txt, frac):
                self.progress.emit(b + n)
                self.stage.emit(f"Etap {st + 1}/{len(names)}: {names[st]} - miejsce {ri} z {nroots}: {root} - {txt}")
                self.fraction.emit(frac)

            res = pipeline.scan_all(cfg, cancel=lambda: self._cancel, report=report,
                                    on_merge=lambda: (self.fraction.emit(0.99),
                                                      self.stage.emit("Ostatni etap: scalam wyniki ze wszystkich dysków i układam listę …")))
            self.done.emit(res)
        except Exception as ex:  # noqa: BLE001
            self.failed.emit(f"Błąd analizy: {ex}")


AI_MISSING = ("Nie znalazłem lokalnego serwera modelu (sprawdziłem porty 8888, 8080, 11434, 1234, 8000). "
              "Uruchom Unsloth Studio z modelem (`unsloth run --model …`) albo llama-server i ustaw adres oraz "
              "klucz w Ustawienia → AI.")


class AITriageWorker(QThread):
    """Lejek AI: reguly -> statystyki -> AI foldery -> AI pliki -> AI weryfikacja. Tylko metadane."""
    batch = pyqtSignal(object, object, int, int)  # wyniki {sciezka: (werdykt, ryzyko, dlaczego)}, meta, zrobione, razem
    status = pyqtSignal(str)
    fraction = pyqtSignal(float)  # ogolny postep oceny AI 0..1
    finished_ok = pyqtSignal(object)  # statystyki etapow
    failed = pyqtSignal(str)

    def __init__(self, advice: list, nodes: dict, top_files: list, skip=()) -> None:
        super().__init__()
        self.advice, self.nodes, self.top_files, self.skip = advice, nodes, top_files, set(skip)
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            host, models = ai.detect()
            if host is None:
                self.failed.emit(AI_MISSING)
                return
            if not models:
                self.failed.emit(f"Serwer {host} odpowiada, ale nie zgłasza żadnego modelu.")
                return
            model = ai.pick_model(models)
            self.status.emit(f"Model: {model}")
            cfg = settings.apply(settings.load())
            stats = ai.cascade(
                model, self.advice, self.nodes, self.top_files, host, str(core.HOME),
                roots=[r for r, _d in core.cleanup_roots()], skip=self.skip,
                on_batch=lambda r, m, d, t: self.batch.emit(r, m, d, t),
                on_status=self.status.emit, cancel=lambda: self._cancel,
                on_progress=lambda d, t: self.fraction.emit(d / t if t else 0.0), cfg=cfg)
            self.finished_ok.emit(stats)
        except PermissionError as ex:
            self.failed.emit(f"Serwer AI odrzucił dostęp: {ex}")
        except Exception as ex:  # noqa: BLE001
            self.failed.emit("Przegląd AI przerwany: " + ai.friendly_error(str(ex)))


class AITestWorker(QThread):
    """Sprawdza polaczenie z lokalnym serwerem AI (adres i klucz z zapisanych ustawien)."""
    ok = pyqtSignal(str, object)  # adres, lista modeli
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            host, models = ai.detect()
            if host is None:
                self.failed.emit(AI_MISSING)
            else:
                self.ok.emit(host, list(models or []))
        except PermissionError as ex:
            self.failed.emit(f"Serwer AI odrzucił dostęp - sprawdź klucz API ({ex}).")
        except Exception as ex:  # noqa: BLE001
            self.failed.emit("Test połączenia nie powiódł się: " + ai.friendly_error(str(ex)))


class AIWorker(QThread):
    """Pytanie do lokalnego modelu (API zgodne z OpenAI). Tylko metadane, odpowiedz to podpowiedz."""
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, entry) -> None:
        super().__init__()
        self.entry = entry

    def run(self) -> None:
        try:
            host, models = ai.detect()
            if host is None:
                self.failed.emit(AI_MISSING)
                return
            if not models:
                self.failed.emit(f"Serwer {host} odpowiada, ale nie zgłasza żadnego modelu.")
                return
            e = self.entry
            meta = ai.describe(e.paths[0], e.size, e.rating, e.reasons or [e.why])
            self.done.emit(ai.format_answer(ai.ask(ai.pick_model(models), meta, host, float(settings.load()["ai_timeout_s"]))))
        except Exception as ex:  # noqa: BLE001
            self.failed.emit("Asystent AI nie odpowiedział: " + ai.friendly_error(str(ex)))


class CleanWorker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(object)

    def __init__(self, entries: list, dry: bool) -> None:
        super().__init__()
        self.entries = entries
        self.dry = dry

    def run(self) -> None:
        try:
            journal: list = []
            res = core.run_clean(self.entries, self.dry, self.log.emit, journal)
            if not self.dry:
                history.record(journal, res.freed, res.trashed)
        except Exception as ex:  # noqa: BLE001
            self.log.emit(f"! Nieoczekiwany błąd: {ex}")
            res = core.CleanResult(0, 1)
        self.done.emit(res)



def is_dark_palette(widget=None) -> bool:
    """Czy aktualna paleta (motyw) jest ciemna - do wyboru wariantu kolorow ocen."""
    try:
        pal = widget.palette() if widget is not None else QApplication.palette()
        return bool(pal.color(QPalette.ColorRole.Window).lightness() < 128)
    except Exception:  # noqa: BLE001
        return True


TILE_COLORS = {r: rating_color(r, True) for r in ("safe", "review", "mine", "keep")}  # zgodnosc; rysowanie uzywa rating_color


class TreemapWidget(QWidget):
    """Mapa dysku: kafle proporcjonalne do rozmiaru, kolor = ocena. Klik = wejscie w folder."""
    clicked = pyqtSignal(str)
    hovered = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.items: list = []  # [(sciezka, rozmiar, ocena, tytul)]
        self.ai_paths: set = set()
        self.rects: list = []
        self.setMouseTracking(True)
        self.setMinimumHeight(260)

    def set_items(self, items: list, ai_paths=()) -> None:
        self.items = list(items)
        self.ai_paths = set(ai_paths)
        self._layout()
        self.update()

    def _layout(self) -> None:
        self.rects = treemap.squarify([it[1] for it in self.items], 0, 0, max(self.width(), 1), max(self.height(), 1))

    def resizeEvent(self, ev) -> None:  # noqa: N802
        self._layout()
        super().resizeEvent(ev)

    def _hit(self, pos) -> int:
        for i, (x, y, w, h) in enumerate(self.rects):
            if w > 0 and x <= pos.x() <= x + w and y <= pos.y() <= y + h:
                return i
        return -1

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        i = self._hit(ev.position())
        if i >= 0:
            path, size, _r, title = self.items[i]
            self.hovered.emit(f"{title or path}  ·  {fmt_size(size)}")
        super().mouseMoveEvent(ev)

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        i = self._hit(ev.position())
        if i >= 0 and self.items[i][0]:
            self.clicked.emit(self.items[i][0])
        super().mousePressEvent(ev)

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = is_dark_palette(self)
        txt = self.palette().color(QPalette.ColorRole.WindowText)
        sub_txt = self.palette().color(QPalette.ColorRole.PlaceholderText)
        for (path, size, rating, title), (x, y, w, h) in zip(self.items, self.rects):
            if w < 2 or h < 2:
                continue
            col = QColor(rating_color(rating, dark))
            fill = QColor(col)
            fill.setAlpha(60)
            r = QRectF(x + 2, y + 2, w - 4, h - 4)
            p.setPen(col)
            p.setBrush(fill)
            p.drawRoundedRect(r, 8, 8)
            if w > 70 and h > 34:
                p.setPen(txt)
                f = p.font()
                f.setBold(True)
                p.setFont(f)
                p.drawText(r.adjusted(9, 7, -9, -7), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                           RATING_GLYPH.get(rating, "•") + " " + (title or path.rsplit("/", 1)[-1]) + ("  🤖" if path in self.ai_paths else ""))
                f.setBold(False)
                p.setFont(f)
                p.setPen(sub_txt)
                p.drawText(r.adjusted(9, 26, -9, -7), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, fmt_size(size))
        p.end()


_THUMBS: set = set()  # dzialajace watki miniatur: trzymamy referencje, zeby GC nie zniszczyl dzialajacego QThread (abort procesu)


class ThumbWorker(QThread):
    """Klatka z wideo w tle (ffmpeg), zeby okno nie zamarzalo."""
    ready = pyqtSignal(str, str)  # sciezka pliku, sciezka PNG ('' = brak)

    def __init__(self, path: str, outdir: str) -> None:
        super().__init__()
        self.path, self.outdir = path, outdir

    def run(self) -> None:
        try:
            self.ready.emit(self.path, preview.video_thumb(self.path, self.outdir))
        except Exception:  # noqa: BLE001 - podglad nigdy nie przerywa pracy
            self.ready.emit(self.path, "")


class PreviewWidget(QWidget):
    """Podglad zawartosci: zdjecie, klatka z wideo, tekst, lista z archiwum albo folderu."""

    def __init__(self, height: int = 200) -> None:
        super().__init__()
        self._h = height
        self._path = ""
        self._tmp = ""
        self._worker = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.head = QLabel("")
        self.head.setObjectName("muted")
        self.head.setWordWrap(True)
        self.image = QLabel("")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumHeight(0)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumHeight(height)
        lay.addWidget(self.head)
        lay.addWidget(self.image)
        lay.addWidget(self.text)
        self.clear()

    def clear(self) -> None:
        self._path = ""
        self.head.setText("")
        self.image.clear()
        self.image.hide()
        self.text.setPlainText("")
        self.text.hide()

    def _pixmap(self, path: str, maxw: int = 440):
        rd = QImageReader(path)
        rd.setAutoTransform(True)
        sz = rd.size()
        if not sz.isValid() or sz.width() <= 0 or sz.height() <= 0:
            return None, ""
        k = min(maxw / sz.width(), self._h / sz.height(), 1.0)
        rd.setScaledSize(sz * k)  # dekoduje od razu w malym rozmiarze - duze zdjecia nie zjadaja pamieci
        img = rd.read()
        meta = f"{sz.width()}×{sz.height()} px"
        return (QPixmap.fromImage(img) if not img.isNull() else None), meta

    def show_path(self, path: str) -> None:
        self.clear()
        if not path:
            return
        self._path = path
        d = preview.info(path)
        self.head.setText(d["meta"])
        kind = d["kind"]
        if kind == "image":
            pm, meta = self._pixmap(path)
            if pm is not None:
                self.image.setPixmap(pm)
                self.image.show()
                self.head.setText(d["meta"] + "  ·  " + meta)
            else:
                self.text.setPlainText("Nie udało się wczytać obrazu.")
                self.text.show()
        elif kind == "video":
            self.text.setPlainText("Wczytuję klatkę z filmu …")
            self.text.show()
            self._tmp = self._tmp or preview.new_tempdir()
            import tempfile
            w = ThumbWorker(path, tempfile.mkdtemp(dir=self._tmp))  # osobny katalog na watek: starszy nie nadpisze miniatury nowszego
            w.ready.connect(self._thumb_ready)
            _THUMBS.add(w)
            w.finished.connect(lambda w=w: _THUMBS.discard(w))
            self._worker = w
            w.start()
        elif d["text"]:
            self.text.setPlainText(d["text"])
            self.text.show()

    def _thumb_ready(self, path: str, png: str) -> None:
        if path != self._path:  # uzytkownik zdazyl wybrac inna pozycje
            return
        pm = self._pixmap(png)[0] if png else None
        if pm is not None:
            self.text.hide()
            self.image.setPixmap(pm)
            self.image.show()
        else:
            self.text.setPlainText("Film - brak ffmpeg albo nie da się odczytać klatki.")

    def cleanup(self) -> None:
        import shutil
        if self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = ""


class SpaceChart(QWidget):
    """Wykres zajetego miejsca w czasie (pierwszy dysk z historii)."""

    def __init__(self) -> None:
        super().__init__()
        self.points: list = []
        self.setMinimumHeight(130)

    def set_points(self, points: list) -> None:
        self.points = spacelog.series(points)
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        r = QRectF(8, 8, self.width() - 16, self.height() - 28)
        p.setPen(QPen(pal.color(QPalette.ColorRole.Mid), 1))
        p.drawRect(r)
        s = self.points
        if len(s) < 2:
            p.setPen(pal.color(QPalette.ColorRole.WindowText))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Wykres pojawi się po kilku skanach.")
            p.end()
            return
        x0, x1 = s[0][0], s[-1][0]
        y0, y1 = min(v for _t, v in s), max(v for _t, v in s)
        dx, dy = max(x1 - x0, 1), max(y1 - y0, 1)
        pts = [(r.left() + (t - x0) / dx * r.width(), r.bottom() - (v - y0) / dy * r.height()) for t, v in s]
        p.setPen(QPen(pal.color(QPalette.ColorRole.Highlight), 2))
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            p.drawLine(int(ax), int(ay), int(bx), int(by))
        p.setPen(pal.color(QPalette.ColorRole.WindowText))
        p.drawText(8, self.height() - 6, f"zajęte: {fmt_size(y0)} → {fmt_size(y1)}")
        p.end()


def gray9x8(path: str):
    """(72 wartosci szarosci, szerokosc, wysokosc) albo None. Dekoduje od razu w malym rozmiarze."""
    rd = QImageReader(path)
    rd.setAutoTransform(True)
    sz = rd.size()
    if not sz.isValid() or sz.width() < 16 or sz.height() < 16:
        return None
    rd.setScaledSize(QSize(9, 8))
    img = rd.read()
    if img.isNull():
        return None
    img = img.convertToFormat(QImage.Format.Format_Grayscale8)
    vals = [img.pixelColor(x, y).red() for y in range(8) for x in range(9)]
    return vals, sz.width(), sz.height()


class PhotoWorker(QThread):
    """Szuka podobnych zdjec w folderach: dHash (z pamiecia miedzy skanami) + grupowanie."""
    progress = pyqtSignal(int, int)
    done = pyqtSignal(object)  # lista grup: [[(sciezka, szer, wys, rozmiar, mtime), ...], ...]
    failed = pyqtSignal(str)

    MIN_BYTES = 20 * 1024

    def __init__(self, folders: list, max_dist: int = 3) -> None:
        super().__init__()
        self.folders, self.max_dist = folders, max_dist
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def _files(self) -> list:
        import os
        out = []
        for base in self.folders:
            for dirpath, dirs, names in os.walk(base):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for n in names:
                    if preview._ext(n) in preview.IMAGE:
                        p = os.path.join(dirpath, n)
                        try:
                            st = os.lstat(p)
                        except OSError:
                            continue
                        if st.st_size >= self.MIN_BYTES and not core.is_protected(p) and not os.path.islink(p):
                            out.append((p, st.st_size, st.st_mtime))
        return out

    def run(self) -> None:
        try:
            files = self._files()
            cache_path = str(osal.data_dir() / "photohash.json")
            cache = simimg.load_cache(cache_path)
            keep: set = set()
            info: dict = {}
            items = []
            for i, (p, size, mt) in enumerate(files):
                if self._cancel:
                    return
                if i % 25 == 0:
                    self.progress.emit(i, len(files))
                key = f"{p}|{size}|{int(mt)}"
                keep.add(key)
                if key in cache:
                    h, wd, ht = cache[key]
                else:
                    g = gray9x8(p)
                    if g is None:
                        continue
                    h, wd, ht = simimg.dhash(g[0]), g[1], g[2]
                    cache[key] = [h, wd, ht]
                info[p] = (p, wd, ht, size, mt)
                items.append((p, h))
            simimg.save_cache(cache_path, cache, keep)
            groups = [[info[k] for k in g] for g in simimg.group(items, self.max_dist)]
            groups.sort(key=lambda g: -sum(x[3] for x in g))
            self.done.emit(groups)
        except Exception as ex:  # noqa: BLE001
            self.failed.emit(f"Błąd szukania zdjęć: {ex}")
