"""Smoke-test na prawdziwym PyQt6 (offscreen). Bez PyQt6: SKIP i kod 0.  Uruchom:  python3 tests/smoke_qt.py"""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp(prefix="fc-smoke-")
os.environ["HOME"] = TMP
os.environ["XDG_CONFIG_HOME"] = str(Path(TMP) / ".config")
os.environ["XDG_DATA_HOME"] = str(Path(TMP) / ".local/share")
sys.path.insert(0, str(ROOT))

try:
    import PyQt6  # noqa: F401
except ImportError:
    print("SKIP: brak PyQt6")
    sys.exit(0)

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def guarded(name, fn):
    try:
        fn()
    except Exception as ex:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        check(False, f"{name}: wyjatek {type(ex).__name__}: {ex}")


from PyQt6.QtWidgets import QApplication  # noqa: E402

from tidydisk import core, gui, settings  # noqa: E402

app = QApplication(sys.argv)
win = gui.MainWindow()
win.show()
app.processEvents()
check(True, "MainWindow utworzone")


def pages():
    n = win.nav.count()
    check(n >= 6, f"nawigacja ma {n} stron")
    for i in range(n):
        win.nav.setCurrentRow(i)
        app.processEvents()
        check(win.pages.currentIndex() == i, f"strona {i} ({win.nav.item(i).text()}) przelaczona")
        shots = os.environ.get("SMOKE_SHOTS")  # katalog na zrzuty ekranu stron (CI zapisuje je jako artefakt)
        if shots:
            os.makedirs(shots, exist_ok=True)
            win.grab().save(os.path.join(shots, f"strona-{i:02d}.png"))


def settings_values():
    vals = win.settings_page.values()
    check(isinstance(vals, dict), "settings_page.values() zwraca slownik")
    missing = [k for k in settings.SPEC if k not in vals]
    check(not missing, f"values() ma wszystkie klucze SPEC (brak: {missing})")


def treemap():
    m = win.map_page.map
    items = [("/a", 5_000_000, "safe", "A"), ("/b", 3_000_000, "review", "B"),
             ("/c", 1_500_000, "mine", "C"), ("/d", 500_000, "keep", "D")]
    m.set_items(items, ai_paths=["/b"])
    m.resize(800, 500)
    app.processEvents()
    img = m.grab()
    check(not img.isNull() and img.width() > 0, "TreemapWidget wyrenderowany (grab)")
    check(len(m.rects) == len(items), "treemap ma tyle prostokatow co elementow")
    m.set_items([])
    check(not m.grab().isNull(), "pusty treemap tez sie renderuje")


def detail():
    panel = win.clean_page.panel
    panel.clear()
    e = core.Entry(label="Test", size=123456, kind="path", paths=["/tmp/x"], rating="safe",
                   what="opis", why="powod", score=80)
    panel.set_entry(e)
    app.processEvents()
    check(panel.title.text() == "Test", "DetailPanel.set_entry ustawia tytul")
    panel.show_ai("odpowiedz")
    panel.clear()
    check(True, "DetailPanel clear/show_ai bez wyjatku")


def save():
    cfg = win.settings_page.save()
    check(isinstance(cfg, dict) and set(settings.SPEC) <= set(cfg), "SettingsPage.save() zwraca pelna konfiguracje")
    check(Path(settings.path()).exists(), "plik ustawien zapisany")
    check(settings.load()["theme"] == cfg["theme"], "ustawienia odczytane po zapisie")


for name, fn in (("strony", pages), ("ustawienia", settings_values), ("treemap", treemap),
                 ("panel", detail), ("zapis", save)):
    guarded(name, fn)


def shutdown():
    for _ in range(20):
        app.processEvents()
        time.sleep(0.05)
    # skan mogl ruszyc po utworzeniu okna - close() anuluje i czeka na watki
    win.close()
    app.processEvents()
    from PyQt6.QtCore import QThread
    names = ("dscanner", "triage_worker", "ai_worker", "analyzer", "scanner", "cleaner")
    ths = [getattr(win, n, None) for n in names] + [getattr(win.settings_page, "tester", None)]
    ths += list(getattr(win, "_retired", []))
    ths = [t for t in ths if isinstance(t, QThread)]
    deadline = time.time() + 10
    while time.time() < deadline and any(t.isRunning() for t in ths):
        app.processEvents()
        time.sleep(0.05)
    left = [type(t).__name__ for t in ths if t.isRunning()]
    check(not left, f"brak dzialajacych watkow po zamknieciu ({left})")


guarded("zamkniecie", shutdown)
print(f"\n{'BLEDY: ' + str(len(fails)) if fails else 'WSZYSTKO OK'}")
sys.exit(1 if fails else 0)
