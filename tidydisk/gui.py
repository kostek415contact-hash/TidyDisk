"""Okno TidyDisk (PyQt6): dyski, foldery, pliki, sprzatanie."""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QDesktopServices, QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QTabBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__, ai, background, openfiles, osal, changes, i18n, core, disks, export, history, kb, learn, report, rules, schedule, settings, snapshots, spacelog, theme, treemap, viewmodel
from .core import fmt_size
from .settings_page import SettingsPage
from .viewmodel import plural, rating_color, rating_legend_html, rating_text
from .widgets import (
    _THUMBS,
    FRAC_ROLE,
    ProgressTracker,
    QSS,
    SEGMENT_COLORS,
    CleanWorker,
    DiskMeter,
    AITriageWorker,
    AIWorker,
    AnalysisWorker,
    DiskScanWorker,
    ScanWorker,
    PhotoWorker,
    PreviewWidget,
    RingWidget,
    SpaceChart,
    TreemapWidget,
    SegmentBar,
    is_dark_palette,
    SizeBarDelegate,
    app_icon,
    themed,
    usage_bar,
)

ENTRY_ROLE = Qt.ItemDataRole.UserRole
PATH_ROLE = int(Qt.ItemDataRole.UserRole.value) + 2
SORT_ROLE = int(Qt.ItemDataRole.UserRole.value) + 4  # klucz sortowania kolumny (rozmiar jako liczba, nazwa bez wielkosci liter)
SECTION_ROLE = int(Qt.ItemDataRole.UserRole.value) + 3
PAGE_DISKS, PAGE_FOLDERS, PAGE_FILES, PAGE_MAP, PAGE_CLEAN, PAGE_PHOTOS, PAGE_HISTORY, PAGE_SETTINGS = 0, 1, 2, 3, 4, 5, 6, 7
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

CATEGORY_ICONS = {
    "cache": (["folder-temp", "edit-clear-history", "folder"], QStyle.StandardPixmap.SP_DirIcon),
    "trash": (["user-trash"], QStyle.StandardPixmap.SP_TrashIcon),
    "flatpak": (["flatpak-discover", "package-x-generic", "folder"], QStyle.StandardPixmap.SP_DirIcon),
    "system": (["preferences-system", "computer"], QStyle.StandardPixmap.SP_ComputerIcon),
    "kernel": (["cpu", "applications-system", "computer"], QStyle.StandardPixmap.SP_ComputerIcon),
    "packages": (["package-x-generic", "system-software-install"], QStyle.StandardPixmap.SP_DirIcon),
}


def rating_item_text(rating: str) -> str:
    return rating_text(rating)  # glif + tekst: ocena czytelna bez koloru


def paint_rating(item: QTreeWidgetItem, col: int, rating: str) -> None:
    item.setText(col, rating_item_text(rating))
    item.setForeground(col, QBrush(QColor(rating_color(rating, is_dark_palette()))))


class SortItem(QTreeWidgetItem):
    """Wiersz sortowany po kluczu z SORT_ROLE (rozmiar liczbowo, nazwa bez wielkosci liter), a nie po wyswietlanym tekscie."""

    def __lt__(self, other) -> bool:
        tree = self.treeWidget()
        col = tree.sortColumn() if tree is not None else 0
        a, b = self.data(col, SORT_ROLE), other.data(col, SORT_ROLE)
        if a is None or b is None:
            a, b = self.text(col).casefold(), other.text(col).casefold()
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)


def set_sort_keys(item, *keys) -> None:
    for col, k in enumerate(keys):
        if k is not None:
            item.setData(col, SORT_ROLE, k)


def make_tree(headers: list, widths: list) -> QTreeWidget:
    tree = QTreeWidget()
    tree.setFrameShape(QFrame.Shape.NoFrame)
    tree.setColumnCount(len(headers))
    tree.setHeaderLabels(headers)
    tree.setUniformRowHeights(True)
    tree.setIndentation(20)
    tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    tree.setIconSize(QSize(20, 20))
    hdr = tree.header()
    hdr.setStretchLastSection(True)
    for i, w in enumerate(widths):
        hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        tree.setColumnWidth(i, w)
    return tree


def card_around(widget: QWidget) -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(3, 3, 3, 3)
    lay.addWidget(widget)
    return card


def open_in_file_manager(path: str) -> None:
    p = path if os.path.isdir(path) else os.path.dirname(path)
    QDesktopServices.openUrl(QUrl.fromLocalFile(p))


def page_header(title: str, subtitle: str) -> QVBoxLayout:
    box = QVBoxLayout()
    box.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("pagetitle")
    s = QLabel(subtitle)
    s.setObjectName("subtitle")
    s.setWordWrap(True)
    box.addWidget(t)
    box.addWidget(s)
    return box


def details_label() -> QLabel:
    lab = QLabel("Wybierz pozycję, żeby zobaczyć, co to jest i dlaczego tak ją oceniam.")
    lab.setObjectName("details")
    lab.setWordWrap(True)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lab.setMinimumHeight(74)
    return lab


def empty_state(text: str) -> QWidget:
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.addStretch(1)
    lab = QLabel(text)
    lab.setObjectName("muted")
    lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lab.setWordWrap(True)
    lay.addWidget(lab)
    lay.addStretch(1)
    return page


# ---------------------------------------------------------- strona: dyski --

SEARCH_MODE_LABELS = (("Niedokładny (tylko algorytm)", "algorithm"), ("Dokładny (algorytm + AI)", "assisted"),
                      ("Bardzo dokładny (tylko AI)", "ai_only"))

GROUPS = (
    ("Wszystkie rodzaje", None),
    ("Duplikaty", {"duplicates"}),
    ("Instalatory i obrazy ISO", {"installers", "iso"}),
    ("Starsze wersje i kopie", {"versions"}),
    ("Foldery do odtworzenia", {"builddirs", "cache"}),
    ("Stare pliki", {"old_review", "archives", "logs", "tempbak", "partial", "coredumps", "extracted", "video"}),
)


def entry_groups(e) -> set:
    """Do ktorych rodzajow z GROUPS nalezy pozycja (te same kategorie co reguly w Ustawieniach)."""
    if not getattr(e, "paths", None):
        return set()
    p = e.paths[0]
    kind = "dir" if os.path.isdir(p) and not os.path.islink(p) else "file"
    return rules.categories(p, e.reasons, e.rating, kind)


class DisksPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addLayout(page_header(
            "Dyski i partycje",
            "Fizyczne dyski, ich partycje i zajęte miejsce. Kolory paska odpowiadają partycjom poniżej."))
        self.snap = QLabel(snapshots.detect()["text"])
        self.snap.setObjectName("muted")
        self.snap.setWordWrap(True)
        self.snap.setVisible(bool(self.snap.text()))
        lay.addWidget(self.snap)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        lay.addWidget(self.scroll, 1)
        self.refresh()

    def refresh(self) -> None:
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(14)
        found = disks.list_disks()
        if not found:
            col.addWidget(empty_state("Nie udało się odczytać listy dysków (polecenie lsblk)."))
        for d in found:
            col.addWidget(self._disk_card(d))
        col.addStretch(1)
        self.scroll.setWidget(inner)

    def _disk_card(self, d) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        head = QHBoxLayout()
        name = QLabel(f"{d.name}  ·  {d.model}" if d.model else d.name)
        name.setObjectName("bigtext")
        kind = QLabel(f"{d.kind}  ·  {fmt_size(d.size)}")
        kind.setObjectName("muted")
        head.addWidget(name)
        head.addStretch(1)
        head.addWidget(kind)
        lay.addLayout(head)
        used = tot = 0
        shared: dict = {}
        for p in d.parts:
            if not (p.mount and p.size):
                continue
            if p.group <= 1 or not p.uuid or not p.volume_size:
                used += p.used
                tot += p.used + p.free
            else:  # jeden system plikow na kilku partycjach: liczymy raz, proporcjonalnie do udzialu na tym dysku
                g = shared.setdefault(p.uuid, [p, 0])
                g[1] += p.size
        for p, mine in shared.values():
            share = min(mine / p.volume_size, 1.0)
            used += int(p.used * share)
            tot += int((p.used + p.free) * share)
        if tot:  # pasek zajetosci calego dysku (suma zamontowanych systemow plikow)
            row0 = QHBoxLayout()
            row0.addWidget(usage_bar(used, tot), 1)
            lbl = QLabel(f"zajęte {fmt_size(used)} z {fmt_size(tot)}  ·  wolne {fmt_size(tot - used)}")
            lbl.setObjectName("muted")
            row0.addWidget(lbl)
            lay.addLayout(row0)
        if d.parts:
            lay.addWidget(SegmentBar([(p.name, p.size) for p in d.parts]))
        for i, p in enumerate(d.parts):
            row = QHBoxLayout()
            row.setSpacing(12)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {SEGMENT_COLORS[i % len(SEGMENT_COLORS)]};")
            title = QLabel(" ".join(x for x in (p.name, p.label) if x))
            title.setMinimumWidth(170)
            fs = QLabel((p.fstype or "—") + (f" ×{p.group}" if p.group > 1 else ""))
            fs.setToolTip(f"Jeden system plików rozłożony na {p.group} partycjach "
                          f"(razem {fmt_size(p.volume_size)}) - zajętość dotyczy całości."
                          if p.group > 1 else "")
            fs.setObjectName("muted")
            fs.setMinimumWidth(70)
            mnt = QLabel(p.mount or "niezamontowana")
            mnt.setObjectName("muted")
            mnt.setMinimumWidth(130)
            row.addWidget(dot)
            row.addWidget(title)
            row.addWidget(fs)
            row.addWidget(mnt)
            if p.mount and p.size:
                row.addWidget(usage_bar(p.used, p.used + p.free), 1)
                use = QLabel(f"{fmt_size(p.used)} z {fmt_size(p.used + p.free)}")
            else:
                row.addStretch(1)
                use = QLabel(fmt_size(p.size))
            use.setObjectName("muted")
            use.setMinimumWidth(130)
            use.setAlignment(RIGHT)
            row.addWidget(use)
            lay.addLayout(row)
        return card


# -------------------------------------------------------- strona: foldery --

class FoldersPage(QWidget):
    """Przegladarka wszystkich plikow na zywo; rozmiary katalogow ze skanu (jesli jest)."""

    def __init__(self) -> None:
        super().__init__()
        self.scan = None
        self.sizes: dict = {}
        self.root = str(core.HOME)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addLayout(page_header(
            "Foldery i pliki",
            "Wszystkie pliki i foldery wybranego miejsca - rozwijaj foldery. Przy każdej pozycji "
            "ocena i wyjaśnienie. Program tylko pokazuje; Twoich plików nie usuwa."))
        self.where = QLabel("")
        self.where.setObjectName("muted")
        lay.addWidget(self.where)
        self.tree = make_tree(["Nazwa", "Rozmiar", "Zmieniony", "Ocena", "Co to jest"],
                              [400, 120, 100, 140, 260])
        self.tree.setItemDelegateForColumn(1, SizeBarDelegate(self.tree))
        self.tree.itemExpanded.connect(self.on_expand)
        self.tree.currentItemChanged.connect(self.on_select)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_menu)
        lay.addWidget(card_around(self.tree), 1)
        self.details = details_label()
        lay.addWidget(self.details)
        self.refresh()

    def set_root(self, path: str) -> None:
        self.root = path
        self.refresh()

    def set_scan(self, scan) -> None:
        """Wynik skanu: znane rozmiary katalogow (reszta liczona na biezaco)."""
        self.scan = scan
        self.sizes = {p: n[0] for p, n in scan.nodes.items()}
        self.refresh()

    def refresh(self) -> None:
        self.tree.clear()
        self.where.setText(f"Miejsce: {viewmodel.short_path(self.root)}"
                           + ("" if self.scan else "  ·  rozmiary folderów: przybliżone, uruchom „Skanuj” po dokładne"))
        self._fill(self.tree.invisibleRootItem(), self.root)

    def _fill(self, parent, path: str) -> None:
        items, extra, err = core.list_folder(path, self.sizes)
        if err:
            QTreeWidgetItem(parent, [f"(brak dostępu: {err})"])
            return
        if not items:
            QTreeWidgetItem(parent, ["(pusty folder)"])
            return
        biggest = max((i.size for i in items), default=0)
        for i in items:
            size_txt = ("≥ " if not i.exact else "") + fmt_size(i.size) if i.size >= 0 else "—"
            it = QTreeWidgetItem(parent, [("📁 " if i.is_dir else "") + i.name, size_txt,
                                          viewmodel.date_text(i.mtime), "", i.verdict.title])
            it.setData(0, PATH_ROLE, i.path)
            it.setData(1, FRAC_ROLE, (i.size / biggest) if biggest > 0 and i.size > 0 else None)
            it.setTextAlignment(1, RIGHT)
            it.setToolTip(0, i.path)
            paint_rating(it, 3, i.verdict.rating)
            if i.is_dir:
                QTreeWidgetItem(it, ["…"])  # znacznik: zawartosc wczytamy przy rozwinieciu
        if extra:
            QTreeWidgetItem(parent, [f"… i {extra} więcej (najmniejszych)"])

    def on_expand(self, item) -> None:
        if item.childCount() != 1 or item.child(0).text(0) != "…":
            return
        item.takeChild(0)
        self._fill(item, item.data(0, PATH_ROLE))

    def on_select(self, item, _prev) -> None:
        if item is None:
            return
        path = item.data(0, PATH_ROLE)
        if not path:
            return
        v = core.KB.classify(path) if os.path.isdir(path) else core.KB.classify_file(path)
        self.details.setText(
            f"{viewmodel.short_path(path)}\nCo to jest: {v.title} - {v.what}\n"
            f"Dlaczego {kb.RATING_LABEL[v.rating].lower()}: {v.why}")

    def show_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None or not item.data(0, PATH_ROLE):
            return
        menu = QMenu(self)
        act = menu.addAction(i18n.tr("Otwórz w menedżerze plików"))
        if menu.exec(self.tree.viewport().mapToGlobal(pos)) == act:
            open_in_file_manager(item.data(0, PATH_ROLE))


# ---------------------------------------------------------- strona: pliki --

class FilesPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.scan = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addLayout(page_header(
            "Pliki",
            "Największe pliki z całego skanu (od 256 KB), z wyjaśnieniem. Wszystkie pliki "
            "danego folderu zobaczysz w zakładce „Foldery i pliki”."))
        self.summary = QLabel("")
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)

        row = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.addItem("Wszystkie oceny", None)
        for r in kb.RATINGS:
            self.combo.addItem(kb.RATING_LABEL[r], r)
        self.combo.currentIndexChanged.connect(self.refill)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Szukaj w nazwie lub typie …")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(280)
        self.search.textChanged.connect(self.refill)
        row.addWidget(self.combo)
        row.addWidget(self.search)
        row.addStretch(1)
        lay.addLayout(row)

        self.stack = QStackedWidget()
        self.stack.addWidget(empty_state("Najpierw przeskanuj dysk - przyciski są nad listą."))
        self.tree = make_tree(["Plik", "Rozmiar", "Zmieniony", "Ocena", "Co to jest"],
                              [330, 100, 100, 140, 220])
        self.tree.setRootIsDecorated(False)
        self.tree.currentItemChanged.connect(self.on_select)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_menu)
        self.stack.addWidget(card_around(self.tree))
        lay.addWidget(self.stack, 1)
        self.details = details_label()
        lay.addWidget(self.details)

    def set_scan(self, scan) -> None:
        self.scan = scan
        types = " · ".join(f"{n} {fmt_size(b)}" for n, b, _c, _f in viewmodel.type_rows(scan)[:7])
        ratings = " · ".join(f"{kb.RATING_LABEL[r]} {fmt_size(b)}"
                             for r, b, _f in viewmodel.rating_rows(scan))
        self.summary.setText(f"Wg typu: {types}\nWg oceny: {ratings}")
        self.stack.setCurrentIndex(1)
        self.refill()

    def refill(self, *_a) -> None:
        if self.scan is None:
            return
        self.tree.clear()
        rating = self.combo.currentData()
        for r in viewmodel.file_rows(self.scan, rating, self.search.text()):
            it = QTreeWidgetItem([r.name, fmt_size(r.size), viewmodel.date_text(r.mtime), "", r.title])
            it.setData(0, PATH_ROLE, r.path)
            it.setTextAlignment(1, RIGHT)
            it.setToolTip(0, r.path)
            paint_rating(it, 3, r.rating)
            self.tree.addTopLevelItem(it)

    def on_select(self, item, _prev) -> None:
        if item is None:
            return
        path = item.data(0, PATH_ROLE)
        v = core.KB.classify_file(path)
        self.details.setText(
            f"{viewmodel.short_path(path)}\nCo to jest: {v.title} - {v.what}\n"
            f"Dlaczego {kb.RATING_LABEL[v.rating].lower()}: {v.why}")

    def show_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        act = menu.addAction("Otwórz folder w menedżerze plików")
        if menu.exec(self.tree.viewport().mapToGlobal(pos)) == act:
            open_in_file_manager(item.data(0, PATH_ROLE))


# ------------------------------------------------------ strona: sprzatanie --

