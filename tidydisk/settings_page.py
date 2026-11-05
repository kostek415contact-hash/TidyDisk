"""Strona „Ustawienia”: zwykle opcje, parametry algorytmu i AI, edycja promptow, ochrona sciezek, dane.

Formularz jest sterowany tabela FIELDS (klucz ustawienia -> etykieta, rodzaj pola), wiec dodanie opcji to jedna linijka.
Logika (odczyt/zapis wartosci, prompty, eksport) nie zalezy od wygladu i jest testowana bez Qt.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import ai, osal, rules, settings

# (klucz, etykieta, podpowiedz, rodzaj, parametry)  rodzaj: bool | int | float | choice | str | secret
TABS = [
    ("Ogólne", [
        ("trash_mine", "Moje pliki do kosza", "Pliki z „Twoich plików” trafiają do kosza (można przywrócić).", "bool", None),
        ("review_each", "Pytaj o każdą pozycję po kolei", "Przed usunięciem okno z pytaniem o każdy plik osobno.", "bool", None),
        ("review_safe_together", "Bezpieczne pozycje w jednym oknie", "Przy pytaniu po kolei: cache i pliki tymczasowe (Bezpieczne) potwierdzasz razem, resztę osobno.", "bool", None),
        ("dry_run", "Tryb symulacji", "Nic nie jest usuwane - tylko pokazuję, co bym zrobił.", "bool", None),
        ("auto_analysis", "Analizuj automatycznie po skanie", "Po skanie sprzątania od razu szukaj propozycji.", "bool", None),
        ("anonymize", "Raport: anonimizuj nazwę użytkownika", "W raporcie zamiast /home/nazwa jest ~.", "bool", None),
        ("show_private_names", "Raport: pokaż nazwy w moich plikach", "Domyślnie nazwy prywatnych plików są ukryte.", "bool", None),
        ("search_mode", "Dokładność wyszukiwania", "Niedokładny: tylko algorytm (bez AI). Dokładny: algorytm + AI. "
         "Bardzo dokładny: wyłącznie AI - algorytm w ogóle nie podaje ani nie ocenia kandydatów.", "choice",
         [("Niedokładny (tylko algorytm)", "algorithm"), ("Dokładny (algorytm + AI)", "assisted"),
          ("Bardzo dokładny (tylko AI)", "ai_only")]),
        ("theme", "Wygląd", "Zmiana działa od razu po zapisie.", "choice",
         [("TidyDisk (ciemny)", "fedora"), ("Nowoczesny (ciemny)", "modern"),
          ("Nowoczesny (jasny)", "modern-light"), ("Systemowy (KDE)", "system")]),
        ("language", "Język (część napisów)", "Po zmianie uruchom program ponownie. Brakujące tłumaczenia zostają po polsku.", "choice",
         [("Automatycznie", "auto"), ("Polski", "pl"), ("English", "en")]),
        ("show_log", "Pokaż dziennik", "Dziennik czyszczenia widoczny od razu.", "bool", None),
    ]),
    ("Reguły", "RULES"),
    ("Algorytm", [
        ("min_score", "Najniższa pewność propozycji (%)", "Poniżej tej oceny pozycja nie trafia na listę.", "int", None),
        ("auto_score", "Pewność, od której zaznaczam sam (%)", "Nie dotyczy „Twoich plików” - tych nie zaznaczam sam.", "int", None),
        ("dup_min_mb", "Duplikaty: najmniejszy plik (MB)", "Mniejsze pliki nie są porównywane.", "int", None),
        ("dup_budget_s", "Duplikaty: limit czasu (s)", "Po tym czasie szukanie duplikatów kończy się.", "int", None),
        ("analysis_depth", "Głębokość analizy folderów", "Jak głęboko schodzić do podfolderów.", "int", None),
        ("scan_parallel", "Miejsca skanowane naraz", "Dom i dyski danych są przeglądane równolegle. 1 = po kolei (domyślnie). Więcej pomaga głównie, gdy dom i dyski danych są na osobnych, wolnych dyskach.", "int", None),
    ]),
    ("AI", [
        ("ai_url", "Adres serwera", "Puste = wykryj sam. Tylko 127.0.0.1 / localhost.", "str", None),
        ("ai_key", "Klucz API", "Unsloth Studio: Settings → API (sk-unsloth-…).", "secret", None),
        ("ai_model", "Model", "Puste = pierwszy wczytany na serwerze.", "str", None),
        ("ai_timeout_s", "Limit czasu zapytania (s)", "Duży model na małej karcie może myśleć długo.", "int", None),
        ("ai_auto", "Oceniaj automatycznie po analizie", "", "bool", None),
        ("ai_inspect", "Zaglądaj do zawartości plików", "Krótki podgląd, lokalnie. Pliki z kluczami i hasłami nie są otwierane.", "bool", None),
        ("tray", "Praca w tle po zamknięciu okna", "Gdy trwa skan albo ocena AI, zamknięcie okna chowa program do zasobnika zamiast je przerywać.", "bool", None),
        ("ai_cache_days", "Pamiętaj oceny AI (dni)", "Przerwana ocena nie przepada, kolejna pomija to, co już ocenione. Zmiana modelu, promptów lub pliku = nowa ocena. 0 = wyłączone.", "int", None),
        ("ai_parallel", "Zapytań AI naraz (foldery)", "Szybciej, jeśli serwer obsługuje kilka zapytań (llama-server: --parallel). 1 = po kolei.", "int", None),
        ("ai_skip_inside", "Pomijaj wnętrza folderów uznanych za „cały zbędny”", "Oszczędza większość zapytań; ocena pojedynczego folderu się nie zmienia.", "bool", None),
        ("ai_mine", "AI może zaznaczać „Twoje pliki”", "Algorytm ich nie zaznacza sam. Wyłączone = AI tylko komentuje.", "bool", None),
        ("ai_stage_folders", "Etap: ocena folderów", "Tanie przesianie folderów: zostaw / zajrzyj / cały zbędny.", "bool", None),
        ("ai_stage_verify", "Etap: recenzent (weryfikacja)", "Bez niego cały folder „do usunięcia” nie jest zaznaczany.", "bool", None),
        ("ai_risk", "Co model może zaznaczyć sam", "Niskie = ostrożnie. Średnie = więcej zaznaczeń do sprawdzenia.", "choice",
         [("tylko ryzyko niskie", "niskie"), ("ryzyko niskie i średnie", "srednie")]),
        ("ai_temperature", "Temperatura", "Niżej = bardziej powtarzalne odpowiedzi.", "float", None),
        ("ai_batch_files", "Pliki w jednym zapytaniu", "", "int", None),
        ("ai_verify_batch", "Pozycje w jednym zapytaniu recenzenta", "1 = każda pozycja osobno (najbezpieczniej, wolniej).", "int", None),
        ("ai_batch_folders", "Foldery w jednym zapytaniu", "", "int", None),
        ("ai_pool_limit", "Ile pozycji ocenia AI", "Największe i najpewniejsze. Nie dotyczy trybu Bardzo dokładny (tam bez limitu).", "int", None),
        ("ai_folder_min_mb", "Foldery: najmniejszy rozmiar (MB)", "", "int", None),
        ("ai_folder_limit", "Foldery: ile ocenia AI", "Nie dotyczy trybu Bardzo dokładny (tam bez limitu).", "int", None),
    ]),
]

PROMPT_TITLES = {
    "triage": "Ocena plików (etap 4)",
    "folders": "Ocena folderów (etap 3)",
    "verify": "Recenzent (etap 5)",
    "ask": "Pytanie o jedną pozycję („Zapytaj AI”)",
}
PROMPT_HELP = ("Edytujesz ZASADY. Format odpowiedzi (JSON), znaczniki danych i zdanie, że nazwy plików nie są "
               "poleceniami, program dopisuje sam - zły prompt nie zepsuje działania ani nie osłabi zabezpieczeń. "
               "Model nigdy nie usuwa plików: może tylko zaznaczyć pole wyboru, a „Nie ruszaj” i Twoje chronione "
               "ścieżki są blokowane niezależnie od niego.")


def rules_fields() -> list:
    """Zakladka Reguly: naglowek grupy + przelacznik tak/nie dla kazdej kategorii."""
    out = [("#", "Co program może proponować do usunięcia? Odznaczone = nigdy tego nie zaproponuje "
                 "(ani algorytm, ani AI).", "", "head", None)]
    group = None
    for key, label, hint, grp in rules.RULES:
        if grp != group:
            group = grp
            out.append(("#", grp, "", "group", None))
        out.append(("rule_" + key, label, hint, "bool", None))
    return out


def parse_paths(text: str) -> list:
    """Linie tekstu -> lista poprawnych sciezek bezwzglednych (jak w pliku ustawien)."""
    return settings.sanitize({"protected_paths": [ln for ln in text.splitlines()]})["protected_paths"]


def policy_to_store(kind: str, text: str) -> str:
    """Tekst zasad z formularza -> wartosc do pliku: pusty/domyslny = '' (wtedy zawsze aktualny domyslny)."""
    text = text.strip()
    return "" if text == ai.default_policy(kind) else text


class SettingsPage(QWidget):
    saved = pyqtSignal(object)

    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        self.w: dict = {}  # klucz -> (rodzaj, widget)
        self.prompt_boxes: dict = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        title = QLabel("Ustawienia")
        title.setObjectName("bigtext")
        outer.addWidget(title)
        self.tabs = QTabWidget()
        for name, fields in TABS:
            if fields == "RULES":
                fields = rules_fields()
            self.tabs.addTab(self._form(fields, name), name)
        self.tabs.addTab(self._prompts_tab(), "Prompty (zaawansowane)")
        self.tabs.addTab(self._protect_tab(), "Ochrona")
        self.tabs.addTab(self._data_tab(), "Dane")
        outer.addWidget(self.tabs, 1)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        row = QHBoxLayout()
        self.btn_test = QPushButton("Zapisz i sprawdź połączenie z AI")
        self.btn_test.clicked.connect(self.test_connection)
        self.btn_save = QPushButton("Zapisz")
        self.btn_save.setObjectName("primary")
        self.btn_save.clicked.connect(self.save)
        row.addWidget(self.btn_test)
        row.addStretch(1)
        row.addWidget(self.btn_save)
        outer.addLayout(row)
        self.models: list = []
        self.tester = None
        self.load(settings.load())

    # -- budowa
    def _scroll(self, inner: QWidget) -> QWidget:
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(inner)
        return sc

    def _make(self, key: str, kind: str, extra):
        default, lo, hi = settings.SPEC[key]
        if kind == "bool":
            w = QCheckBox()
        elif kind == "int":
            w = QSpinBox()
            w.setRange(lo, hi)
        elif kind == "float":
            w = QDoubleSpinBox()
            w.setRange(lo, hi)
            w.setSingleStep(0.05)
            w.setDecimals(2)
        elif kind == "choice":
            w = QComboBox()
            for text, data in extra:
                w.addItem(text, data)
        else:
            w = QLineEdit()
            if kind == "secret":
                w.setEchoMode(QLineEdit.EchoMode.Password)
        self.w[key] = (kind, w)
        return w

    def _form(self, fields: list, tab: str) -> QWidget:
        inner = QWidget()
        form = QFormLayout(inner)
        form.setContentsMargins(14, 12, 14, 12)
        form.setVerticalSpacing(4)
        for key, label, hint, kind, extra in fields:
            if kind in ("head", "group"):
                lab = QLabel(label)
                lab.setObjectName("muted" if kind == "head" else "bigtext")
                form.addRow(lab)
                continue
            if kind == "bool":  # pole wyboru z opisem obok (bez osobnej kolumny etykiet)
                w = self._make(key, kind, extra)
                w.setText(label)
                form.addRow(w)
            else:
                w = self._make(key, kind, extra)
                form.addRow(label, w)
            if hint:
                w.setToolTip(hint)
                h = QLabel(hint)
                h.setObjectName("muted")
                h.setContentsMargins(26 if kind == "bool" else 0, 0, 0, 8)
                form.addRow(h)  # bez zawijania: zawijane etykiety w przewijanym formularzu ucinaja sie
            else:
                h = QWidget()
                h.setFixedHeight(6)
                form.addRow(h)
        if tab == "AI":
            self.btn_models = QPushButton("Wybierz model z listy serwera …")
            self.btn_models.clicked.connect(self.pick_model)
            form.addRow("", self.btn_models)
        return self._scroll(inner)

    def _prompts_tab(self) -> QWidget:
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(14, 12, 14, 12)
        info = QLabel(PROMPT_HELP)
        info.setObjectName("muted")
        info.setWordWrap(True)
        lay.addWidget(info)
        for kind, title in PROMPT_TITLES.items():
            lay.addWidget(QLabel(title))
            box = QPlainTextEdit()
            box.setMinimumHeight(110)
            self.prompt_boxes[kind] = box
            lay.addWidget(box)
            row = QHBoxLayout()
            b1 = QPushButton("Przywróć domyślne")
            b1.clicked.connect(lambda *_a, k=kind: self.restore_prompt(k))
            b2 = QPushButton("Pokaż pełny prompt")
            b2.clicked.connect(lambda *_a, k=kind: self.show_full_prompt(k))
            row.addWidget(b1)
            row.addWidget(b2)
            row.addStretch(1)
            lay.addLayout(row)
        lay.addWidget(QLabel("Dodatkowe zasady (dopisywane do każdego promptu)"))
        self.extra_box = QPlainTextEdit()
        self.extra_box.setMinimumHeight(80)
        self.extra_box.setPlaceholderText("np. Zawsze zostawiaj wszystko w folderze ~/Praca.")
        lay.addWidget(self.extra_box)
        lay.addStretch(1)
        return self._scroll(inner)

    def _protect_tab(self) -> QWidget:
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(14, 12, 14, 12)
        t1 = QLabel("Chronione ścieżki - po jednej w linii. Program nigdy ich nie zaproponuje, nie pokaże AI "
                    "i nie usunie (także gdy zaznaczysz folder, który je zawiera).")
        t1.setWordWrap(True)
        t1.setObjectName("muted")
        lay.addWidget(t1)
        self.protect_box = QPlainTextEdit()
        self.protect_box.setMinimumHeight(140)
        self.protect_box.setPlaceholderText("/home/ty/Praca\n~/Zdjęcia/Rodzina")
        lay.addWidget(self.protect_box)
        b = QPushButton("Dodaj folder …")
        b.clicked.connect(self.add_protected)
        lay.addWidget(b)
        t2 = QLabel("Pozycje, których kazałeś nie proponować więcej (z okna „Nie proponuj więcej”) - po jednej w linii. "
                    "Usuń linię, żeby program znów mógł to proponować.")
        t2.setWordWrap(True)
        t2.setObjectName("muted")
        lay.addWidget(t2)
        self.ignore_box = QPlainTextEdit()
        self.ignore_box.setMinimumHeight(120)
        lay.addWidget(self.ignore_box)
        t3 = QLabel("Czego się nauczyłem z Twoich decyzji (+ zwykle usuwasz, − zwykle zostawiasz). "
                    "Wybierz cechę i zapomnij tylko ją.")
        t3.setWordWrap(True)
        t3.setObjectName("muted")
        lay.addWidget(t3)
        self.learned_box = QComboBox()
        lay.addWidget(self.learned_box)
        self.btn_drop = QPushButton("Zapomnij wybraną cechę")
        self.btn_drop.clicked.connect(self.drop_learned)
        lay.addWidget(self.btn_drop)
        self.btn_forget = QPushButton("Zapomnij moje wcześniejsze decyzje (uczenie)")
        self.btn_forget.clicked.connect(self.forget)
        lay.addWidget(self.btn_forget)
        lay.addStretch(1)
        return self._scroll(inner)

    def _data_tab(self) -> QWidget:
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(14, 12, 14, 12)
        self.paths_label = QLabel("")
        self.paths_label.setWordWrap(True)
        self.paths_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.paths_label)
        for text, fn in (("Eksportuj ustawienia (bez klucza API) …", self.export_settings),
                         ("Importuj ustawienia …", self.import_settings),
                         ("Zapisz zrzut diagnostyczny (do wysłania z raportem) …", self.save_diag),
                         ("Przywróć wszystkie ustawienia domyślne", self.reset_defaults)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            lay.addWidget(b)
        lay.addStretch(1)
        return self._scroll(inner)

    # -- wartosci
    def _get(self, key: str):
        kind, w = self.w[key]
        if kind == "bool":
            return bool(w.isChecked())
        if kind in ("int", "float"):
            return w.value()
        if kind == "choice":
            return w.currentData()
        return w.text().strip()

    def _set(self, key: str, value) -> None:
        kind, w = self.w[key]
        if kind == "bool":
            w.setChecked(bool(value))
        elif kind in ("int", "float"):
            w.setValue(value)
        elif kind == "choice":
            for i in range(w.count()):
                if w.itemData(i) == value:
                    w.setCurrentIndex(i)
        else:
            w.setText(str(value))

    def load(self, cfg: dict) -> None:
        for key in self.w:
            self._set(key, cfg[key])
        for kind, box in self.prompt_boxes.items():
            box.setPlainText(cfg["prompt_" + kind].strip() or ai.default_policy(kind))
        self.extra_box.setPlainText(cfg["prompt_extra"])
        self.protect_box.setPlainText("\n".join(cfg["protected_paths"]))
        learner = getattr(getattr(self.win, "clean_page", None), "learner", None)
        self.ignore_box.setPlainText("\n".join(learner.ignored) if learner is not None else "")
        self.refresh_learned()
        self.paths_label.setText(
            f"Plik ustawień (tylko dla Ciebie{'' if osal.is_windows() else ', 0600'}): {settings.path()}\n"
            f"Uczenie się z Twoich decyzji: {osal.data_dir() / 'learn.json'}")

    def values(self) -> dict:
        out = {key: self._get(key) for key in self.w}
        for kind, box in self.prompt_boxes.items():
            out["prompt_" + kind] = policy_to_store(kind, box.toPlainText())
        out["prompt_extra"] = self.extra_box.toPlainText().strip()
        out["protected_paths"] = parse_paths(self.protect_box.toPlainText())
        return out

    # -- akcje
    def save(self, *_a) -> dict:
        typed = str(self.values().get("ai_url", "")).strip()
        cfg = settings.update(self.values())
        settings.apply(cfg)
        learner = getattr(getattr(self.win, "clean_page", None), "learner", None)
        if learner is not None:
            new = [ln.strip() for ln in self.ignore_box.toPlainText().splitlines() if ln.strip()]
            if new != learner.ignored:
                learner.ignored = new
                learner.save()
        self.load(cfg)  # pokaz to, co naprawde zapisano (po poprawkach zakresow)
        self.status.setText("Zapisano. Zmiany AI i ochrony działają od razu; zmiany algorytmu - od następnej analizy.")
        if typed and not cfg.get("ai_url"):
            self.status.setText("Zapisano, ale adres AI pominąłem: musi być lokalny (http://127.0.0.1:PORT lub "
                                "http://localhost:PORT) - dane nie wychodzą z komputera.")
        self.saved.emit(cfg)
        return cfg

    def restore_prompt(self, kind: str) -> None:
        self.prompt_boxes[kind].setPlainText(ai.default_policy(kind))

    def show_full_prompt(self, kind: str) -> None:
        cfg = {**self.values()}
        QMessageBox.information(self, PROMPT_TITLES[kind], ai.prompt_text(kind, cfg))

    def add_protected(self, *_a) -> None:
        d = QFileDialog.getExistingDirectory(self, "Wybierz folder do ochrony")
        if d:
            cur = self.protect_box.toPlainText().rstrip()
            self.protect_box.setPlainText((cur + "\n" if cur else "") + d)

    def _learner(self):
        return getattr(getattr(self.win, "clean_page", None), "learner", None)

    @staticmethod
    def learned_label(name: str, weight: float, n: int) -> str:
        kind, _, val = name.partition("=")
        what = {"ext": "pliki .", "top": "folder ", "dir2": "folder ", "sig": "sygnał: "}.get(kind, "") if val else name
        shown = (what + val) if val else name
        return f"{shown}  ({'+' if weight >= 0 else '−'}{abs(weight):.1f}, {n} decyzji)"

    def refresh_learned(self) -> None:
        self.learned_box.clear()
        learner = self._learner()
        if learner is None:
            return
        for name, w, n in learner.learned():
            self.learned_box.addItem(self.learned_label(name, w, n), name)

    def drop_learned(self, *_a) -> None:
        learner = self._learner()
        name = self.learned_box.currentData()
        if learner is None or not name:
            return
        learner.drop_feature(name)
        self.refresh_learned()
        self.status.setText(f"Zapomniałem cechę: {name}")

    def forget(self, *_a) -> None:
        cp = getattr(self.win, "clean_page", None)
        if cp is not None:
            cp.forget_learning()
        self.ignore_box.setPlainText("")
        self.refresh_learned()
        self.status.setText("Zapomniałem Twoje wcześniejsze decyzje.")

    def export_settings(self, *_a) -> None:
        path, _f = QFileDialog.getSaveFileName(self, "Eksport ustawień", "tidydisk-ustawienia.json", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(settings.export_text(settings.sanitize(self.values())))
            self.status.setText(f"Zapisano ustawienia (bez klucza API): {path}")
        except OSError as ex:
            self.status.setText(f"Nie udało się zapisać: {ex.strerror}")

    def save_diag(self, *_a) -> None:
        from . import diag, fsutil
        path, _f = QFileDialog.getSaveFileName(self, "Zrzut diagnostyczny", "tidydisk-diag.txt", "Tekst (*.txt)")
        if not path:
            return
        try:
            fsutil.atomic_write(path, diag.build(), 0o600)
            self.status.setText(f"Zapisano zrzut diagnostyczny (bez klucza API): {path}")
        except OSError as ex:
            self.status.setText(f"Nie udało się zapisać: {ex.strerror}")

    def import_settings(self, *_a) -> None:
        path, _f = QFileDialog.getOpenFileName(self, "Import ustawień", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                cfg = settings.import_text(f.read())
        except (OSError, ValueError) as ex:
            self.status.setText(f"Nie udało się wczytać ustawień: {ex}")
            return
        self.load(cfg)
        self.status.setText("Wczytano ustawienia - sprawdź je i kliknij Zapisz.")

    def reset_defaults(self, *_a) -> None:
        keep_key = self._get("ai_key")
        cfg = settings.defaults()
        cfg["ai_key"] = keep_key  # klucza API nie kasujemy przy przywracaniu domyslnych
        self.load(cfg)
        self.status.setText("Przywrócono domyślne (klucz API zostawiony) - kliknij Zapisz.")

    def test_connection(self, *_a) -> None:
        from .widgets import AITestWorker
        if self.tester is not None and self.tester.isRunning():
            return
        self.save()
        self.status.setText("Sprawdzam połączenie …")
        self.tester = AITestWorker()
        self.tester.ok.connect(self.on_test_ok)
        self.tester.failed.connect(self.status.setText)
        self.tester.start()

    def on_test_ok(self, host: str, models: list) -> None:
        self.models = list(models)
        names = ", ".join(models[:6]) + (" …" if len(models) > 6 else "")
        self.status.setText(f"✓ Połączono z {host}. Modele: {names or 'brak wczytanego modelu'}")

    def pick_model(self, *_a) -> None:
        if not self.models:
            self.status.setText("Najpierw kliknij „Zapisz i sprawdź połączenie z AI”.")
            return
        name, ok = QInputDialog.getItem(self, "Model", "Model:", self.models, 0, False)
        if ok and name:
            self._set("ai_model", name)