ADVICE_GROUPS = [
    ("ai", "Wskazane przez AI", "Pozycje, które lokalny model uznał za bezpieczne do usunięcia, a których algorytm nie zgłosił."),
    ("dup", "Identyczne kopie plików", "Pliki, które mają dokładnie tę samą zawartość co inny plik - zostaje jeden egzemplarz."),
    ("inst", "Instalatory, archiwa i niedokończone pobrania", "Pliki, które po użyciu zwykle nie są już potrzebne."),
    ("dir", "Foldery, które da się odtworzyć", "node_modules, środowiska .venv, cache kompilacji - narzędzie zbuduje je ponownie."),
    ("old", "Stare lub tymczasowe pliki", "Dawno nieużywane pliki w miejscach, gdzie zwykle leżą zbędne rzeczy."),
]


def advice_group(a: list) -> str:
    if a[7] == "ai":
        return "ai"
    if a[7] == "dir":
        return "dir"
    reasons = " ".join(a[6])
    if "identyczna kopia" in reasons:
        return "dup"
    if any(w in reasons for w in ("instalator", "archiwum", "niedokończone", "rozpakowane", "pakiet «")):
        return "inst"
    return "old"


class Flag(QObject):
    """Ukryty przelacznik (stan opcji) - zastepuje akcje z menu Opcje; wartosc ustawia strona Ustawienia."""
    toggled = pyqtSignal(bool)

    def __init__(self, value: bool = False) -> None:
        super().__init__()
        self._v = bool(value)

    def isChecked(self) -> bool:  # noqa: N802
        return self._v

    def setChecked(self, v) -> None:  # noqa: N802
        v = bool(v)
        if v != self._v:
            self._v = v
            self.toggled.emit(v)


class DetailPanel(QWidget):
    """Panel szczegolow po prawej: decyzja (zaznaczone/zostaje), kafelki rozmiar/pewnosc/ocena, gdzie to jest,
    co to jest, dlaczego, werdykt AI, podglad i przyciski. Puste sekcje sa ukryte; calosc przewija sie, gdy tekstu jest duzo."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page = page
        self.setObjectName("panel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)  # QWidget sam nie maluje tla z QSS
        self.setMinimumWidth(340)
        self.setMaximumWidth(440)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(6)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        self.title = QLabel("Wybierz pozycję")
        self.title.setObjectName("bigtext")
        self.title.setWordWrap(True)
        self.decision = QLabel("")
        self.decision.setWordWrap(True)
        self.decision.setAccessibleName("Decyzja dla wybranej pozycji")
        self.hint = QLabel(viewmodel.EMPTY_HINT)
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        tiles = QHBoxLayout()
        tiles.setContentsMargins(0, 0, 0, 0)
        self.size_tile, self.score, self.rating_tile = QLabel(""), QLabel(""), QLabel("")
        for t in (self.size_tile, self.score, self.rating_tile):
            t.setObjectName("tile")
            tiles.addWidget(t)
        self.tiles_box = QWidget()
        self.tiles_box.setLayout(tiles)
        self.path = QLabel("")
        self.path.setObjectName("path")
        self._sections: dict = {}
        self.where = self._block("Gdzie to jest", lay, self.path)
        self.what = self._block("Co to jest", lay)
        self.why = self._block("Dlaczego można usunąć", lay)
        self.warn = self._block("Uwaga", lay)
        self.verdict = QLabel("")
        self.verdict.setObjectName("verdict")
        self.verdict.setWordWrap(True)
        self.verdict.hide()
        self.preview_head = QLabel("Podgląd zawartości")
        self.preview_head.setObjectName("section")
        self.preview = PreviewWidget(170)
        # kolejnosc: tytul, decyzja, podpowiedz (pusty stan), kafelki, potem bloki
        lay.insertWidget(0, self.title)
        lay.insertWidget(1, self.decision)
        lay.insertWidget(2, self.hint)
        lay.insertWidget(3, self.tiles_box)
        lay.addWidget(self.verdict)
        lay.addWidget(self.preview_head)
        lay.addWidget(self.preview)
        lay.addStretch(1)

        self.btn_ask = page.btn_ai
        outer.addWidget(self.btn_ask)
        row = QHBoxLayout()
        self.btn_del = QPushButton("Zaznacz do usunięcia")
        self.btn_del.setObjectName("danger")
        self.btn_del.clicked.connect(lambda *_: page.set_current_checked(True))
        self.btn_keep = QPushButton("Zostaw")
        self.btn_keep.clicked.connect(lambda *_: page.set_current_checked(False))
        row.addWidget(self.btn_del)
        row.addWidget(self.btn_keep)
        outer.addLayout(row)
        self.clear()

    def show_ai(self, text: str) -> None:
        """Odpowiedz asystenta AI (przycisk Zapytaj AI) w ramce werdyktu."""
        self.verdict.setText(text)
        self.verdict.show()

    def _block(self, head: str, lay: QVBoxLayout, label=None) -> QLabel:
        h = QLabel(head)
        h.setObjectName("section")
        t = label if label is not None else QLabel("")
        t.setWordWrap(True)
        t.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(h)
        lay.addWidget(t)
        self._sections[id(t)] = (h, t)
        return t

    def _show_block(self, label, text: str) -> None:
        head, t = self._sections[id(label)]
        t.setText(text)
        visible = bool(text) and text != "-"
        head.setVisible(visible)
        t.setVisible(visible)

    def clear(self) -> None:
        self.title.setText("Wybierz pozycję")
        self.decision.setText("")
        self.hint.show()
        self.tiles_box.hide()
        for t in (self.where, self.what, self.why, self.warn):
            self._show_block(t, "")
        self.verdict.hide()
        self.preview_head.hide()
        self.preview.hide()
        self.preview.clear()
        self.btn_del.setEnabled(False)
        self.btn_keep.setEnabled(False)

    def set_decision(self, e) -> None:
        """Tylko decyzja i przyciski (po zmianie zaznaczenia) - bez ponownego wczytywania podgladu."""
        d = viewmodel.decision_of(e)
        color = {"delete": "#e5484d", "stay": "#3ddbb9", "keep": "#9aa5b4"}.get(d["decision_level"], "#9aa5b4")
        self.decision.setText(d["decision"])
        self.decision.setStyleSheet(f"font-weight:600;font-size:11pt;color:{color};")

    def set_entry(self, e) -> None:
        d = viewmodel.detail_sections(e)
        self.hint.hide()
        self.title.setText(d["title"])
        self.set_decision(e)
        self.tiles_box.show()
        muted = "<span style='color:#8b93a0'>{}</span>"
        self.size_tile.setText(f"<b style='font-size:14pt'>{d['size']}</b><br>" + muted.format("rozmiar"))
        self.score.setText(f"<b style='font-size:14pt'>{d['score']}</b><br>" + muted.format("pewność"))
        self.rating_tile.setText(f"<b style='font-size:11pt'>{d['rating_text']}</b><br>" + muted.format("ocena"))
        self._show_block(self.where, d["path"])
        self._show_block(self.what, d["what"])
        self._show_block(self.why, d["why"])
        self._show_block(self.warn, d["warn"])
        self.verdict.setText("🤖 " + d["ai"])
        self.verdict.setVisible(bool(d["ai"]))
        self.btn_del.setEnabled(d["can_toggle"])
        self.btn_keep.setEnabled(d["can_toggle"])
        one = e.kind == "path" and len(e.paths) == 1
        self.preview_head.setVisible(one)
        self.preview.setVisible(one)
        self.preview.show_path(e.paths[0] if one else "")


class MapPage(QWidget):
    """Mapa dysku (treemapa): kafle = foldery, kolor = ocena, klik = wejscie, 'Wyżej' = powrot."""

    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        self.base = ""
        self.nodes: dict = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addLayout(page_header("Mapa dysku", "Rozmiar kafla = rozmiar folderu. Kliknij kafel, żeby wejść głębiej."))
        row = QHBoxLayout()
        self.btn_up = QPushButton("↑ Wyżej")
        self.btn_up.clicked.connect(self.go_up)
        self.crumb = QLabel("")
        self.crumb.setObjectName("muted")
        self.legend = QLabel(rating_legend_html(is_dark_palette()) + " &nbsp; 🤖 wybrane przez AI")
        self.legend.setAccessibleName("Legenda ocen na mapie")
        row.addWidget(self.btn_up)
        row.addWidget(self.crumb, 1)
        row.addWidget(self.legend)
        lay.addLayout(row)
        self.map = TreemapWidget()
        self.map.clicked.connect(self.go)
        self.map.hovered.connect(lambda t: self.info.setText(t))
        lay.addWidget(card_around(self.map), 1)
        self.info = QLabel("")
        self.info.setObjectName("muted")
        lay.addWidget(self.info)

    def source(self) -> dict:
        res = self.win.analysis_res
        if res is not None and getattr(res, "nodes", None):
            return res.nodes
        scan = self.win.folders_page.scan
        return scan.nodes if scan is not None else {}

    def refresh(self) -> None:
        self.nodes = self.source()
        if not self.nodes:
            self.crumb.setText("Brak danych - uruchom analizę (Sprzątanie) albo skan folderów.")
            self.map.set_items([])
            return
        if self.base not in self.nodes:
            self.base = treemap.top_base(self.nodes, [str(core.HOME)])
        self.show_base()

    def show_base(self) -> None:
        kids = treemap.children_of(self.nodes, self.base)
        ai_paths = {p for p, (v, _r, _w) in self.win.clean_page.ai_notes.items() if v == "usunac"}
        self.crumb.setText(viewmodel.short_path(self.base) + f"  ·  {len(kids)} folderów")
        self.btn_up.setEnabled(self.base != treemap.top_base(self.nodes, [str(core.HOME)]))
        self.map.set_items(kids, ai_paths)

    def go(self, path: str) -> None:
        if treemap.children_of(self.nodes, path):
            self.base = path
            self.show_base()
        else:
            self.info.setText("To folder bez podfolderów - sprawdź go na stronie „Foldery i pliki”.")

    def go_up(self, *_a) -> None:
        up = os.path.dirname(self.base.rstrip("/")) or "/"
        if up in self.nodes:
            self.base = up
            self.show_base()


class CleanupPage(QWidget):
    TAB_ADVICE, TAB_FILES, TAB_SYSTEM = 0, 1, 2

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.win = window
        self.cats: list = []  # System i pakiety
        self.adv_cats: list = []  # propozycje algorytmu (Polecane)
        self.file_entries: dict = {}  # sciezka -> Entry (wspolne dla wszystkich zakladek)
        self.adv_items: dict = {}  # sciezka -> pozycja w drzewie 'Polecane'
        self.ai_notes: dict = {}  # sciezka -> (werdykt, ryzyko, dlaczego) z przegladu AI
        self.ai_extra: dict = {}  # pozycje wskazane tylko przez AI (nie bylo ich w algorytmie)
        self.sizes: dict = {}
        self._guard = False
        self._adv_text = "Analiza plików jeszcze nie ruszyła."
        self.learner = learn.Learner(osal.data_dir())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lay.addLayout(page_header(
            "Sprzątanie", "Zaznacz, co usunąć. Kliknij pozycję, żeby zobaczyć, co to i dlaczego tak ją oceniam."))
        top = QHBoxLayout()
        top.setSpacing(8)
        self.disk_combo = QComboBox()
        self.disk_combo.setToolTip("Pokaż pozycje tylko z wybranego dysku lub partycji.")
        self.disk_combo.setMinimumWidth(250)
        self.disk_combo.addItem("Wszystkie dyski", None)
        self.disk_combo.currentIndexChanged.connect(lambda *_: self.apply_filter(self.filter.text()))
        self.mode_combo = QComboBox()
        self.mode_combo.setToolTip("Niedokładny: tylko algorytm. Dokładny: algorytm + AI. "
                                   "Bardzo dokładny: zaznacza tylko AI (algorytm podaje kandydatów).")
        for label, key in SEARCH_MODE_LABELS:
            self.mode_combo.addItem(label, key)
        self.mode_combo.setCurrentIndex(1)
        self.mode_combo.currentIndexChanged.connect(self.on_mode)
        self.group_combo = QComboBox()
        self.group_combo.setToolTip("Pokaż tylko jeden rodzaj pozycji.")
        for label, keys in GROUPS:
            self.group_combo.addItem(label, keys)
        self.group_combo.currentIndexChanged.connect(lambda *_: self.apply_filter(self.filter.text()))
        self.view_combo = QComboBox()
        self.view_combo.setToolTip("Pokaż wszystko albo tylko to, co zaznaczone do usunięcia (lub jeszcze nie zaznaczone).")
        self.view_combo.setAccessibleName("Widok listy: zaznaczone lub niezaznaczone")
        for label, key in (("Widok: wszystkie", None), ("Widok: tylko do usunięcia ✖", "checked"), ("Widok: tylko zostawione", "unchecked")):
            self.view_combo.addItem(label, key)
        self.view_combo.currentIndexChanged.connect(lambda *_: self.apply_filter(self.filter.text()))
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Szukaj na liście …")
        self.filter.setClearButtonEnabled(True)
        self.filter.setFixedWidth(240)
        self.filter.textChanged.connect(self.apply_filter)
        self.btn_recommended = QPushButton("Zaznacz polecane")
        self.btn_recommended.setToolTip("Zaznacza pozycje, które algorytm ocenił jako bezpieczne do usunięcia.")
        self.btn_recommended.clicked.connect(self.select_recommended)
        self.btn_none = QPushButton("Odznacz")
        self.btn_none.clicked.connect(self.uncheck_all)
        self.btn_rescan = QPushButton()
        self.btn_rescan.setIcon(themed(["view-refresh"], QStyle.StandardPixmap.SP_BrowserReload))
        self.btn_rescan.setToolTip("Skanuj ponownie system i pakiety (Ctrl+R)")
        self.btn_rescan.setAccessibleName("Skanuj ponownie system i pakiety")
        self.filter.setAccessibleName("Szukaj na liście sprzątania")
        self.mode_combo.setAccessibleName("Dokładność wyszukiwania")
        self.disk_combo.setAccessibleName("Filtr dysku lub partycji")
        self.group_combo.setAccessibleName("Filtr rodzaju pozycji")
        self.btn_rescan.clicked.connect(self.win.start_scan)
        top.addWidget(self.mode_combo)
        top.addWidget(self.disk_combo)
        top.addWidget(self.group_combo)
        top.addWidget(self.view_combo)
        top.addWidget(self.filter)
        top.addStretch(1)
        for w in (self.btn_recommended, self.btn_none, self.btn_rescan):
            top.addWidget(w)
        self.toolbar_widgets = [self.filter, self.mode_combo, self.disk_combo, self.group_combo, self.view_combo, self.btn_recommended, self.btn_none, self.btn_rescan]
        lay.addLayout(top)

        self.tabs = QTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(True)
        for title in ("Polecane", "Wszystkie pliki", "System i pakiety"):
            self.tabs.addTab(title)
        self.tabs.currentChanged.connect(self.on_tab)
        lay.addWidget(self.tabs)

        strip = QHBoxLayout()
        self.adv_status = QLabel(self._adv_text)
        self.adv_status.setObjectName("muted")
        self.adv_status.setWordWrap(True)
        self.btn_analyze = QPushButton("Analizuj ponownie")
        self.btn_analyze.setAccessibleName("Analizuj pliki ponownie")
        self.btn_analyze.setToolTip("Przeszukuje wszystkie pliki (dom i dyski danych) i szuka rzeczy do usunięcia.")
        self.btn_analyze.clicked.connect(self.win.start_analysis)
        self.btn_ai_review = QPushButton("🤖 Oceń przez AI")
        self.btn_ai_review.setToolTip("Lokalny model przegląda kandydatów i największe rzeczy na dysku i sam "
                                      "zaznacza te, które uzna za bezpieczne do usunięcia.")
        self.btn_ai_review.clicked.connect(self.win.toggle_triage)
        self.btn_rejected = QPushButton("Odrzucone przez recenzenta")
        self.btn_rejected.setToolTip("Pozycje, które AI uznało za zbędne, ale recenzent ich nie zatwierdził - możesz je przejrzeć i zdecydować sam.")
        self.btn_rejected.clicked.connect(self.show_rejected)
        self.btn_rejected.setVisible(False)
        strip.addWidget(self.adv_status, 1)
        strip.addWidget(self.btn_rejected)
        strip.addWidget(self.btn_ai_review)
        strip.addWidget(self.btn_analyze)
        lay.addLayout(strip)
        self.prog = QProgressBar()  # postep z procentem i szacunkowym czasem (analiza i ocena AI)
        self.prog.setObjectName("busy")
        self.prog.setTextVisible(True)
        self.prog.setFixedHeight(16)
        self.prog.setRange(0, 1000)
        self.prog.setVisible(False)
        lay.addWidget(self.prog)

        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        lay.addWidget(self.banner)

        self.stack = QStackedWidget()
        scan_page = QWidget()
        sl = QVBoxLayout(scan_page)
        sl.addStretch(1)
        big = QLabel("Szukam rzeczy do sprzątnięcia …")
        big.setObjectName("bigtext")
        big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scan_status = QLabel("")
        self.scan_status.setObjectName("muted")
        self.scan_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar = QProgressBar()
        bar.setObjectName("busy")
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        bar.setFixedSize(280, 6)
        sl.addWidget(big)
        sl.addWidget(self.scan_status)
        sl.addSpacing(10)
        sl.addWidget(bar, 0, Qt.AlignmentFlag.AlignCenter)
        sl.addStretch(1)
        self.stack.addWidget(scan_page)  # 0

        self.adv_tree = self._make(["Pozycja", "Rozmiar", "Pewność", "Dlaczego"], [380, 120, 90, 380])
        self.files_tree = self._make(["Pozycja", "Rozmiar", "Ocena", "Co to jest"], [400, 130, 140, 300])
        self.tree = self._make(["Pozycja", "Rozmiar", "Ocena", "Co to jest"], [400, 130, 140, 300])
        self.adv_card = card_around(self.adv_tree)
        self.files_card = card_around(self.files_tree)
        self.tree_card = card_around(self.tree)
        self.adv_empty = QLabel(self._adv_text)
        self.adv_empty.setObjectName("muted")
        self.adv_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.adv_empty.setWordWrap(True)
        self.pages = QStackedWidget()
        for w in (self.adv_card, self.files_card, self.tree_card, self.adv_empty):
            self.pages.addWidget(w)
        self.stack.addWidget(self.pages)  # 1
        self.details = details_label()
        self.details.hide()  # tekst szczegolow pokazuje teraz panel po prawej (zostaje dla zgodnosci)
        self._cur_entry = None
        self.btn_ai = QPushButton("🤖 Zapytaj AI")
        self.btn_ai.setToolTip("Lokalny model (np. Gemma przez llama.cpp / Unsloth, na Twojej karcie) wyjaśni pozycję. Dostaje tylko ścieżkę, "
                               "rozmiar i nazwy plików obok - nie zawartość. To tylko podpowiedź.")
        self.btn_ai.clicked.connect(lambda: self._cur_entry is not None and self.win.ask_ai(self._cur_entry))
        self.btn_ai.setEnabled(False)
        self.panel = DetailPanel(self)
        body = QHBoxLayout()  # lista po lewej, szczegoly w panelu po prawej
        body.setSpacing(12)
        body.addWidget(self.stack, 1)
        body.addWidget(self.panel)
        lay.addLayout(body, 1)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(160)
        mono = QFont("monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.log.setFont(mono)
        self.log.hide()
        lay.addWidget(self.log)
        lay.addWidget(self._build_footer())

    def _make(self, headers: list, widths: list) -> QTreeWidget:
        tree = make_tree(headers, widths)
        tree.header().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)  # start: kolejnosc programu (wg pewnosci); klik w naglowek sortuje
        tree.setSortingEnabled(True)
        tree.header().setSortIndicatorShown(True)
        tree.header().setToolTip("Kliknij nagłówek kolumny, żeby posortować (nazwa, rozmiar, pewność).")
        tree.setAnimated(True)
        tree.setItemDelegateForColumn(1, SizeBarDelegate(tree))
        tree.itemChanged.connect(self.on_item_changed)
        tree.itemExpanded.connect(self.on_expand)
        tree.itemDoubleClicked.connect(self._toggle_expand)
        tree.currentItemChanged.connect(self.on_select)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(lambda pos, t=tree: self.show_menu(t, pos))
        return tree

    def _build_footer(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("footer")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(20, 10, 20, 10)
        lay.setSpacing(12)

        self.ring = RingWidget(64)
        lay.addWidget(self.ring)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        self.sum_big = QLabel()
        self.sum_big.setObjectName("bigtext")
        self.sum_small = QLabel()
        self.sum_small.setObjectName("muted")
        self.sum_disks = QLabel()
        self.sum_disks.setObjectName("muted")
        self.sum_plan = QLabel()  # 'Co zniknie: bezpowrotnie X, do kosza Y, liczby wg ocen'
        self.sum_plan.setObjectName("muted")
        self.sum_plan.setWordWrap(True)
        self.sum_plan.setAccessibleName("Co dokładnie zostanie usunięte")
        texts.addWidget(self.sum_big)
        texts.addWidget(self.sum_small)
        texts.addWidget(self.sum_plan)
        texts.addWidget(self.sum_disks)
        lay.addLayout(texts, 1)

        self.btn_plan = QPushButton("Pokaż, co zostanie usunięte")
        self.btn_plan.setToolTip("Pełna lista zaznaczonych pozycji: nazwa, rozmiar, ocena, pełna ścieżka i powód.")
        self.btn_plan.clicked.connect(self.show_plan)
        self.btn_plan.setEnabled(False)
        lay.addWidget(self.btn_plan)
        self.btn_report = QPushButton("Raport ▾")
        self.btn_report.setToolTip("Lista: co usunę, co zostawię i co jest chronione - do wysłania do sprawdzenia.")
        menu = QMenu(self.btn_report)
        menu.addAction("Zapisz raport (Markdown .md) …").triggered.connect(lambda: self.win.save_report("md"))
        menu.addAction("Zapisz tabelę (CSV .csv) …").triggered.connect(lambda: self.win.save_report("csv"))
        menu.addAction("Zapisz raport HTML (pełny obraz) …").triggered.connect(lambda: self.win.save_report("html"))
        menu.addAction("Kopiuj raport do schowka").triggered.connect(self.win.copy_report)
        self.btn_report.setMenu(menu)
        lay.addWidget(self.btn_report)

        # Opcje sa tylko na stronie Ustawienia; tu zostaje ukryty stan (synchronizowany z ustawieniami),
        # z ktorego korzysta reszta programu.
        self.trash_box, self.dry_box = Flag(True), Flag(False)
        self.act_ai_auto, self.act_review_each, self.act_ai_look = Flag(True), Flag(True), Flag(True)
        self.act_anon, self.act_private, self.btn_log = Flag(True), Flag(False), Flag(False)
        self.dry_box.toggled.connect(self.update_primary_text)
        self.trash_box.toggled.connect(lambda *_: self.update_summary())
        self.btn_log.toggled.connect(lambda on: self.log.setVisible(bool(on) and bool(self.log.toPlainText())))
        self.log.textChanged.connect(lambda: self.log.setVisible(bool(self.btn_log.isChecked()) and bool(self.log.toPlainText())))
        for act, key in ((self.trash_box, "trash_mine"), (self.dry_box, "dry_run"), (self.btn_log, "show_log"),
                         (self.act_anon, "anonymize"), (self.act_private, "show_private_names"),
                         (self.act_ai_auto, "ai_auto"), (self.act_review_each, "review_each"),
                         (self.act_ai_look, "ai_inspect")):
            act.toggled.connect(lambda v, k=key: self.win.save_quick(k, bool(v)))
        self.btn_settings = QPushButton("⚙ Ustawienia")
        self.btn_settings.clicked.connect(lambda *_: self.win.show_settings())
        lay.addWidget(self.btn_settings)

        self.busy_bar = QProgressBar()
        self.busy_bar.setObjectName("busy")
        self.busy_bar.setTextVisible(False)
        self.busy_bar.setFixedSize(60, 6)
        self.busy_bar.setRange(0, 1)
        lay.addWidget(self.busy_bar)

        self.btn_clean = QPushButton("Wyczyść zaznaczone")
        self.btn_clean.setObjectName("primary")
        self.btn_clean.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clean.setAccessibleName("Wyczyść zaznaczone pozycje (Ctrl+Enter)")
        self.btn_clean.clicked.connect(self.win.start_clean)
        lay.addWidget(self.btn_clean)
        return frame

    QUICK = {"trash_mine": "trash_box", "review_each": "act_review_each", "dry_run": "dry_box",
             "anonymize": "act_anon", "show_private_names": "act_private", "show_log": "btn_log",
             "ai_auto": "act_ai_auto", "ai_inspect": "act_ai_look"}

    def on_mode(self, *_a) -> None:
        if self.win._syncing:
            return
        self.win.set_search_mode(self.mode_combo.currentData())

    def apply_settings(self, cfg: dict) -> None:
        """Ustawia szybkie przelaczniki (menu Opcje i Raport) zgodnie z ustawieniami."""
        i = self.mode_combo.findData(cfg.get("search_mode", "assisted"))
        if i >= 0 and i != self.mode_combo.currentIndex():
            self.mode_combo.setCurrentIndex(i)
        for key, attr in self.QUICK.items():
            act = getattr(self, attr)
            if bool(act.isChecked()) != bool(cfg[key]):
                act.setChecked(bool(cfg[key]))
        self.update_primary_text()

    def forget_learning(self, *_a) -> None:
        self.learner.forget()
        self.show_banner("Zapomniałem Twoje wcześniejsze decyzje - ocena wraca do ustawień domyślnych "
                         "(po kolejnej analizie).")

    # -- stan
    def trees(self) -> list:
        return [self.adv_tree, self.files_tree, self.tree]

    def all_cats(self) -> list:
        return list(self.adv_cats) + list(self.cats)

    def update_primary_text(self, *_a) -> None:
        self.btn_clean.setText("Symuluj czyszczenie" if self.dry_box.isChecked() else "Wyczyść zaznaczone")

    def set_busy(self, busy: bool) -> None:
        for w in self.toolbar_widgets + [self.tabs, self.pages]:
            w.setEnabled(not busy)
        self.btn_analyze.setEnabled(not busy and not self.win.analysis_busy)
        self.busy_bar.setRange(0, 0 if busy else 1)
        self.busy_bar.setValue(0)
        self.update_summary()

    def show_banner(self, text: str, level: str = "ok") -> None:
        self.banner.setText(text)
        self.banner.setProperty("level", level)
        style = self.banner.style()
        style.unpolish(self.banner)
        style.polish(self.banner)
        self.banner.show()

    def show_scanning(self) -> None:
        self.banner.hide()
        self.scan_status.setText("")
        self.stack.setCurrentIndex(0)

    def set_progress(self, percent, eta: str = "", label: str = "") -> None:
        """percent: 0..100, None = nieokreslony (pasek 'w ruchu'), -1 = ukryj pasek."""
        if percent == -1:
            self.prog.setVisible(False)
            return
        self.prog.setVisible(True)
        if percent is None:
            self.prog.setRange(0, 0)
            self.prog.setFormat("")
            return
        self.prog.setRange(0, 1000)
        self.prog.setValue(int(percent * 10))
        self.prog.setFormat(f"{label}{percent}%" + (f" · pozostało {eta}" if eta else ""))

    def set_analysis_status(self, text: str, busy: bool = False) -> None:
        if not busy:
            self.prog.setVisible(False)
        self._adv_text = text
        self.adv_status.setText(text)
        self.adv_empty.setText(text)
        self.btn_analyze.setEnabled(not busy and not self.win.busy)

    def on_tab(self, idx: int) -> None:
        self._refresh_checks()
        self._show_tab(idx)
        self.on_select(self._current_tree().currentItem(), None)

    def _current_tree(self):
        return (self.adv_tree, self.files_tree, self.tree)[max(0, min(self.tabs.currentIndex(), 2))]

    def _show_tab(self, idx: int) -> None:
        if idx == self.TAB_ADVICE and not self.adv_cats:
            self.pages.setCurrentIndex(3)
        else:
            self.pages.setCurrentIndex(idx)
        self.adv_status.setVisible(idx == self.TAB_ADVICE)
        self.btn_analyze.setVisible(idx == self.TAB_ADVICE)

    def _refresh_tab_titles(self) -> None:
        n_adv = sum(len(c.entries) for c in self.adv_cats)
        n_sys = sum(len(c.entries) for c in self.cats)
        self.tabs.setTabText(self.TAB_ADVICE, f"Polecane ({n_adv})" if n_adv else "Polecane")
        self.tabs.setTabText(self.TAB_SYSTEM, f"System i pakiety ({n_sys})" if n_sys else "System i pakiety")

    # -- zawartosc
    def fill_disks(self) -> None:
        cats = self.all_cats()
        labels = list(dict.fromkeys(list(disks.mount_labels().values())
                                    + [e.disk for c in cats for e in c.entries if e.disk]))
        keep = self.disk_combo.currentData()
        self.disk_combo.blockSignals(True)
        self.disk_combo.clear()
        self.disk_combo.addItem("Wszystkie dyski", None)
        for lab in labels:
            n = sum(1 for c in cats for e in c.entries if e.disk == lab)
            self.disk_combo.addItem(f"{lab}  ({n} {plural(n, 'pozycja', 'pozycje', 'pozycji')})", lab)
        idx = next((i for i in range(len(labels) + 1) if self.disk_combo.itemData(i) == keep), 0)
        self.disk_combo.setCurrentIndex(idx)
        self.disk_combo.blockSignals(False)

    def _top_item(self, tree, cat, bold, with_lock: bool = True):
        grey = QBrush(self.palette().placeholderText())
        total = sum(e.size for e in cat.entries)
        top = SortItem([cat.title, fmt_size(total), "", cat.desc])
        set_sort_keys(top, cat.title.casefold(), total, "", cat.desc.casefold())
        top.setFont(0, bold)
        top.setFont(1, bold)
        top.setIcon(0, themed(*CATEGORY_ICONS.get(cat.key, (["folder"], QStyle.StandardPixmap.SP_DirIcon))))
        if cat.root and with_lock:
            top.setIcon(3, themed(["object-locked", "lock"], QStyle.StandardPixmap.SP_DialogApplyButton))
        top.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
        top.setCheckState(0, Qt.CheckState.Unchecked)
        top.setTextAlignment(1, RIGHT)
        top.setToolTip(0, cat.desc)
        top.setSizeHint(0, QSize(0, 40))
        for col in range(4):
            top.setBackground(col, self.palette().alternateBase())
        top.setForeground(3, grey)
        tree.addTopLevelItem(top)
        return top

    def _bold(self):
        bold = QFont()
        bold.setBold(True)
        bold.setPointSizeF(bold.pointSizeF() + 1 if bold.pointSizeF() > 0 else 11)
        return bold

    def populate(self, cats: list) -> None:
        """System i pakiety + sekcje 'Wszystkie pliki' kazdego dysku."""
        self.cats = cats
        self._guard = True
        self.tree.clear()
        self.files_tree.clear()
        bold = self._bold()
        grey = QBrush(self.palette().placeholderText())
        for cat in cats:
            if not cat.entries:
                continue
            top = self._top_item(self.tree, cat, bold)
            biggest = max((e.size for e in cat.entries), default=0)
            for e in sorted(cat.entries, key=lambda x: -x.size):
                label = ("⚠ " if e.warn else "") + e.label
                what = e.what.split(" - ")[0] if e.what else e.note
                ch = SortItem(top, [label, fmt_size(e.size), "", what])
                set_sort_keys(ch, e.label.casefold(), e.size, e.rating, what.casefold())
                ch.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                            | Qt.ItemFlag.ItemIsUserCheckable)
                ch.setCheckState(0, Qt.CheckState.Checked if e.checked else Qt.CheckState.Unchecked)
                ch.setData(0, ENTRY_ROLE, e)
                ch.setData(1, FRAC_ROLE, (e.size / biggest) if biggest > 0 and e.size > 0 else None)
                ch.setTextAlignment(1, RIGHT)
                paint_rating(ch, 2, e.rating)
                ch.setToolTip(0, e.warn or e.note or e.label)
                ch.setForeground(3, grey)
                ch.setSizeHint(0, QSize(0, 32))
            for p in cat.protected:
                pr = QTreeWidgetItem(top, ["🔒 " + p.label, fmt_size(p.size), "", p.reason])
                pr.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                pr.setTextAlignment(1, RIGHT)
                paint_rating(pr, 2, p.rating)
                pr.setForeground(0, grey)
                pr.setForeground(3, grey)
                pr.setToolTip(0, p.reason)
                pr.setSizeHint(0, QSize(0, 30))
            self._sync_parent(top)
            top.setExpanded(len(cat.entries) <= 12)
        old = {p: e for p, e in self.file_entries.items() if e.rule == "analiza"}
        self.file_entries = old
        for path, disk in core.cleanup_roots():
            sec = QTreeWidgetItem([viewmodel.short_path(path), "", "", disk or "dysk systemowy"])
            sec.setFont(0, bold)
            sec.setIcon(0, themed(["folder", "drive-harddisk"], QStyle.StandardPixmap.SP_DriveHDIcon))
            sec.setData(0, SECTION_ROLE, (path, disk))
            sec.setToolTip(0, "Rozwiń, żeby zobaczyć i zaznaczyć dowolne pliki tego dysku.")
            sec.setSizeHint(0, QSize(0, 40))
            for col in range(4):
                sec.setBackground(col, self.palette().alternateBase())
            sec.setForeground(3, grey)
            self.files_tree.addTopLevelItem(sec)
            QTreeWidgetItem(sec, ["…"])
        self._guard = False
        self._refresh_tab_titles()
        self.fill_disks()
        self.stack.setCurrentIndex(1)
        self._show_tab(self.tabs.currentIndex())
        self.apply_filter(self.filter.text())
        self.update_summary()

    def _reason_text(self, e) -> str:
        return "; ".join(([x for x in e.reasons if x.startswith("🤖")] + [x for x in e.reasons if not x.startswith("🤖")])[:3])

    def _adv_child(self, top, e, biggest: int):
        grey = QBrush(self.palette().placeholderText())
        mine = "👤 " if e.rating == kb.MINE else ""
        badge = {"usunac": "🤖✓ ", "zostawic": "🤖✗ ", "nie_wiem": "🤖? "}.get(e.ai, "")
        reason = self._reason_text(e)
        ch = SortItem(top, [mine + badge + e.label, fmt_size(e.size), (core.score_label(e.score).replace("ryzyko ", "") if core.ai_only() else f"{e.score}%"), reason])
        set_sort_keys(ch, e.label.casefold(), e.size, e.score, reason.casefold())
        ch.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
        ch.setCheckState(0, Qt.CheckState.Checked if e.checked else Qt.CheckState.Unchecked)
        ch.setData(0, ENTRY_ROLE, e)
        ch.setData(1, FRAC_ROLE, (e.size / biggest) if biggest > 0 and e.size > 0 else None)
        ch.setTextAlignment(1, RIGHT)
        ch.setTextAlignment(2, RIGHT)
        ch.setToolTip(0, e.paths[0])
        ch.setToolTip(3, "\n".join(e.reasons))
        ch.setForeground(3, grey)
        ch.setSizeHint(0, QSize(0, 32))
        self.adv_items[e.paths[0]] = ch
        return ch

    # -- ocena przez AI
    def apply_note(self, e, verdict: str, risk: str, why: str) -> None:
        e.ai, e.ai_risk = verdict, risk
        e.reasons = [x for x in e.reasons if not x.startswith("🤖")] + [f"🤖 {why or ai.VERDICTS.get(verdict, verdict)}"]
        head = (f"AI: {ai.VERDICTS.get(verdict, verdict)} (ryzyko {risk or 'nieznane'})" if core.ai_only()
                else core.confidence_text(e.score))
        e.why = f"{head}: " + "; ".join(e.reasons)
        if not e.touched:  # decyduje model: zaznacza tylko 'usunac' z niskim ryzykiem
            if kb.has_reason(e.reasons, "project") and e.score >= core.ADVICE_AUTO:
                pass  # folder wygenerowany w projekcie rozpoznany po plikach obok: model nie odznacza (zdarza sie, ze myli Library z danymi)
            else:
                e.checked = e.suggested = (verdict == "usunac" and risk in ai.allowed_risks()
                                           and (settings.RUNTIME["ai_mine"] or e.rating != kb.MINE))

    def apply_ai(self, results: dict, meta: dict) -> None:
        """Wyniki przegladu AI: {sciezka: (werdykt, ryzyko, dlaczego)}; meta = {sciezka: pozycja z puli}."""
        self._guard = True
        try:
            for path, (v, r, why) in results.items():
                self.ai_notes[path] = (v, r, why)
                e = self.file_entries.get(path)
                if e is not None and e.rule == "analiza":
                    self.apply_note(e, v, r, why)
                    it = self.adv_items.get(path)
                    if it is not None:
                        badge = {"usunac": "🤖✓ ", "zostawic": "🤖✗ ", "nie_wiem": "🤖? "}.get(v, "")
                        it.setText(0, ("👤 " if e.rating == kb.MINE else "") + badge + e.label)
                        it.setText(3, self._reason_text(e))
                        it.setToolTip(3, "\n".join(e.reasons))
                        it.setCheckState(0, Qt.CheckState.Checked if e.checked else Qt.CheckState.Unchecked)
                elif v == "usunac" and r in ("niskie", "srednie") and path in meta:
                    d = meta[path]
                    self.ai_extra[path] = [80 if r == "niskie" else 55, path, d["size"], d.get("mtime", 0),
                                           d["rating"], ("Wskazane przez AI" if core.ai_only() else d.get("title") or "Wskazane przez AI"), [], "ai"]
                    e = self._new_advice_entry(self.ai_extra[path])
                    if e is None:
                        continue
                    self.apply_note(e, v, r, why)
                    self._attach_ai_entry(e)
            for t in (self.adv_tree,):
                for i in range(t.topLevelItemCount()):
                    self._sync_parent(t.topLevelItem(i))
            self._rebind_file_rows()
        finally:
            self._guard = False
        self._refresh_tab_titles()
        self.update_summary()

    def _new_advice_entry(self, a: list):
        labels = disks.mount_labels()
        e = core.advice_entry(a, labels.get(core.mount_of(a[1], core.read_mounts()), ""))
        if e is None:
            return None
        e.checked = e.suggested = False
        self.file_entries[e.paths[0]] = e
        return e

    def _attach_ai_entry(self, e) -> None:
        cat = next((c for c in self.adv_cats if c.key == "adv_ai"), None)
        bold = self._bold()
        if cat is None:
            t, d = next((t, d) for k, t, d in ADVICE_GROUPS if k == "ai")
            cat = core.Category("adv_ai", t, d, False, [])
            self.adv_cats.insert(0, cat)
            top = self._top_item(self.adv_tree, cat, bold)
            self.adv_tree.insertTopLevelItem(0, self.adv_tree.takeTopLevelItem(self.adv_tree.topLevelItemCount() - 1))
            top.setExpanded(True)
        else:
            top = next(self.adv_tree.topLevelItem(i) for i in range(self.adv_tree.topLevelItemCount())
                       if self.adv_tree.topLevelItem(i).text(0) == cat.title)
        cat.entries.append(e)
        self._adv_child(top, e, max(e.size, 1))
        top.setText(1, fmt_size(sum(x.size for x in cat.entries)))

    def set_advice(self, advice: list, notes=()) -> None:
        """Buduje zakladke 'Polecane' z propozycji algorytmu (lista z scanner.ScanResult.advice)."""
        labels = disks.mount_labels()
        mounts = core.read_mounts()
        by_group: dict = {k: [] for k, _t, _d in ADVICE_GROUPS}
        self.adv_items = {}
        if settings.RUNTIME.get("search_mode") == "ai_only":
            advice = [x for x in self.ai_extra.values() if os.path.lexists(x[1])]  # tylko AI: to, co wskazal model
        else:
            advice = list(advice) + [x for x in self.ai_extra.values() if x[1] not in {a[1] for a in advice} and os.path.lexists(x[1])]
        for a in advice:
            if self.learner.is_ignored(a[1]):
                continue
            disk = labels.get(core.mount_of(a[1], mounts), "")
            e = core.advice_entry(a, disk)
            if e is None:
                continue
            new, delta = (e.score, 0) if settings.RUNTIME.get("search_mode") == "ai_only" else self.learner.adjust(e.score, self.feats(e))
            if delta:  # korekta z Twoich wczesniejszych decyzji
                e.score = new
                e.reasons = e.reasons + [f"dopasowano do Twoich wcześniejszych decyzji ({delta:+d} pkt)"]
                e.why = f"Pewność {new}%: " + "; ".join(e.reasons)
                e.checked = e.suggested = new >= core.ADVICE_AUTO and e.rating != kb.MINE
                if new < 45:
                    continue
            note = self.ai_notes.get(e.paths[0])
            if note is not None:
                self.apply_note(e, *note)
            prev = self.file_entries.get(e.paths[0])
            if prev is not None and prev.rule != "analiza":
                e.checked = prev.checked or e.checked
            elif prev is not None and prev.touched:
                e.checked, e.touched = prev.checked, True
            self.file_entries[e.paths[0]] = e
            by_group[advice_group(a)].append(e)
        self.adv_cats = [
            core.Category("adv_" + k, t, d, False, sorted(by_group[k], key=lambda x: (-x.score, -x.size)))
            for k, t, d in ADVICE_GROUPS if by_group[k]
        ]
        self._guard = True
        self.adv_tree.clear()
        bold = self._bold()
        for cat in self.adv_cats:
            top = self._top_item(self.adv_tree, cat, bold)
            biggest = max((e.size for e in cat.entries), default=0)
            for e in cat.entries:
                self._adv_child(top, e, biggest)
            self._sync_parent(top)
            top.setExpanded(True)
        self._rebind_file_rows()
        self._guard = False
        n = sum(len(c.entries) for c in self.adv_cats)
        total = sum(e.size for c in self.adv_cats for e in c.entries)
        text = (f"Znalazłem {n} {plural(n, 'propozycję', 'propozycje', 'propozycji')} "
                f"({fmt_size(total)}). Zaznaczone od razu są te, których jestem pewny; resztę oceń sam."
                if n else "Nie znalazłem nic oczywistego do usunięcia w Twoich plikach.")
        if self.learner.strength():
            text += f"  Uwzględniam {len(self.learner.samples)} Twoich wcześniejszych decyzji."
        if notes:
            text += "  " + " ".join(notes)
        self.set_analysis_status(text)
        self._refresh_tab_titles()
        self.fill_disks()
        self._show_tab(self.tabs.currentIndex())
        self.apply_filter(self.filter.text())
        self.update_summary()

    def feats(self, e) -> dict:
        score = e.score if e.score else 60  # reczne wybory: neutralna pewnosc bazowa
        return learn.features(e.paths[0], e.size, e.rating, score, e.reasons, str(core.HOME))

    def record_decisions(self, selected: list) -> int:
        """Przed prawdziwym czyszczeniem: zapamietaj, co wybrales (a co zostawiles mimo wysokiej pewnosci)."""
        sel_ids = {id(e) for e in selected}
        pos = [self.feats(e) for e in selected if e.kind == "path" and e.paths and (e.user_pick or e.score)]
        neg = [self.feats(e) for c in self.adv_cats for e in c.entries if id(e) not in sel_ids and e.score >= 60]
        return self.learner.record(pos, neg) if (pos or neg) else 0

    def rejected_entries(self) -> list:
        """Pozycje, ktore AI wskazalo do usuniecia, ale recenzent ich nie zatwierdzil (werdykt koncowy != 'usunac')."""
        out = []
        for path in self.ai_extra:
            note = self.ai_notes.get(path)
            e = self.file_entries.get(path)
            if e is not None and note is not None and note[0] != "usunac" and not e.checked:
                out.append(e)
        return sorted(out, key=lambda x: -x.size)

    def accept_rejected(self, entries: list) -> int:
        """Uzytkownik jednak zaznacza te pozycje do usuniecia (twarde zabezpieczenia i potwierdzenie przed usunieciem zostaja)."""
        n = 0
        for e in entries:
            if e.deletable:
                e.checked = True
                e.touched = True
                it = self.adv_items.get(e.paths[0]) if e.paths else None
                if it is not None:
                    it.setCheckState(0, Qt.CheckState.Checked)
                n += 1
        self.update_summary()
        return n

    def show_plan(self, *_a) -> None:
        sel = self.selected_entries()
        rows = viewmodel.plan_rows(sel, self.trash_box.isChecked(), fmt_size)
        dlg = QDialog(self)
        dlg.setWindowTitle("Co zostanie usunięte")
        dlg.resize(1100, 600)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(viewmodel.plan_line(sel, self.trash_box.isChecked(), fmt_size) or "Nic nie zaznaczono."))
        tree = QTreeWidget()
        tree.setHeaderLabels(["Pozycja", "Rozmiar", "Ocena", "Gdzie", "Dlaczego"])
        tree.setColumnWidth(0, 300)
        tree.setColumnWidth(2, 130)
        tree.setColumnWidth(3, 360)
        groups: dict = {}
        for how, label, size, rating, where, why, nbytes in rows:
            top = groups.get(how)
            if top is None:
                top = SortItem(tree, [how])
                top.setExpanded(True)
                groups[how] = top
            it = SortItem(top, [label, size, rating, where, why])
            set_sort_keys(it, label.casefold(), nbytes, rating, where.casefold(), why.casefold())
            it.setTextAlignment(1, RIGHT)
        tree.header().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)  # start: od najwiekszych; klik w naglowek sortuje
        tree.setSortingEnabled(True)
        tree.header().setSortIndicatorShown(True)
        tree.header().setToolTip("Kliknij nagłówek kolumny, żeby posortować (nazwa, rozmiar, ocena, miejsce).")
        for how, top in groups.items():
            top.setText(0, f"{how} ({top.childCount()})")
        lay.addWidget(tree, 1)
        close = QPushButton("Zamknij")
        close.clicked.connect(dlg.accept)
        lay.addWidget(close)
        dlg.exec()

    def show_rejected(self, *_a) -> None:
        ents = self.rejected_entries()
        dlg = QDialog(self)
        dlg.setWindowTitle("Odrzucone przez recenzenta")
        dlg.resize(900, 520)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"{len(ents)} pozycji, które AI uznało za zbędne, a recenzent nie zatwierdził. "
                             "Zaznacz te, które jednak chcesz usunąć - dalej zadziała zwykłe potwierdzenie przed usunięciem."))
        tree = QTreeWidget()
        tree.setHeaderLabels(["Pozycja", "Rozmiar", "Dlaczego odrzucone"])
        tree.setColumnWidth(0, 360)
        rows = []
        for e in ents:
            why = "; ".join(x for x in e.reasons if x.startswith("🤖")) or e.why
            it = SortItem(tree, [e.label, fmt_size(e.size), why])
            set_sort_keys(it, e.label.casefold(), e.size, why.casefold())
            it.setTextAlignment(1, RIGHT)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(0, Qt.CheckState.Unchecked)
            it.setToolTip(0, e.paths[0] if e.paths else "")
            rows.append((it, e))
        tree.setSortingEnabled(True)
        tree.header().setSortIndicator(1, Qt.SortOrder.DescendingOrder)
        lay.addWidget(tree, 1)
        buttons = QHBoxLayout()
        ok = QPushButton("Zaznacz wybrane do usunięcia")
        close = QPushButton("Zamknij")
        buttons.addStretch(1)
        buttons.addWidget(ok)
        buttons.addWidget(close)
        lay.addLayout(buttons)
        ok.clicked.connect(lambda: (self.accept_rejected([e for it, e in rows if it.checkState(0) == Qt.CheckState.Checked]), dlg.accept()))
        close.clicked.connect(dlg.reject)
        dlg.exec()

    def protect_entry(self, item) -> None:
        """'Zawsze zostaw': sciezka trafia na liste chronionych w ustawieniach (program jej nie zaproponuje, nie pokaze AI i nie usunie)."""
        e = item.data(0, ENTRY_ROLE)
        if e is None or not e.paths:
            return
        cfg = settings.load(env=False)
        paths = list(cfg["protected_paths"])
        if e.paths[0] not in paths:
            paths.append(e.paths[0])
        cfg = settings.sanitize({**cfg, "protected_paths": paths})
        settings.save(cfg)
        settings.apply(settings.load())
        e.checked = False
        for c in self.adv_cats:
            if e in c.entries:
                c.entries.remove(e)
        item.setHidden(True)
        self.file_entries.pop(e.paths[0], None)
        self._refresh_tab_titles()
        self.update_summary()

    def ignore_entry(self, item) -> None:
        e = item.data(0, ENTRY_ROLE)
        if e is None or not e.paths:
            return
        self.learner.ignore(e.paths[0])
        e.checked = False
        for c in self.adv_cats:
            if e in c.entries:
                c.entries.remove(e)
        item.setHidden(True)
        self.file_entries.pop(e.paths[0], None)
        self._refresh_tab_titles()
        self.update_summary()

    def _is_section(self, top) -> bool:
        return top.data(0, SECTION_ROLE) is not None

    def on_expand(self, item) -> None:
        """Leniwie wczytuje zawartosc dysku/folderu (wszystkie pliki, na zywo)."""
        if item.childCount() != 1 or item.child(0).text(0) != "…":
            return
        sec = item.data(0, SECTION_ROLE)
        if sec is not None:
            path, disk = sec
        elif item.data(0, PATH_ROLE):
            path, disk = item.data(0, PATH_ROLE), item.data(0, SECTION_ROLE + 1)
        else:
            return
        item.takeChild(0)
        parent_ent = item.data(0, ENTRY_ROLE)
        self._guard = True
        try:
            self._fill_files(item, path, disk, bool(parent_ent is not None and parent_ent.checked))
        finally:
            self._guard = False

    def _fill_files(self, parent, path: str, disk: str, parent_checked: bool) -> None:
        items, extra, err = core.list_folder(path, self.sizes)
        if err:
            QTreeWidgetItem(parent, [f"(brak dostępu: {err})"])
            return
        if not items:
            QTreeWidgetItem(parent, ["(pusty folder)"])
            return
        grey = QBrush(self.palette().placeholderText())
        biggest = max((i.size for i in items), default=0)
        for i in items:
            ent = self.file_entries.get(i.path)
            if ent is None:
                ent = core.file_entry(i, disk)
                self.file_entries[i.path] = ent
            locked = ent.rating == kb.KEEP
            size_txt = (("≥ " if not i.exact else "") + fmt_size(i.size)) if i.size >= 0 else "—"
            name = ("🔒 " if locked else "") + ("📁 " if i.is_dir else "") + i.name
            it = QTreeWidgetItem(parent, [name, size_txt, "", i.verdict.title])
            it.setData(0, PATH_ROLE, i.path)
            it.setData(0, ENTRY_ROLE, ent)
            it.setData(0, SECTION_ROLE + 1, disk)
            it.setData(1, FRAC_ROLE, (i.size / biggest) if biggest > 0 and i.size > 0 else None)
            it.setTextAlignment(1, RIGHT)
            it.setToolTip(0, i.path)
            paint_rating(it, 2, ent.rating)
            it.setForeground(3, grey)
            if locked:
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                it.setForeground(0, grey)
            else:
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                            | Qt.ItemFlag.ItemIsUserCheckable)
                if parent_checked:
                    ent.checked = True
                it.setCheckState(0, Qt.CheckState.Checked if ent.checked else Qt.CheckState.Unchecked)
            if i.is_dir:
                QTreeWidgetItem(it, ["…"])
        if extra:
            QTreeWidgetItem(parent, [f"… i {extra} więcej (najmniejszych) - użyj wyszukiwania w menedżerze plików"])

    def _file_checked(self, item) -> None:
        ent = item.data(0, ENTRY_ROLE)
        if ent is None:
            return
        state = item.checkState(0) == Qt.CheckState.Checked
        ent.checked = state
        ent.touched = True
        for j in range(item.childCount()):  # wczytane dzieci podazaja za folderem
            ch = item.child(j)
            ce = ch.data(0, ENTRY_ROLE)
            if ce is not None and ce.rating != kb.KEEP:
                ce.checked = state
                ch.setCheckState(0, Qt.CheckState.Checked if state else Qt.CheckState.Unchecked)
                self._file_checked(ch)

    def _rebind_file_rows(self) -> None:
        """Po nowej analizie file_entries trzyma NOWE obiekty Entry, a wiersze 'Wszystkie pliki' - stare: bez tego
        zaznaczenie w tej zakladce nie trafialoby do wyboru. Przepinamy wiersze na aktualne wpisy (wolac pod _guard)."""
        for i in range(self.files_tree.topLevelItemCount()):
            for ch in self._walk_files(self.files_tree.topLevelItem(i)):
                old = ch.data(0, ENTRY_ROLE)
                cur = self.file_entries.get(old.paths[0]) if old is not None and old.paths else None
                if cur is not None and cur is not old:
                    ch.setData(0, ENTRY_ROLE, cur)
                    ch.setCheckState(0, Qt.CheckState.Checked if cur.checked else Qt.CheckState.Unchecked)

    def _walk_files(self, item):
        for j in range(item.childCount()):
            ch = item.child(j)
            if ch.data(0, ENTRY_ROLE) is not None:
                yield ch
            yield from self._walk_files(ch)

    def _children(self, top):
        for j in range(top.childCount()):
            ch = top.child(j)
            if ch.data(0, ENTRY_ROLE) is not None:
                yield ch

    def _each_child(self, tree=None):
        for t in ([tree] if tree is not None else [self.adv_tree, self.tree]):
            for i in range(t.topLevelItemCount()):
                top = t.topLevelItem(i)
                for ch in self._children(top):
                    yield top, ch

    def _sync_parent(self, top) -> None:
        kids = list(self._children(top))
        n = len(kids)
        checked = sum(1 for k in kids if k.checkState(0) == Qt.CheckState.Checked)
        if checked == 0:
            state = Qt.CheckState.Unchecked
        elif checked == n:
            state = Qt.CheckState.Checked
        else:
            state = Qt.CheckState.PartiallyChecked
        top.setCheckState(0, state)

    def _refresh_checks(self) -> None:
        """Po przejsciu na inna zakladke: pokaz aktualny stan zaznaczen (wspolne obiekty)."""
        self._guard = True
        try:
            for t in (self.adv_tree, self.tree):
                for top, ch in self._each_child(t):
                    e = ch.data(0, ENTRY_ROLE)
                    ch.setCheckState(0, Qt.CheckState.Checked if e.checked else Qt.CheckState.Unchecked)
                for i in range(t.topLevelItemCount()):
                    self._sync_parent(t.topLevelItem(i))
            for i in range(self.files_tree.topLevelItemCount()):
                for ch in self._walk_files(self.files_tree.topLevelItem(i)):
                    e = ch.data(0, ENTRY_ROLE)
                    if e.rating != kb.KEEP:
                        ch.setCheckState(0, Qt.CheckState.Checked if e.checked else Qt.CheckState.Unchecked)
        finally:
            self._guard = False
        self.update_summary()

    def on_item_changed(self, item, col: int) -> None:
        if col != 0 or self._guard:
            return
        if item.data(0, PATH_ROLE):  # plik/folder z przegladarki
            self._guard = True
            try:
                self._file_checked(item)
            finally:
                self._guard = False
            self.update_summary()
            return
        self._guard = True
        try:
            parent = item.parent()
            if parent is None:
                state = item.checkState(0)
                if state != Qt.CheckState.PartiallyChecked:
                    for ch in self._children(item):
                        if ch.isHidden():  # filtr (szukaj/dysk/rodzaj/widok): niewidocznych wierszy nie ruszamy
                            continue
                        ch.setCheckState(0, state)
                        ch.data(0, ENTRY_ROLE).checked = state == Qt.CheckState.Checked
            else:
                e = item.data(0, ENTRY_ROLE)
                if e is not None:
                    e.checked = item.checkState(0) == Qt.CheckState.Checked
                    e.touched = True
                self._sync_parent(parent)
        finally:
            self._guard = False
        self.update_summary()

    def select_recommended(self) -> None:
        self._set_all(lambda e: e.suggested)

    def uncheck_all(self) -> None:
        self._set_all(lambda _e: False)

    def _set_all(self, rule) -> None:
        self._guard = True
        for _top, ch in self._each_child():
            e = ch.data(0, ENTRY_ROLE)
            e.checked = bool(rule(e))
            ch.setCheckState(0, Qt.CheckState.Checked if e.checked else Qt.CheckState.Unchecked)
        for t in (self.adv_tree, self.tree):
            for i in range(t.topLevelItemCount()):
                self._sync_parent(t.topLevelItem(i))
        for i in range(self.files_tree.topLevelItemCount()):
            for ch in self._walk_files(self.files_tree.topLevelItem(i)):
                fe = ch.data(0, ENTRY_ROLE)
                if fe.rating != kb.KEEP:
                    fe.checked = bool(rule(fe))
                    ch.setCheckState(0, Qt.CheckState.Checked if fe.checked else Qt.CheckState.Unchecked)
        for fe in self.file_entries.values():
            if fe.rating != kb.KEEP:
                fe.checked = bool(rule(fe))
        self._guard = False
        self.update_summary()

    def extra_entries(self) -> list:
        """Pliki wybrane recznie (bez tych, ktore sa juz w 'Polecane')."""
        adv = {id(e) for c in self.adv_cats for e in c.entries}
        return [e for e in self.file_entries.values() if id(e) not in adv]

    def selected_entries(self) -> list:
        return viewmodel.cleanup_summary(self.all_cats(), self.extra_entries())["selected"]

    def _tint_rows(self) -> None:
        """Zaznaczone do usuniecia wiersze maja czerwonawe tlo i pogrubiona nazwe - widac na pierwszy rzut oka, co zniknie."""
        on = QBrush(QColor(201, 58, 70, 46))
        off = QBrush()
        was, self._guard = self._guard, True  # zmiana czcionki/tla wywoluje itemChanged - nie traktuj tego jak klikniecia
        try:
            for _top, ch in self._each_child():
                e = ch.data(0, ENTRY_ROLE)
                checked = bool(e is not None and e.checked)
                f = ch.font(0)
                if f.bold() != checked:
                    f.setBold(checked)
                    ch.setFont(0, f)
                for col in range(4):
                    ch.setBackground(col, on if checked else off)
        finally:
            self._guard = was

    def update_summary(self) -> None:
        s = viewmodel.cleanup_summary(self.all_cats(), self.extra_entries())
        if not s["n_delete"]:
            self.sum_big.setText("Nic nie zaznaczono")
            self.sum_small.setText(f"Zostawię wszystko ({s['n_keep']} "
                                   f"{plural(s['n_keep'], 'znaleziona pozycja', 'znalezione pozycje', 'znalezionych pozycji')}).")
        else:
            word = plural(s["n_delete"], "pozycja", "pozycje", "pozycji")
            self.sum_big.setText(
                f"Usunę: {fmt_size(s['size_delete'])}" if s["size_delete"] > 0 else f"Usunę: {s['n_delete']}")
            small = f"{s['n_delete']} {word}  ·  zostawię {s['n_keep']} ({fmt_size(s['size_keep'])})"
            try:
                free = shutil.disk_usage(str(core.HOME)).free
                if s["size_delete"] > 0:
                    small += f"  ·  wolne miejsce: {fmt_size(free)} → ok. {fmt_size(free + s['size_delete'])}"
            except OSError:
                pass
            if s["n_root"]:
                small += f"  ·  {s['n_root']} wymaga hasła administratora"
            if s["n_warn"]:
                small += f"  ·  ⚠ {s['n_warn']} dotyczy działającego programu"
            if s["n_mine"]:
                small += f"  ·  {s['n_mine']} to Twoje pliki"
            self.sum_small.setText(small)
        per = viewmodel.disk_summary(self.all_cats(), self.extra_entries())
        self.sum_disks.setText("Z dysków: " + "  ·  ".join(f"{d} {fmt_size(sz)}" for d, _n, sz in per)
                               if len(per) > 1 else "")
        self.sum_plan.setText(viewmodel.plan_line(s["selected"], self.trash_box.isChecked(), fmt_size))
        self.sum_plan.setVisible(bool(self.sum_plan.text()))
        total = s["size_delete"] + s["size_keep"]
        self.ring.set_value(s["size_delete"] / total if total else 0.0,
                            fmt_size(s["size_delete"]) if s["size_delete"] > 0 else "0")
        nrej = len(self.rejected_entries())
        self.btn_rejected.setText(f"Odrzucone przez recenzenta ({nrej})")
        self.btn_rejected.setVisible(nrej > 0)
        self.btn_clean.setEnabled(bool(s["n_delete"]) and not self.win.busy)
        self.btn_report.setEnabled(bool(self.all_cats()))
        self.btn_plan.setEnabled(bool(s["n_delete"]))
        self._tint_rows()
        if self._cur_entry is not None:
            self.panel.set_decision(self._cur_entry)
        if self.view_combo.currentData() is not None:  # widok 'tylko zaznaczone/zostawione' odswieza sie przy kazdej zmianie
            self.apply_filter(self.filter.text())

    def on_select(self, item, _prev) -> None:
        if item is None:
            return
        e = item.data(0, ENTRY_ROLE)
        self._cur_entry = e if (e is not None and e.kind == "path" and e.paths) else None
        self.btn_ai.setEnabled(self._cur_entry is not None)
        if self._cur_entry is not None:
            self.panel.set_entry(self._cur_entry)
        else:
            self.panel.clear()
        if e is not None:
            self.details.setText(viewmodel.entry_details(e))
        elif item.data(0, SECTION_ROLE) is not None:
            self.details.setText("Rozwiń, żeby zobaczyć wszystkie pliki i foldery tego dysku. "
                                 "Każdy ma ocenę; zaznacz to, co chcesz usunąć.")
        elif item.parent() is None:
            self.details.setText(item.text(3))
        else:
            self.details.setText(item.text(0).replace("🔒 ", "") + "\n" + item.text(3)
                                 + "\nOcena: Nie ruszaj - program tego nie usuwa.")

    def set_current_checked(self, value: bool) -> None:
        """Przyciski panelu: zaznacz / odznacz biezaca pozycje (z reka - ma pierwszenstwo przed AI)."""
        e = self._cur_entry
        if e is None or not e.deletable:
            return
        item = self.adv_items.get(e.paths[0])
        if item is not None:
            item.setCheckState(0, Qt.CheckState.Checked if value else Qt.CheckState.Unchecked)
        else:
            e.checked = value
            e.touched = True
            self.update_summary()

    def apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        disk = self.disk_combo.currentData()
        group = self.group_combo.currentData()
        view = self.view_combo.currentData()
        for i in range(self.files_tree.topLevelItemCount()):
            top = self.files_tree.topLevelItem(i)
            sec = top.data(0, SECTION_ROLE)
            dsk = (sec[1] or "") if sec is not None else ""
            top.setHidden(disk is not None and dsk != disk)
        for tree in (self.adv_tree, self.tree):
            for i in range(tree.topLevelItemCount()):
                top = tree.topLevelItem(i)
                visible = 0
                for j in range(top.childCount()):
                    ch = top.child(j)
                    e = ch.data(0, ENTRY_ROLE)
                    hay = (e.label + " " + e.note + " " + e.what + " " + " ".join(e.reasons)) if e is not None \
                        else ch.text(0)
                    match = (not needle) or needle in hay.lower()
                    if disk is not None:  # wybrany dysk: tylko jego pozycje (chronione wiersze ukryte)
                        match = match and e is not None and e.disk == disk
                    if group is not None:  # wybrany rodzaj: duplikaty, instalatory, foldery, stare pliki
                        match = match and e is not None and bool(entry_groups(e) & group)
                    if view is not None:  # tylko zaznaczone do usuniecia albo tylko zostawione
                        match = match and e is not None and (bool(e.checked) == (view == "checked"))
                    ch.setHidden(not match)
                    visible += 1 if (match and e is not None) else 0
                top.setHidden((bool(needle) or disk is not None or group is not None or view is not None) and visible == 0)
                if (needle or disk is not None or group is not None or view is not None) and visible:
                    top.setExpanded(True)

    def _toggle_expand(self, item, _col: int) -> None:
        if item.childCount():
            item.setExpanded(not item.isExpanded())

    def show_menu(self, tree, pos) -> None:
        item = tree.itemAt(pos)
        if item is None:
            return
        e = item.data(0, ENTRY_ROLE)
        if not e or not e.paths:
            return
        menu = QMenu(self)
        act = menu.addAction(i18n.tr("Otwórz w menedżerze plików"))
        ign = menu.addAction(i18n.tr("Nie proponuj tego więcej")) if tree is self.adv_tree else None
        prot = menu.addAction(i18n.tr("Zawsze zostaw (dodaj do chronionych)")) if tree is self.adv_tree else None
        ask = menu.addAction("Zapytaj asystenta AI …") if tree is not self.tree else None
        chosen = menu.exec(tree.viewport().mapToGlobal(pos))
        if chosen == act:
            open_in_file_manager(e.paths[0])
        elif ign is not None and chosen == ign:
            self.ignore_entry(item)
        elif prot is not None and chosen == prot:
            self.protect_entry(item)
        elif ask is not None and chosen == ask:
            self.win.ask_ai(e)


class PhotosPage(QWidget):
    """Podobne zdjecia (np. serie ujec, zrzuty ekranu w kilku wersjach). Nic nie jest zaznaczane samo;
    'Zaznacz slabsze kopie' zostawia w kazdej grupie najwieksza rozdzielczosc, a usuwanie idzie do kosza."""
    PHOTO_ROLE = int(Qt.ItemDataRole.UserRole.value) + 5

    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        self.worker = None
        self.folder = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addLayout(page_header("Podobne zdjęcia",
                                  "Znajduje zdjęcia prawie takie same (inna rozdzielczość, kompresja, drobne różnice). "
                                  "Nic nie jest zaznaczane samo, a usunięte trafiają do kosza."))
        top = QHBoxLayout()
        self.btn_folder = QPushButton("Wybierz folder …")
        self.btn_folder.clicked.connect(self.pick_folder)
        self.lbl_folder = QLabel("")
        self.lbl_folder.setObjectName("muted")
        self.btn_scan = QPushButton("Szukaj podobnych")
        self.btn_scan.setObjectName("primary")
        self.btn_scan.clicked.connect(self.scan)
        top.addWidget(self.btn_folder)
        top.addWidget(self.lbl_folder, 1)
        top.addWidget(self.btn_scan)
        lay.addLayout(top)
        body = QHBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Zdjęcie", "Rozdzielczość", "Rozmiar"])
        self.tree.setColumnWidth(0, 420)
        self.tree.currentItemChanged.connect(self.on_select)
        self.tree.itemChanged.connect(lambda *_: self._sync())
        body.addWidget(self.tree, 1)
        self.preview = PreviewWidget(300)
        self.preview.setFixedWidth(340)
        body.addWidget(self.preview)
        lay.addLayout(body, 1)
        row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.btn_weak = QPushButton("Zaznacz słabsze kopie")
        self.btn_weak.clicked.connect(self.select_weaker)
        self.btn_trash = QPushButton("Przenieś zaznaczone do kosza")
        self.btn_trash.setObjectName("danger")
        self.btn_trash.clicked.connect(self.trash_selected)
        row.addWidget(self.status, 1)
        row.addWidget(self.btn_weak)
        row.addWidget(self.btn_trash)
        lay.addLayout(row)
        self.set_folder(str(core.HOME / ("Obrazy" if (core.HOME / "Obrazy").is_dir() else "Pictures")))
        self._sync()

    def set_folder(self, path: str) -> None:
        self.folder = path
        self.lbl_folder.setText(viewmodel.short_path(path))

    def pick_folder(self, *_a) -> None:
        d = QFileDialog.getExistingDirectory(self, "Folder ze zdjęciami", self.folder)
        if d:
            self.set_folder(d)

    def scan(self, *_a) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            return
        self.tree.clear()
        self.status.setText("Szukam …")
        self.btn_scan.setText(i18n.tr("Przerwij"))
        self.worker = PhotoWorker([self.folder])
        self.worker.progress.connect(lambda i, n: self.status.setText(f"Sprawdzam zdjęcia: {i} z {n}"))
        self.worker.done.connect(self.fill)
        self.worker.failed.connect(lambda m: self.status.setText(m))
        self.worker.finished.connect(lambda: self.btn_scan.setText("Szukaj podobnych"))
        self.worker.start()

    def fill(self, groups: list) -> None:
        self._guard = True
        self.tree.clear()
        for n, g in enumerate(groups, 1):
            top = QTreeWidgetItem(self.tree, [f"Grupa {n}: {len(g)} podobnych zdjęć", "", fmt_size(sum(x[3] for x in g))])
            for info in sorted(g, key=lambda x: -(x[1] * x[2])):
                ch = QTreeWidgetItem(top, [viewmodel.short_path(info[0]), f"{info[1]}×{info[2]}", fmt_size(info[3])])
                ch.setFlags(ch.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                ch.setCheckState(0, Qt.CheckState.Unchecked)
                ch.setData(0, self.PHOTO_ROLE, info)
            top.setExpanded(True)
        self._guard = False
        self.status.setText(f"Znaleziono {len(groups)} grup." if groups else "Nie znalazłem podobnych zdjęć.")
        self._sync()

    def _items(self) -> list:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            out += [top.child(j) for j in range(top.childCount())]
        return out

    def _sync(self) -> None:
        n = sum(1 for it in self._items() if it.checkState(0) == Qt.CheckState.Checked)
        self.btn_trash.setEnabled(n > 0)
        self.btn_weak.setEnabled(self.tree.topLevelItemCount() > 0)

    def on_select(self, item, _prev) -> None:
        info = item.data(0, self.PHOTO_ROLE) if item is not None else None
        self.preview.show_path(info[0] if isinstance(info, tuple) else "")

    def select_weaker(self, *_a) -> None:
        from . import simimg
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            kids = [top.child(j) for j in range(top.childCount())]
            weak = set(simimg.weaker_copies([k.data(0, self.PHOTO_ROLE) for k in kids]))
            for k in kids:
                k.setCheckState(0, Qt.CheckState.Checked if k.data(0, self.PHOTO_ROLE)[0] in weak else Qt.CheckState.Unchecked)
        self._sync()

    def trash_selected(self, *_a) -> None:
        sel = [it.data(0, self.PHOTO_ROLE) for it in self._items() if it.checkState(0) == Qt.CheckState.Checked]
        if not sel:
            return
        total = sum(x[3] for x in sel)
        if QMessageBox.question(self, "TidyDisk",
                                f"Przenieść do kosza {len(sel)} zdjęć (ok. {fmt_size(total)})?\nMożna je przywrócić z kosza lub ze strony Historia.") \
                != QMessageBox.StandardButton.Yes:
            return
        done, journal = 0, []
        for info in sel:
            ok, why = core.is_user_target(info[0])
            errs: list = []
            if ok:
                core.trash_path(info[0], errs)
            if ok and not errs:
                done += 1
                journal.append({"label": os.path.basename(info[0]), "size": info[3], "paths": [info[0]], "how": "trash"})
        history.record(journal, 0, sum(j["size"] for j in journal))
        self.status.setText(f"Przeniesiono do kosza: {done} z {len(sel)}.")
        self.scan()


HOW_LABEL = {"trash": "do kosza (można przywrócić)", "delete": "usunięte na stałe", "command": "polecenie systemowe"}


class HistoryPage(QWidget):
    """Dziennik czyszczen: kiedy, ile, co i jak. Pozycje przeniesione do kosza mozna stad przywrocic."""

    def __init__(self, directory=None) -> None:
        super().__init__()
        self.directory = directory
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addLayout(page_header("Historia czyszczenia",
                                  "Co i kiedy zostało usunięte. Rzeczy przeniesione do kosza możesz przywrócić."))
        self.chart = SpaceChart()
        lay.addWidget(self.chart)
        self.growth = QLabel("")
        self.growth.setObjectName("muted")
        lay.addWidget(self.growth)
        sched = QHBoxLayout()
        self.sched_label = QLabel("")
        self.sched_label.setObjectName("muted")
        self.btn_sched_on = QPushButton("Włącz cotygodniowe powiadomienia")
        self.btn_sched_on.setToolTip("Timer systemd użytkownika: raz w tygodniu sprawdza dysk i powiadamia, "
                                     "gdy jest mało miejsca albo dużo do bezpiecznego odzyskania. Nic nie usuwa.")
        self.btn_sched_on.clicked.connect(self.sched_enable)
        self.btn_sched_off = QPushButton("Wyłącz")
        self.btn_sched_off.clicked.connect(self.sched_disable)
        sched.addWidget(self.sched_label, 1)
        sched.addWidget(self.btn_sched_on)
        sched.addWidget(self.btn_sched_off)
        lay.addLayout(sched)
        ai_row = QHBoxLayout()
        self.ai_sched_label = QLabel("")
        self.ai_sched_label.setObjectName("muted")
        self.ai_sched_label.setWordWrap(True)
        self.ai_every = QComboBox()
        for label, key in (("Codziennie", "daily"), ("Co tydzień", "weekly"), ("Co miesiąc", "monthly")):
            self.ai_every.addItem(label, key)
        self.ai_every.setCurrentIndex(1)
        self.ai_every.setAccessibleName("Jak często oceniać przez AI w tle")
        self.ai_at = QLineEdit("03:00")
        self.ai_at.setFixedWidth(70)
        self.ai_at.setAccessibleName("Godzina oceny AI w tle (GG:MM)")
        self.btn_ai_on = QPushButton("Włącz ocenę AI w tle")
        self.btn_ai_on.setToolTip("Timer systemd użytkownika: o wybranej porze skanuje dysk i ocenia go przez AI "
                                  "(najniższy priorytet), potem powiadamia. Niczego nie usuwa.")
        self.btn_ai_on.clicked.connect(self.ai_sched_enable)
        self.btn_ai_off = QPushButton("Wyłącz")
        self.btn_ai_off.clicked.connect(self.ai_sched_disable)
        ai_row.addWidget(self.ai_sched_label, 1)
        ai_row.addWidget(self.ai_every)
        ai_row.addWidget(self.ai_at)
        ai_row.addWidget(self.btn_ai_on)
        ai_row.addWidget(self.btn_ai_off)
        lay.addLayout(ai_row)
        self.changes_label = QLabel("")
        self.changes_label.setObjectName("muted")
        self.changes_label.setWordWrap(True)
        self.changes_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.changes_label)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Kiedy / pozycja", "Rozmiar", "Jak"])
        self.tree.setColumnWidth(0, 520)
        self.tree.setColumnWidth(1, 100)
        self.tree.currentItemChanged.connect(lambda *_: self._sync())
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.btn_restore = QPushButton("Przywróć z kosza")
        self.btn_restore.clicked.connect(self.restore_selected)
        row.addWidget(self.status, 1)
        row.addWidget(self.btn_restore)
        lay.addLayout(row)
        self.refresh()

    def sched_enable(self, *_a) -> None:
        self.sched_label.setText("Powiadomienia: " + schedule.enable("weekly"))
        self._sched_sync()

    def sched_disable(self, *_a) -> None:
        self.sched_label.setText("Powiadomienia: " + schedule.disable())
        self._sched_sync()

    def _sched_sync(self) -> None:
        on = schedule.is_enabled()
        self.btn_sched_on.setEnabled(not on)
        self.btn_sched_off.setEnabled(on)
        ai_on = schedule.is_ai_enabled()
        self.btn_ai_on.setEnabled(not ai_on)
        self.btn_ai_off.setEnabled(ai_on)
        self.changes_label.setText(changes.describe(home=str(core.HOME), limit=6))
        last = background.describe_last()
        self.ai_sched_label.setText("Ocena AI w tle: " + ("włączona" if ai_on else "wyłączona") + (f". {last}" if last else ""))

    def ai_sched_enable(self, *_a) -> None:
        at = self.ai_at.text().strip()
        try:
            msg = schedule.enable_ai(self.ai_every.currentData() or "weekly", at)
        except (ValueError, KeyError):
            self.ai_sched_label.setText("Podaj godzinę w formacie GG:MM, np. 03:00.")
            return
        self._sched_sync()
        self.ai_sched_label.setText(self.ai_sched_label.text() + f" ({msg})")

    def ai_sched_disable(self, *_a) -> None:
        schedule.disable_ai()
        self._sched_sync()

    def refresh(self) -> None:
        pts = spacelog.load(self.directory)
        self.chart.set_points(pts)
        g, days = spacelog.growth(pts)
        self.growth.setText(f"Przez ostatnie {days} dni zajęte miejsce {'wzrosło' if g >= 0 else 'spadło'} o {fmt_size(abs(g))}."
                            if days else "")
        if not self.sched_label.text():
            self.sched_label.setText("Powiadomienia: " + ("włączone" if schedule.is_enabled() else "wyłączone"))
        self._sched_sync()
        self.tree.clear()
        runs = history.load(self.directory)
        if not runs:
            self.status.setText("Brak zapisanych czyszczeń.")
        for r in runs:
            when = time.strftime("%d.%m.%Y %H:%M", time.localtime(r.get("ts", 0)))
            top = QTreeWidgetItem(self.tree, [f"{when}  ·  {len(r['items'])} pozycji",
                                             fmt_size(int(r.get("freed", 0)) + int(r.get("trashed", 0))), ""])
            for it in r["items"]:
                ch = QTreeWidgetItem(top, [it["label"] + ("  (przywrócone)" if it.get("restored") else ""),
                                          fmt_size(int(it.get("size", 0))), HOW_LABEL.get(it.get("how"), "")])
                ch.setData(0, ENTRY_ROLE, (r.get("ts", 0), it))
        self._sync()

    def _sync(self) -> None:
        cur = self.tree.currentItem()
        d = cur.data(0, ENTRY_ROLE) if cur is not None else None
        self.btn_restore.setEnabled(isinstance(d, tuple) and d[1].get("how") == "trash" and not d[1].get("restored"))

    def restore_selected(self, *_a) -> None:
        cur = self.tree.currentItem()
        d = cur.data(0, ENTRY_ROLE) if cur is not None else None
        if not isinstance(d, tuple):
            return
        ts, it = d
        ok_n, msgs = 0, []
        for p in it["paths"]:
            ok, msg = history.restore_from_trash(p)
            ok_n += ok
            if ok:
                history.mark_restored(ts, p, self.directory)
            else:
                msgs.append(msg)
        self.status.setText(f"Przywrócono {ok_n} z {len(it['paths'])}." + (" " + msgs[0] if msgs else ""))
        self.refresh()


class ReviewDialog(QDialog):
    """Pyta o kazda pozycje po kolei: usunac czy zostawic. Domyslny przycisk to bezpieczne 'Zostaw'."""

    def __init__(self, parent, session: "viewmodel.ReviewSession") -> None:
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("Czy usunąć?")
        self.setMinimumSize(720, 520)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        self.counter = QLabel()
        self.counter.setObjectName("muted")
        self.title = QLabel()
        self.title.setObjectName("bigtext")
        self.title.setWordWrap(True)
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.info = QPlainTextEdit()
        self.info.setReadOnly(True)
        self.preview = PreviewWidget(260)
        self.bar = QProgressBar()
        self.bar.setObjectName("meter")
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        lay.addWidget(self.counter)
        lay.addWidget(self.title)
        lay.addWidget(self.bar)
        lay.addWidget(self.preview)
        lay.addWidget(self.info, 1)
        row = QHBoxLayout()
        self.btn_open = QPushButton("Otwórz folder")
        self.btn_open.clicked.connect(self._open)
        self.btn_keep_rest = QPushButton("Zostaw resztę")
        self.btn_keep_rest.clicked.connect(lambda: self._act("keep_rest"))
        self.btn_del_rest = QPushButton("Usuń resztę")
        self.btn_del_rest.setToolTip("Usuwa tę i wszystkie pozostałe pozycje bez dalszych pytań.")
        self.btn_del_rest.clicked.connect(lambda: self._act("delete_rest"))
        self.btn_abort = QPushButton(i18n.tr("Przerwij"))
        self.btn_abort.clicked.connect(lambda: self._act("abort"))
        self.btn_delete = QPushButton("Usuń")
        self.btn_delete.setObjectName("primary")
        self.btn_delete.clicked.connect(lambda: self._act("delete"))
        self.btn_keep = QPushButton("Zostaw")
        self.btn_keep.setDefault(True)
        self.btn_keep.setAutoDefault(True)
        self.btn_keep.clicked.connect(lambda: self._act("keep"))
        for w in (self.btn_open, self.btn_abort):
            row.addWidget(w)
        row.addStretch(1)
        for w in (self.btn_keep_rest, self.btn_del_rest, self.btn_keep, self.btn_delete):
            row.addWidget(w)
        lay.addLayout(row)
        self.btn_keep.setFocus()
        self._show()

    def _show(self) -> None:
        s = self.session
        e = s.current
        if e is None:
            self.accept()
            return
        self.counter.setText(f"Pozycja {s.i + 1} z {s.total}  ·  do usunięcia dotąd: {len(s.approved)}")
        self.bar.setRange(0, max(s.total, 1))
        self.bar.setValue(s.i)
        self.title.setText(e.label)
        preview = None
        if e.kind == "path" and e.paths and os.path.isfile(e.paths[0]):
            preview = ai.peek(e.paths[0], e.size)
        self.info.setPlainText(viewmodel.review_text(e, preview))
        self.preview.show_path(e.paths[0] if (e.kind == "path" and len(e.paths) == 1) else "")
        self.btn_open.setEnabled(bool(e.kind == "path" and e.paths))

    def _act(self, action: str) -> None:
        if self.session.decide(action):
            self.reject() if self.session.aborted else self.accept()
        else:
            self._show()

    def _open(self) -> None:
        e = self.session.current
        if e is not None and e.paths:
            open_in_file_manager(e.paths[0])

    def done(self, r) -> None:  # noqa: D102 - sprzatanie podgladu przy kazdym zamknieciu
        self.preview.cleanup()
        super().done(r)

    def reject(self) -> None:  # zamkniecie okna krzyzykiem = przerwanie, nic nie jest usuwane
        self.session.aborted = True
        self.session.approved = []
        super().reject()


# -------------------------------------------------------------------- okno --

class MainWindow(QMainWindow):
    NAV = ["Dyski i partycje", "Foldery i pliki", "Największe pliki", "Mapa dysku", "Sprzątanie", "Podobne zdjęcia", "Historia", "Ustawienia"]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TidyDisk")
        self.setWindowIcon(app_icon())
        self.resize(1180, 800)
        self.setMinimumSize(980, 620)

        self.busy = False  # skan sprzatania lub czyszczenie
        self.dscan_busy = False  # skan calego dysku
        self.analysis_busy = False  # analiza plikow (Polecane)
        self._reanalyze = True  # po kazdym skanie sprzatania, dopoki nie ma swiezej analizy
        self.analyzer: AnalysisWorker | None = None
        self.ai_worker: AIWorker | None = None
        self.triage_worker: AITriageWorker | None = None
        self.triage_busy = False
        self.analysis_res = None
        self._dry_last = False
        self._banner: tuple | None = None
        self.scan_result = None
        self.scanner: ScanWorker | None = None
        self.cleaner: CleanWorker | None = None
        self.dscanner: DiskScanWorker | None = None
        self.settings = QSettings("tidydisk", "tidydisk")
        self._syncing = False

        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_sidebar())
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(22, 18, 22, 16)
        rl.setSpacing(12)
        rl.addLayout(self._build_meters())
        rl.addWidget(self._build_scanbar())

        self.pages = QStackedWidget()
        self.disks_page = DisksPage()
        self.folders_page = FoldersPage()
        self.files_page = FilesPage()
        self.clean_page = CleanupPage(self)
        self.map_page = MapPage(self)
        self.photos_page = PhotosPage(self)
        self.history_page = HistoryPage()
        self.settings_page = SettingsPage(self)
        self.settings_page.saved.connect(self.on_settings_saved)
        for p in (self.disks_page, self.folders_page, self.files_page, self.map_page, self.clean_page,
                  self.photos_page, self.history_page, self.settings_page):
            self.pages.addWidget(p)
        rl.addWidget(self.pages, 1)
        outer.addWidget(right, 1)

        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self.start_scan)
        QShortcut(QKeySequence("F5"), self).activated.connect(self.start_scan)
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self.quit_app)
        self._quitting = False
        self.tray = None
        self._init_tray()
        self._init_status_bar()
        self._announce_background_run()
        for i in range(len(self.NAV)):  # Ctrl+1..8 - strony, Ctrl+, - ustawienia, Ctrl+F - szukaj na liscie sprzatania
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self).activated.connect(lambda i=i: self.nav.setCurrentRow(i))
        QShortcut(QKeySequence("Ctrl+,"), self).activated.connect(self.show_settings)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.focus_search)
        QShortcut(QKeySequence("F1"), self).activated.connect(self.show_shortcuts)
        for keys, action in (("Ctrl+Return", self.start_clean_from_keyboard), ("Ctrl+Shift+R", self.recommend_from_keyboard),
                             ("Ctrl+Shift+D", self.uncheck_from_keyboard)):
            QShortcut(QKeySequence(keys), self).activated.connect(action)

        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)

        self.on_settings_saved(settings.apply(settings.load()))
        self.nav.setCurrentRow(PAGE_DISKS)
        self.update_disks()
        self.start_scan()

    # -- budowa
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setFixedWidth(210)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        brand = QFrame()
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(18, 18, 18, 10)
        pix = QLabel()
        pix.setPixmap(app_icon().pixmap(QSize(38, 38)))
        name = QLabel("TidyDisk")
        name.setObjectName("bigtext")
        bl.addWidget(pix)
        bl.addWidget(name, 1)
        lay.addWidget(brand)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFrameShape(QFrame.Shape.NoFrame)
        self.nav.setAccessibleName("Główna nawigacja")
        icons = [(["drive-harddisk"], QStyle.StandardPixmap.SP_DriveHDIcon),
                 (["folder"], QStyle.StandardPixmap.SP_DirIcon),
                 (["text-x-generic", "document-properties"], QStyle.StandardPixmap.SP_FileIcon),
                 (["view-list-icons", "map-globe"], QStyle.StandardPixmap.SP_FileDialogContentsView),
                 (["edit-clear-all", "trash-empty"], QStyle.StandardPixmap.SP_TrashIcon),
                 (["image-x-generic", "camera-photo"], QStyle.StandardPixmap.SP_FileDialogContentsView),
                 (["view-history", "document-open-recent"], QStyle.StandardPixmap.SP_BrowserReload),
                 (["preferences-system", "configure"], QStyle.StandardPixmap.SP_FileDialogDetailedView)]
        for title, (names, fb) in zip(self.NAV, icons):
            it = QListWidgetItem(themed(names, fb), i18n.tr(title))
            it.setSizeHint(QSize(0, 44))
            self.nav.addItem(it)
        self.nav.currentRowChanged.connect(self.on_nav)
        lay.addWidget(self.nav, 1)
        ver = QLabel(f"wersja {__version__}")
        ver.setObjectName("muted")
        ver.setContentsMargins(18, 8, 18, 12)
        lay.addWidget(ver)
        return side

    def _build_meters(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(24)
        self.meters: list = []
        for mount in core.disk_info():
            m = DiskMeter(mount)
            self.meters.append(m)
            row.addWidget(m)
        row.addStretch(1)
        return row

    def _build_scanbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("footer")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(10)
        self.dscan_label = QLabel("Foldery i pliki wymagają przeskanowania dysku.")
        self.dscan_label.setObjectName("muted")
        lay.addWidget(self.dscan_label, 1)
        self.dscan_bar = QProgressBar()
        self.dscan_bar.setObjectName("busy")
        self.dscan_bar.setTextVisible(False)
        self.dscan_bar.setRange(0, 1)
        self.dscan_bar.setFixedSize(90, 6)
        lay.addWidget(self.dscan_bar)
        self.scan_combo = QComboBox()
        self.scan_combo.setToolTip(
            "Wybierz, co przeskanować. Cały dysk (administrator) przeszukuje wszystkie pliki - "
            "wymaga hasła i może potrwać kilka minut. Skaner tylko czyta, niczego nie usuwa.")
        self.fill_scan_targets()
        self.scan_combo.currentIndexChanged.connect(self.on_scan_target)
        lay.addWidget(self.scan_combo)
        self.btn_scan = QPushButton("Skanuj")
        self.btn_scan.clicked.connect(self.start_selected_scan)
        self.btn_cancel = QPushButton(i18n.tr("Przerwij"))
        self.btn_cancel.clicked.connect(self.cancel_disk_scan)
        self.btn_cancel.hide()
        lay.addWidget(self.btn_scan)
        lay.addWidget(self.btn_cancel)
        self.scanbar = frame
        frame.hide()
        return frame

    def fill_scan_targets(self) -> None:
        """Lista celow skanowania: dom, kazdy dodatkowy dysk, caly system."""
        labels = disks.mount_labels()
        self.scan_combo.clear()
        self.scan_combo.addItem("Mój profil użytkownika" if osal.is_windows() else "Mój katalog domowy", ("user", str(core.HOME)))
        for mp in core.data_mounts():
            self.scan_combo.addItem(f"Dysk {mp}  ({labels.get(mp, mp)})", ("user", mp))
        if osal.SYSTEM == "linux":  # skan administratora = pkexec + polkit: tylko Linux
            self.scan_combo.addItem("Cały system - wszystkie dyski (administrator)", ("admin", "/"))

    def browse_disk(self, label) -> None:
        """Przejdz do przegladarki plikow wybranego dysku (z listy w Sprzataniu)."""
        if label is None:
            return
        labels = disks.mount_labels()
        mounts = [m for m, lab in labels.items() if lab == label]
        data = set(core.data_mounts())
        root = next((m for m in mounts if m in data), None) or str(core.HOME)
        self.folders_page.set_root(root)
        self.nav.setCurrentRow(PAGE_FOLDERS)

    def on_scan_target(self, _idx: int = 0) -> None:
        data = self.scan_combo.currentData()
        if data:
            self.folders_page.set_root("/" if data[0] == "admin" else data[1])

    def start_selected_scan(self) -> None:
        mode, root = self.scan_combo.currentData()
        self.start_disk_scan(mode == "admin", root)

    def on_nav(self, row: int) -> None:
        if row < 0:
            return
        self.pages.setCurrentIndex(row)
        self.scanbar.setVisible(row in (PAGE_FOLDERS, PAGE_FILES))
        if row == PAGE_MAP:
            self.map_page.refresh()
        if row == PAGE_HISTORY:
            self.history_page.refresh()
        if row == PAGE_SETTINGS:
            self.settings_page.load(settings.load())
        if row == PAGE_DISKS:
            self.disks_page.refresh()

    # -- stan
    def update_disks(self) -> None:
        info = core.disk_info()
        spacelog.record(info)  # najwyzej raz na godzine
        for m in self.meters:
            if m.mount in info:
                used, total = info[m.mount]
                m.set_usage(used, total)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.clean_page.set_busy(busy)

    # -- skan sprzatania
    def start_scan(self) -> None:
        if self.busy:
            return
        self.clean_page.show_scanning()
        self.set_busy(True)
        self._retire("scanner")
        self.scanner = ScanWorker()
        self.scanner.status.connect(self.clean_page.scan_status.setText)
        self.scanner.done.connect(self.on_scan_done)
        self.scanner.start()

    def on_scan_done(self, cats: list) -> None:
        self.clean_page.populate(cats)
        self.set_busy(False)
        if self._reanalyze and settings.load()["auto_analysis"]:
            self.start_analysis()
        if self._banner:
            self.clean_page.show_banner(*self._banner)
            self._banner = None
        self.update_disks()

    # -- przeglad AI: model sam ocenia i zaznacza
    def toggle_triage(self) -> None:
        if self.triage_busy:
            if self.triage_worker is not None:
                self.triage_worker.cancel()
            return
        self.start_triage(auto=False)

    def start_triage(self, auto: bool = False) -> None:
        cp = self.clean_page
        res = self.analysis_res
        if self.triage_busy or res is None:
            if res is None and not auto:
                cp.show_banner("Najpierw poczekaj na analizę plików - AI ocenia jej wyniki.", "warn")
            return
        self._ai_marked = 0
        self.triage_busy = True
        cp.btn_ai_review.setText("Przerwij ocenę AI")
        cp.set_analysis_status("🤖 AI startuje (pierwsze zapytanie może potrwać - model ładuje się na kartę) …",
                               busy=True)
        self._retire("triage_worker")
        self.triage_worker = AITriageWorker(res.advice, res.nodes, res.top_files, skip=cp.ai_notes.keys())
        self.triage_worker.batch.connect(self.on_triage_batch)
        self.triage_worker.status.connect(lambda t: cp.set_analysis_status("🤖 " + t, busy=True))
        self.ai_track = ProgressTracker()
        self.triage_worker.fraction.connect(lambda f: self._progress("AI: ", self.ai_track.update(f)))
        self.triage_worker.finished_ok.connect(self.on_triage_done)
        self.triage_worker.failed.connect(lambda m: self.on_triage_failed(m, auto))
        self.triage_worker.start()

    def on_triage_batch(self, results: dict, meta: dict, done: int, total: int) -> None:
        self.clean_page.apply_ai(results, meta)

    def _triage_end(self) -> None:
        self.triage_busy = False
        if not self.analysis_busy:
            self.set_global_progress(-1)
        self.clean_page.btn_ai_review.setText("🤖 Oceń przez AI")

    def on_triage_done(self, stats) -> None:
        self._triage_end()
        self.tray_note("Ocena AI zakończona." if not stats.get("przerwano") else "Ocena AI przerwana - wyniki zapisane.")
        cp = self.clean_page
        n = sum(1 for e in cp.file_entries.values() if e.ai == "usunac" and e.checked)
        if stats.get("przerwano"):
            cp.btn_ai_review.setText("🤖 Wznów ocenę AI")
            cp.set_analysis_status(f"🤖 Przerwano. Dotychczasowe oceny są zapisane (z pamięci: {stats.get('z_pamieci', 0)}) - "
                                   "kliknij „Wznów ocenę AI”, żeby kontynuować od tego miejsca.")
            return
        cp.set_analysis_status(
            f"🤖 Gotowe. Foldery: {stats.get('keep', 0)} do zostawienia, {stats.get('dig', 0)} do przejrzenia, "
            f"{stats.get('whole', 0)} w całości zbędnych"
            + (f", bez odpowiedzi modelu: {stats['bez_odpowiedzi']}" if stats.get("bez_odpowiedzi") else "")
            + (f", z pamięci: {stats['z_pamieci']}" if stats.get("z_pamieci") else "")
            + f". Recenzent odrzucił {stats.get('odrzucone', 0)}. "
            f"Zaznaczone przez AI: {n}. Kliknij pozycję, żeby zobaczyć uzasadnienie.")

    def on_triage_failed(self, msg: str, auto: bool) -> None:
        self._triage_end()
        self.tray_note("Ocena AI nie powiodła się: " + msg[:100])
        self.clean_page.set_analysis_status(("🤖 " if msg.startswith("Nie znalazłem") else "") + msg)

    def save_quick(self, key: str, value: bool) -> None:
        """Szybki przelacznik z menu: zapisuje do ustawien (chyba ze to wlasnie synchronizacja z formularzem)."""
        if self._syncing:
            return
        cfg = settings.update({key: value})
        settings.apply(cfg)
        self.settings_page.load(cfg)

    def set_search_mode(self, mode: str) -> None:
        """Zmiana dokladnosci z paska Sprzatania: zapis, a gdy trzeba - nowa analiza lub przeglad AI."""
        old = settings.RUNTIME.get("search_mode", "assisted")
        if mode == old:
            return
        cfg = settings.update({"search_mode": mode})
        settings.apply(cfg)
        self.settings_page.load(cfg)
        cp = self.clean_page
        if "ai_only" in (old, mode):
            if self.triage_busy and self.triage_worker is not None:
                self.triage_worker.cancel()  # przegląd AI w starym trybie jest nieaktualny
            cp.ai_notes.clear()
            cp.ai_extra.clear()
            if self.analysis_busy:
                self._reanalyze = True  # trwający skan był w starym trybie - po jego końcu zrób nowy
            elif not self.busy:
                self.start_analysis()  # inne progi kandydatow i zaznaczania -> przelicz od nowa
        elif mode != "algorithm" and self.analysis_res is not None and not self.triage_busy and cp.act_ai_auto.isChecked():
            self.start_triage(auto=True)
        cp.show_banner({"algorithm": "Tryb niedokładny: tylko algorytm, bez AI.",
                        "assisted": "Tryb dokładny: algorytm + AI.",
                        "ai_only": "Tryb bardzo dokładny: lista powstaje wyłącznie z ocen AI (bez algorytmu)."}[mode])

    def focus_search(self) -> None:
        self.nav.setCurrentRow(PAGE_CLEAN)
        self.clean_page.filter.setFocus()

    SHORTCUTS = (("Ctrl+1 … Ctrl+8", "strony"), ("Ctrl+R / F5", "skanuj ponownie"),
                 ("Ctrl+F", "szukaj na liście Sprzątania"), ("Ctrl+Shift+R", "zaznacz polecane (Sprzątanie)"),
                 ("Ctrl+Shift+D", "odznacz wszystko (Sprzątanie)"),
                 ("Ctrl+Enter", "wyczyść zaznaczone (Sprzątanie; i tak pyta o potwierdzenie)"),
                 ("Spacja", "zaznacz / odznacz pozycję na liście"), ("Ctrl+,", "Ustawienia"),
                 ("Ctrl+Q", "zakończ (naprawdę)"), ("F1", "ta pomoc"))

    def shortcuts_text(self) -> str:
        return "\n".join(f"{k} - {d}" for k, d in self.SHORTCUTS)

    def _on_clean_page(self) -> bool:
        return self.nav.currentRow() == PAGE_CLEAN and not self.busy

    def start_clean_from_keyboard(self) -> None:
        if self._on_clean_page():
            self.start_clean()  # to samo co przycisk: ostrzezenia i potwierdzenia zostaja

    def recommend_from_keyboard(self) -> None:
        if self._on_clean_page():
            self.clean_page.select_recommended()

    def uncheck_from_keyboard(self) -> None:
        if self._on_clean_page():
            self.clean_page.uncheck_all()

    def show_shortcuts(self) -> None:
        QMessageBox.information(self, "Skróty klawiszowe", self.shortcuts_text() + "\n\n"
                                "Zamknięcie okna w trakcie pracy chowa program do zasobnika (Ustawienia → Praca w tle).")

    def show_settings(self) -> None:
        self.nav.setCurrentRow(PAGE_SETTINGS)

    def on_settings_saved(self, cfg: dict) -> None:
        app = QApplication.instance()
        if app is not None and cfg.get("theme") != getattr(self, "_theme", None):
            if getattr(self, "_theme", None) is not None:  # pierwszy raz motyw ustawia main()
                theme.apply(app, cfg["theme"], QSS)
            self._theme = cfg["theme"]
        self._syncing = True
        try:
            self.clean_page.apply_settings(cfg)
        finally:
            self._syncing = False

    # -- asystent AI
    def ask_ai(self, entry) -> None:
        if self.ai_worker is not None and self.ai_worker.isRunning():
            return
        cp = self.clean_page
        cp.panel.show_ai("🤖 Pytam lokalny model … (pierwsze pytanie może potrwać, model ładuje się na kartę)")
        self._retire("ai_worker")
        self.ai_worker = AIWorker(entry)
        self.ai_worker.done.connect(cp.panel.show_ai)
        self.ai_worker.failed.connect(lambda t: cp.panel.show_ai("🤖 " + t))
        self.ai_worker.start()

    # -- analiza plikow (zakladka Polecane)
    def start_analysis(self) -> None:
        if self.analysis_busy:
            return
        self.analysis_busy = True
        self._reanalyze = False
        cp = self.clean_page
        cp.set_analysis_status("Etap 1: zaczynam przeglądanie plików … Możesz w tym czasie przeglądać pozostałe zakładki.",
                               busy=True)
        self._retire("analyzer")
        self.analyzer = AnalysisWorker()
        self.analyzer.stage.connect(lambda t: cp.set_analysis_status(t, busy=True))
        self.an_track = ProgressTracker()
        self.analyzer.fraction.connect(lambda f: self._progress("Skan: ", self.an_track.update(f)))
        self.analyzer.done.connect(self.on_analysis_done)
        self.analyzer.failed.connect(self.on_analysis_failed)
        self.analyzer.start()

    def on_analysis_done(self, res) -> None:
        self.analysis_busy = False
        if not self.triage_busy:
            self.set_global_progress(-1)
        self.tray_note("Analiza plików zakończona.")
        if self._reanalyze:  # w trakcie czyszczono - wynik jest nieaktualny
            self.start_analysis()
            return
        cp = self.clean_page
        if res is None:
            cp.set_analysis_status("Analiza nie znalazła nic do sprawdzenia.")
            return
        cp.set_advice(res.advice, res.advice_notes)
        nf = f"{res.nfiles:,}".replace(",", " ")
        cp.set_analysis_status(f"{cp._adv_text}  (przeszukano {nf} plików w {res.seconds} s"
                               + (", przerwano" if res.cancelled else "") + ")")
        self.analysis_res = res
        if cp.act_ai_auto.isChecked() and not res.cancelled and settings.RUNTIME.get("search_mode") != "algorithm":
            self.start_triage(auto=True)

    def on_analysis_failed(self, msg: str) -> None:
        self.analysis_busy = False
        self.clean_page.set_analysis_status(msg)

    # -- skan calego dysku
    def start_disk_scan(self, admin: bool, root: str = "") -> None:
        if self.dscan_busy:
            return
        self.dscan_busy = True
        self.btn_scan.setEnabled(False)
        self.scan_combo.setEnabled(False)
        self.btn_cancel.setVisible(not admin)
        self.dscan_bar.setRange(0, 0)
        self.dscan_label.setText("Czekam na hasło administratora …" if admin else "Skanuję …")
        self._retire("dscanner")
        self.dscanner = DiskScanWorker(admin, root)
        self.dscanner.progress.connect(self.on_disk_progress)
        self.dscanner.done.connect(self.on_disk_done)
        self.dscanner.failed.connect(self.on_disk_failed)
        self.dscanner.start()

    def on_disk_progress(self, n: int) -> None:
        self.dscan_label.setText(f"Przeszukano {n:,} plików …".replace(",", " "))

    def cancel_disk_scan(self) -> None:
        if self.dscanner is not None:
            self.dscanner.cancel()

    def _disk_scan_finished(self) -> None:
        self.dscan_busy = False
        self.btn_scan.setEnabled(True)
        self.scan_combo.setEnabled(True)
        self.btn_cancel.hide()
        self.dscan_bar.setRange(0, 1)
        self.dscan_bar.setValue(0)

    def on_disk_done(self, res) -> None:
        self._disk_scan_finished()
        self.scan_result = res
        if res.mode == "admin" and res.advice and not self.analysis_busy:
            self.clean_page.set_advice(res.advice, res.advice_notes)
        nf = f"{res.nfiles:,}".replace(",", " ")
        self.dscan_label.setText(
            f"Przeskanowano {nf} plików ({fmt_size(res.total)}) w {res.seconds} s"
            + (f"  ·  {res.errors} miejsc niedostępnych (użyj skanu administratora)"
               if res.errors and res.mode != "admin" else "")
            + ("  ·  przerwano" if res.cancelled else ""))
        self.folders_page.set_scan(res)
        self.files_page.set_scan(res)

    def on_disk_failed(self, msg: str) -> None:
        self._disk_scan_finished()
        self.dscan_label.setText(msg)

    # -- raport
    def _report_texts(self, fmt: str) -> str:
        cp = self.clean_page
        an = report.Anon(cp.act_anon.isChecked(), cp.act_private.isChecked())
        prot = core.protected_items(self.scan_result)
        cats = cp.all_cats()
        picked = [e for e in cp.extra_entries() if e.checked and e.deletable]
        if picked:  # pliki wybrane recznie z list dyskow
            cats.append(core.Category("files", "Pliki wybrane ręcznie", "", False, picked))
        if fmt == "html":
            return export.to_html(export.data_from_cats(cats, core.disk_info(), __version__), spacelog.load())
        if fmt == "csv":
            return report.build_csv(cats, prot, an)
        return report.build_markdown(cats, prot, self.scan_result, disks.list_disks(), an,
                                     cp.dry_box.isChecked(), ai_count=len(cp.ai_notes))

    def save_report(self, fmt: str) -> None:
        text = self._report_texts(fmt)
        filt = {"md": "Markdown (*.md)", "csv": "CSV (*.csv)", "html": "HTML (*.html)"}[fmt]
        start = str(Path.home() / report.default_filename(fmt))
        path, _ = QFileDialog.getSaveFileName(self, "Zapisz raport", start, filt)
        if not path:
            return
        try:
            enc = "utf-8-sig" if fmt == "csv" else "utf-8"
            Path(path).write_text(text, encoding=enc)
        except OSError as ex:
            QMessageBox.warning(self, "TidyDisk", f"Nie udało się zapisać raportu:\n{ex}")
            return
        self.clean_page.show_banner(
            f"Zapisano raport: {viewmodel.short_path(path)} - możesz go teraz wysłać do sprawdzenia.")

    def copy_report(self) -> None:
        QApplication.clipboard().setText(self._report_texts("md"))
        self.clean_page.show_banner("Raport skopiowany do schowka - wklej go do rozmowy.")

    # -- czyszczenie
    def confirm(self, sel: list, dry: bool) -> bool:
        total = sum(e.size for e in sel)
        n_root = sum(1 for e in sel if e.root)
        n_warn = sum(1 for e in sel if e.warn)
        n_review = sum(1 for e in sel if e.rating == kb.REVIEW)
        n_mine = sum(1 for e in sel if e.rating == kb.MINE)
        to_trash = self.clean_page.trash_box.isChecked()
        word = plural(len(sel), "pozycję", "pozycje", "pozycji")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information if dry else QMessageBox.Icon.Warning)
        box.setWindowTitle("Potwierdź czyszczenie")
        size_txt = f" (ok. {fmt_size(total)})" if total > 0 else ""
        box.setText(
            f"{'Symulacja: nic nie zostanie usunięte. ' if dry else ''}"
            f"{'Sprawdzić' if dry else 'Usunąć'} {len(sel)} {word}{size_txt}?")
        info = [] if dry else ["Usuwanie jest nieodwracalne."]
        if n_root:
            info.append(f"{n_root} z pozycji wymaga hasła administratora.")
        if n_review:
            info.append(f"{n_review} z pozycji oceniłem jako „do przejrzenia” - zaznaczyłeś je sam.")
        if n_mine:
            info.append(f"⚠ {n_mine} z pozycji to Twoje pliki (dokumenty, zdjęcia, projekty…), które sam zaznaczyłeś - "
                        + ("trafią do kosza." if to_trash else "zostaną usunięte NA STAŁE."))
        if n_warn:
            info.append(f"⚠ {n_warn} z pozycji dotyczy działającego programu - zamknij go przed czyszczeniem.")
        info.append(viewmodel.plan_text(sel, to_trash, fmt_size).splitlines()[0] + ". Szczegóły w „Pokaż szczegóły”.")
        box.setInformativeText(" ".join(info))
        box.setDetailedText(viewmodel.plan_text(sel, to_trash, fmt_size) + "\n\n" + "\n".join(
            f"• {'⚠ ' if e.warn else ''}{e.label}  ({fmt_size(e.size)}, "
            f"{kb.RATING_LABEL.get(e.rating, e.rating).lower()})" for e in sel))
        go = box.addButton("Symuluj" if dry else "Wyczyść", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("Anuluj", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        return box.clickedButton() == go

    def review_each(self, sel: list):
        """Pyta o kazda pozycje po kolei. Zwraca zatwierdzone pozycje albo None po przerwaniu."""
        session = viewmodel.ReviewSession(sel)
        dlg = ReviewDialog(self, session)
        dlg.exec()
        for e in session.kept:  # zostawione: odznacz, a decyzja trafia do nauki
            e.checked = False
            e.touched = True
        self.clean_page._refresh_checks()
        return None if session.aborted else session.approved

    def start_clean(self) -> None:
        if osal.is_windows():  # w tej wersji Windows tylko skan i raport
            from . import scan_windows
            QMessageBox.information(self, "TidyDisk", scan_windows.refuse_message())
            return
        cp = self.clean_page
        sel = cp.selected_entries()
        if not sel or self.busy:
            return
        dry = cp.dry_box.isChecked()
        if not dry:  # ostrzezenie o plikach, ktore program ma teraz otwarte (np. cache przegladarki, baza danych)
            opened = openfiles.open_paths()
            busy = [(e.label, openfiles.users_of(p, opened)) for e in sel if e.kind in ("path", "contents") for p in e.paths[:1]]
            busy = [(l, u) for l, u in busy if u]
            if busy:
                lines = "\n".join(f"• {l} - używa: {', '.join(u[:3])}" for l, u in busy[:8])
                more = f"\n…i {len(busy) - 8} więcej" if len(busy) > 8 else ""
                if QMessageBox.question(self, "TidyDisk", "Te pozycje są teraz używane przez działające programy:\n\n"
                                        f"{lines}{more}\n\nUsunięcie ich w trakcie pracy programu może coś zepsuć. "
                                        "Zamknij programy i spróbuj ponownie, albo kontynuuj.\n\nKontynuować mimo to?") \
                        != QMessageBox.StandardButton.Yes:
                    return
        if not dry and cp.act_review_each.isChecked():
            together = settings.load()["review_safe_together"]
            safe = [e for e in sel if together and e.rating == kb.SAFE and not e.user_pick and not e.warn] if together else []
            rest = [e for e in sel if e not in safe]
            sel = self.review_each(rest) if rest else []  # kazda pozycja osobno: 'Usun' jest potwierdzeniem
            if sel is not None and safe:
                if self.confirm(safe, dry):
                    sel = sel + safe
                else:
                    for e in safe:
                        e.checked = False
                        e.touched = True
                    cp._refresh_checks()
            if not sel:
                cp.show_banner("Nic nie zostało usunięte." if sel is None else
                               "Zostawiłeś wszystko - nic nie zostało usunięte.", "warn")
                return
        elif not self.confirm(sel, dry):
            return
        for e in sel:
            if e.user_pick:
                e.trash = cp.trash_box.isChecked()
        self._dry_last = dry
        if self.triage_busy and self.triage_worker is not None:
            self.triage_worker.cancel()
        if not dry:
            cp.record_decisions(sel)
        cp.banner.hide()
        cp.log.clear()
        self._syncing = True  # dziennik pokazujemy na czas czyszczenia, bez zapisu do ustawien
        cp.btn_log.setChecked(True)
        self._syncing = False
        self.set_busy(True)
        try:
            self._free_before = shutil.disk_usage(str(core.HOME)).free
        except OSError:
            self._free_before = None
        self.cleaner = CleanWorker(sel, dry)
        self.cleaner.log.connect(cp.log.appendPlainText)
        self.cleaner.done.connect(self.clean_done)
        self.cleaner.start()

    def clean_done(self, res) -> None:
        self.set_busy(False)
        self.update_disks()
        self.clean_page.log.appendPlainText("")
        if self._dry_last:
            banner = ("Symulacja zakończona - nic nie zostało usunięte. Szczegóły w dzienniku.", "ok")
        elif res.problems:
            word = plural(res.problems, "pozycja zgłosiła", "pozycje zgłosiły", "pozycji zgłosiło")
            banner = (f"Zakończono. Zwolniono ok. {fmt_size(res.freed)}, ale {res.problems} {word} "
                      "błędy - szczegóły w dzienniku.", "warn")
        else:
            text = f"✓ Gotowe - zwolniono ok. {fmt_size(res.freed)}."
            if res.trashed:
                text += (f" Do kosza przeniesiono ok. {fmt_size(res.trashed)} - miejsce zwolni się po "
                         "opróżnieniu kosza.")
            try:  # prawdziwy pomiar: wolne miejsce przed i po (btrfs z migawkami i kosz moga zwolnic mniej niz suma rozmiarow)
                real = shutil.disk_usage(str(core.HOME)).free - (getattr(self, "_free_before", None) or 0)
                if getattr(self, "_free_before", None) is not None:
                    text += f" Wolne miejsce na dysku domowym: {'+' if real >= 0 else '-'}{fmt_size(abs(real))}."
            except OSError:
                pass
            banner = (text, "ok")
        self._reanalyze = True
        if self.analysis_busy and self.analyzer is not None:
            self.analyzer.cancel()
        self.start_scan()
        self._banner = banner

    def _retire(self, attr: str) -> None:
        """Przed nadpisaniem referencji do dzialajacego watku odkladamy go na liste (Qt konczy proces, gdy QThread
        jest niszczony w trakcie pracy)."""
        w = getattr(self, attr, None)
        self._retired = [x for x in getattr(self, "_retired", []) if x.isRunning()]
        if w is not None and w.isRunning():
            self._retired.append(w)

    def _progress(self, label: str, pe: tuple) -> None:
        """Postep w zakladce Sprzatanie i w pasku stanu na dole (widoczny na kazdej stronie)."""
        percent, eta = pe
        self.clean_page.set_progress(percent, eta, label=label)
        self.set_global_progress(percent, eta, label)

    def set_global_progress(self, percent, eta: str = "", label: str = "") -> None:
        if percent == -1:
            self.gbar.setVisible(False)
            self.gcancel.setVisible(False)
            return
        self.gbar.setVisible(True)
        self.gcancel.setVisible(True)
        if percent is None:
            self.gbar.setRange(0, 0)
            self.gbar.setFormat("")
            return
        self.gbar.setRange(0, 1000)
        self.gbar.setValue(int(percent * 10))
        self.gbar.setFormat(f"{label}{percent}%" + (f" · pozostało {eta}" if eta else ""))

    def _init_status_bar(self) -> None:
        sb = self.statusBar()
        self.gbar = QProgressBar()
        self.gbar.setObjectName("busy")
        self.gbar.setTextVisible(True)
        self.gbar.setFixedWidth(360)
        self.gbar.setFixedHeight(16)
        self.gbar.setAccessibleName("Postęp pracy w tle")
        self.gcancel = QPushButton(i18n.tr("Przerwij"))
        self.gcancel.setAccessibleName("Przerwij pracę w tle")
        self.gcancel.clicked.connect(self.cancel_background)
        sb.addPermanentWidget(self.gbar)
        sb.addPermanentWidget(self.gcancel)
        self.gbar.setVisible(False)
        self.gcancel.setVisible(False)

    # -- praca w tle: zamkniecie okna w trakcie skanu/oceny AI chowa program do zasobnika zamiast je przerywac
    def _init_tray(self) -> None:
        try:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                return
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip("TidyDisk")
            menu = QMenu(self)
            menu.addAction("Pokaż okno", self.show_from_tray)
            menu.addAction("Przerwij pracę w tle", self.cancel_background)
            menu.addAction("Zakończ program", self.quit_app)
            self.tray.setContextMenu(menu)
            self._tray_menu = menu
            self.tray.activated.connect(lambda _r: self.show_from_tray())
            app = QApplication.instance()
            if app is not None:
                app.setQuitOnLastWindowClosed(False)
        except Exception:  # noqa: BLE001 - zasobnik jest dodatkiem: brak = zwykle zamykanie
            self.tray = None

    def _announce_background_run(self) -> None:
        """Po starcie: jedna linia o pracy w tle, ktora skonczyla sie od ostatniej wizyty (wyniki wczytaja sie z pamieci ocen)."""
        try:
            last = background.last_run()
            seen = float(self.settings.value("bg_seen", 0) or 0)
        except (TypeError, ValueError):
            return
        if not last or float(last.get("time", 0)) <= seen:
            return
        self.settings.setValue("bg_seen", float(last.get("time", 0)))
        extra = "" if last.get("error") else " Uruchom analizę - oceny AI wczytają się z pamięci."
        self.statusBar().showMessage(background.describe_last(last) + extra, 30000)

    def has_background_work(self) -> bool:
        return bool(self.analysis_busy or self.triage_busy or self.dscan_busy)

    def show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if self.tray is not None and not self.has_background_work():
            self.tray.hide()

    def cancel_background(self) -> None:
        for n in ("analyzer", "triage_worker", "dscanner"):
            w = getattr(self, n, None)
            if w is not None and w.isRunning() and hasattr(w, "cancel"):
                w.cancel()

    def quit_app(self) -> None:
        self._quitting = True
        self.close()
        app = QApplication.instance()
        if app is not None and not self.isVisible():
            app.quit()

    def tray_note(self, text: str) -> None:
        """Powiadomienie, gdy okno jest schowane i praca w tle sie skonczyla."""
        if self.tray is not None and self.isHidden():
            self.tray.showMessage("TidyDisk", text)

    def closeEvent(self, ev) -> None:  # noqa: N802
        if self.cleaner is not None and self.cleaner.isRunning():
            QMessageBox.warning(self, "TidyDisk", "Trwa czyszczenie - poczekaj na koniec.")
            ev.ignore()
            return
        if (not self._quitting and self.tray is not None and self.has_background_work()
                and settings.load().get("tray", True)):
            ev.ignore()
            self.hide()
            self.tray.show()
            self.tray.showMessage("TidyDisk", i18n.tr("Pracuję dalej w tle. Kliknij ikonę, żeby wrócić; powiadomię o końcu."))
            return
        workers = [getattr(self, n, None) for n in ("dscanner", "triage_worker", "ai_worker", "analyzer", "scanner")]
        workers += [getattr(self.settings_page, "tester", None)] + list(getattr(self, "_retired", []))
        workers.append(getattr(self.clean_page.panel.preview, "_worker", None))
        workers += [self.photos_page.worker, getattr(self.photos_page.preview, "_worker", None)]
        workers += list(_THUMBS)  # watki miniatur, ktorych nikt inny juz nie trzyma
        for w in workers:
            if w is not None and w.isRunning():
                if hasattr(w, "cancel"):
                    w.cancel()
                if not w.wait(4000):
                    w.terminate()  # lepiej uciac watek niz dostac abort procesu przy niszczeniu dzialajacego QThread
                    w.wait(1000)
        self.clean_page.panel.preview.cleanup()
        self.settings.setValue("geometry", self.saveGeometry())
        ev.accept()
        app = QApplication.instance()
        if app is not None and self.tray is not None:  # przy zasobniku 'zamknij ostatnie okno' nie konczy programu samo
            app.quit()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("tidydisk")
    app.setApplicationDisplayName("TidyDisk")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("tidydisk")
    if osal.SYSTEM == "linux":
        from . import schedule as _sch
        _sch.migrate_legacy_units()  # po zmianie nazwy: stare timery fedora-cleaner-* -> tidydisk-*
    if osal.is_admin():
        QMessageBox.critical(
            None, "TidyDisk",
            "Nie uruchamiaj programu jako administrator - sam poprosi o uprawnienia tylko tam, "
            "gdzie są potrzebne (inaczej wskazuje na profil administratora, nie Twój).")
        return 1
    i18n.set_language(settings.load()["language"])
    theme.apply(app, settings.load()["theme"], QSS)
    win = MainWindow()
    win.show()
    return app.exec()
