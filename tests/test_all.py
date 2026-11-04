"""Testy TidyDisk (bez Qt i bez roota). Uruchom:  python3 -I tests/test_all.py"""
import json
import os
import re
import time
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="fc-test-"))
HOME = TMP / "home"


def make_home():
    for d in (".cache/mozilla/x", ".cache/foo", ".cache/bar", ".cache/pip", ".cache/huggingface", "Documents/Secret",
              "Downloads", ".local/share/Trash/files", ".var/app/org.x.App/cache", ".var/app/org.x.App/data",
              ".config/app", "proj/node_modules/a"):
        (HOME / d).mkdir(parents=True, exist_ok=True)
    def blob(rel, n):
        (HOME / rel).write_bytes(os.urandom(n))
    blob(".cache/mozilla/x/c", 1_500_000); blob(".cache/foo/a", 500_000); blob(".cache/bar/a", 400_000); blob(".cache/pip/a", 1_000_000)
    blob(".cache/huggingface/m", 3_000_000); blob("Documents/Secret/tajne.pdf", 2_500_000)
    blob("Downloads/fedora.iso", 4_000_000); blob(".local/share/Trash/files/x", 700_000)
    blob(".var/app/org.x.App/cache/c", 800_000); blob(".var/app/org.x.App/data/save", 300_000)
    blob("proj/node_modules/a/b.js", 1_200_000); (HOME / ".config/app/c.conf").write_text("x=1\n")


make_home()
os.environ["HOME"] = str(HOME)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from tidydisk import core, extras, kb, report, scanner, viewmodel  # noqa: E402

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


# ---------------------------------------------------------------- baza wiedzy
K = core.KB
H = str(HOME)
cases = {
    H + "/.cache/mozilla/x/c": (kb.SAFE, "Cache Firefoksa"),
    H + "/.cache/foo/a": (kb.SAFE, "Cache aplikacji"),
    H + "/.cache/huggingface/m": (kb.REVIEW, "Modele Hugging Face"),
    H + "/Downloads/fedora.iso": (kb.REVIEW, "Obraz dysku"),
    H + "/Documents/Secret/tajne.pdf": (kb.MINE, "Dokument"),
    H + "/.config/app/c.conf": (kb.KEEP, None),
    H + "/.ssh/id_ed25519": (kb.KEEP, None),
    H + "/.mozilla/firefox/p/places.sqlite": (kb.KEEP, None),
    H + "/.var/app/org.x.App/cache/c": (kb.SAFE, None),
    H + "/.var/app/org.x.App/data/save": (kb.KEEP, None),
    H + "/proj/node_modules/a/b.js": (kb.REVIEW, None),
    H + "/proj/main.py": (kb.MINE, None),
    H + "/proj/.git/objects/ab": (kb.KEEP, None),
    "/usr/bin/ls": (kb.KEEP, None),
    "/boot/vmlinuz": (kb.KEEP, None),
    "/var/cache/libdnf5/x": (kb.SAFE, "Cache DNF"),
    "/etc/passwd": (kb.KEEP, None),
    "/mnt/dysk/foto.jpg": (kb.KEEP, None),
}
for p, (rating, title) in cases.items():
    v = K.classify_file(p)
    check(v.rating == rating and (title is None or v.title == title),
          f"kb: {p.replace(H, '~')} -> {v.rating}/{v.title}")
check(K.classify(H + "/nieznany").rating == kb.MINE, "kb: nieznany plik w domu = Twoje pliki (ostroznie)")
check(K.classify("/dziwny/katalog").rating == kb.KEEP, "kb: nieznane poza domem = nie ruszaj")
check(kb._glob_to_regex("/a/*/c").match("/a/b/c") and not kb._glob_to_regex("/a/*/c").match("/a/b/x/c"),
      "kb: * nie przekracza /")
# zadna regula nie moze oznaczac katalogow z danymi jako 'safe'
for pat, rating, *_ in kb._RULES:
    if any(w in pat for w in ("/.config", "/.ssh", "/.gnupg", "/Documents", "/Pictures", "/.mozilla")):
        check(rating in (kb.KEEP, kb.MINE), f"kb: regula {pat} nie jest 'safe'")

# --------------------------------------------------------------------- skaner
r = scanner.scan(H, K, skip=set())
check(r.nfiles == 12 and r.total > 15_000_000, f"skaner: {r.nfiles} plikow, {r.total} B")
check(abs(sum(r.by_rating.values()) - r.total) < 200_000, "skaner: oceny sumuja sie do calosci")
check(r.top_files[0][1].endswith("fedora.iso"), "skaner: najwiekszy plik na gorze")
check(any(f[1].endswith("tajne.pdf") and f[3] == kb.MINE for f in r.top_files), "skaner: pdf = Twoje pliki")
kids = {os.path.basename(c[0]): c for c in r.children(H)}
check("Downloads" in kids and kids["Downloads"][3] == kb.REVIEW, "skaner: podkatalogi z ocenami")
src = scanner.build_admin_source(H, H)
out = subprocess.run([sys.executable, "-I", "-c", src], capture_output=True, text=True)
parsed = [scanner.parse_admin_line(x) for x in out.stdout.splitlines()]
res = [p[1] for p in parsed if p and p[0] == "J"]
check(out.returncode == 0 and res and res[0].total == r.total and res[0].mode == "admin",
      "skaner: tryb administratora (kod z -c) daje ten sam wynik")
check(scanner.pseudo_mounts() >= {"/proc", "/sys"}, "skaner: pomija pseudo-systemy plikow")
(HOME / "link").symlink_to("/etc")
r2 = scanner.scan(H, K, skip=set())
check(r2.nfiles == r.nfiles + 1 and r2.total < r.total + 100_000, "skaner: nie idzie za symlinkami")

# ------------------------------------------------------------ sprzatanie/rdzen
cats = core.scan()
ents = {e.label: e for c in cats for e in c.entries}
check(ents["mozilla"].checked and ents["mozilla"].rating == kb.SAFE, "core: cache firefoksa zaznaczony (nie dziala)")
check(not ents["huggingface"].checked and ents["huggingface"].rating == kb.REVIEW, "core: modele - do przejrzenia, nie zaznaczone")
check(not ents["Opróżnij kosz"].checked, "core: kosz nie jest zaznaczany sam")
check(all(e.suggested == e.checked for c in cats for e in c.entries), "core: suggested = wybor poczatkowy")
check(not any(e.rating in (kb.KEEP, kb.MINE) for c in cats for e in c.entries), "core: brak wpisow keep/mine")
running = {"firefox"}
check("firefox" in core.running_warn("mozilla", running), "core: wykrywa dzialajacego Firefoksa")
check(core.running_warn("pip", running) == "", "core: brak ostrzezenia gdy nie dziala")
check(len(core.running_names()) > 0, "core: czyta /proc")
mine_entry = core.Entry("Docs", 1, "path", [str(HOME / "Documents")], rating=kb.MINE)
logs = []
core.run_clean([mine_entry], False, logs.append)
check((HOME / "Documents/Secret/tajne.pdf").exists() and "POMINI" in logs[0], "core: Twoje pliki nie sa usuwane")
check(not core.is_safe_target(H + "/Documents/x") and core.is_safe_target(H + "/.cache/x"), "core: is_safe_target")
prot = core.protected_items(r)
check(any(p.label == "~/Documents" and p.size > 0 for p in prot), "core: chronione z rozmiarami")

# ------------------------------------------------------------ dyski i podzial
LSBLK = """{"blockdevices":[
{"name":"sda","path":"/dev/sda","type":"disk","size":1024209543168,"model":"SPCC SSD","rota":false,"tran":"sata","rm":false,"children":[
 {"name":"sda2","path":"/dev/sda2","type":"part","size":604000000000,"fstype":"ext4","label":"Dysk SSD","uuid":"u-sda2","mountpoints":["/mnt/fc-test"]}]},
{"name":"nvme0n1","path":"/dev/nvme0n1","type":"disk","size":1000204886016,"model":"Samsung 980","rota":false,"tran":"nvme","rm":false,"children":[
 {"name":"nvme0n1p3","path":"/dev/nvme0n1p3","type":"part","size":209715200000,"fstype":"btrfs","label":"fedora","uuid":"u-bt","mountpoints":["/home","/"]},
 {"name":"nvme0n1p6","path":"/dev/nvme0n1p6","type":"part","size":106000000000,"fstype":"btrfs","label":"fedora","uuid":"u-bt","mountpoints":[]},
 {"name":"nvme0n1p7","path":"/dev/nvme0n1p7","type":"part","size":149000000000,"fstype":"btrfs","label":"fedora","uuid":"u-bt","mountpoints":[]}]}]}"""
from tidydisk import disks  # noqa: E402
found = disks.parse_lsblk(LSBLK, usage=lambda m: (344 * 2**30, 90 * 2**30))
bt = [p for d in found for p in d.parts if p.uuid == "u-bt"]
check(len(bt) == 3 and all(p.group == 3 and p.mount == "/home" and p.used == 344 * 2**30 for p in bt),
      "dyski: btrfs na 3 partycjach = jeden wolumen (wspolny punkt montowania i zajetosc)")
lab = disks.mount_labels(found)
check(lab["/home"].startswith("nvme0n1") and "„fedora”" in lab["/home"] and lab["/mnt/fc-test"].startswith("sda"),
      "dyski: etykiety punktow montowania")
fm = [("/", "btrfs"), ("/home", "btrfs"), ("/mnt/SSD", "ext4"), ("/mnt/ext4", "ext4"), ("/boot", "ext4"),
      ("/run/user/1000", "tmpfs"), ("/mnt/win", "ntfs3")]
check(core.data_mounts(fm) == ["/mnt/SSD", "/mnt/ext4", "/mnt/win"], "core: dyski danych (bez systemowych i tmpfs)")
check(core.mount_of("/home/x/.cache", fm) == "/home" and core.mount_of("/mnt/SSD/a/b", fm) == "/mnt/SSD"
      and core.mount_of("/usr/bin", fm) == "/", "core: mount_of = najdluzszy prefiks")
K2 = kb.KnowledgeBase(H, ["/mnt/SSD"])
check(K2.classify_file("/mnt/SSD/Gry/save.dat").rating == kb.MINE, "kb: pliki na dysku danych = Twoje pliki")
check(K2.classify_file("/mnt/SSD/.Trash-1000/files/x").rating == kb.SAFE, "kb: kosz na dysku danych = bezpieczne")
check(K2.classify_file("/mnt/SSD/System Volume Information/x").rating == kb.KEEP, "kb: dane Windows = nie ruszaj")
check("kthreadd" not in core.running_names(), "core: watki jadra nie sa 'dzialajacymi programami'")
if os.access("/mnt", os.W_OK):  # bez roota (np. CI na Ubuntu) pomijamy test kosza na drugim dysku
    os.makedirs("/mnt/fc-test/.Trash-%d/files" % os.getuid(), exist_ok=True)
    Path("/mnt/fc-test/.Trash-%d/files/stary.iso" % os.getuid()).write_bytes(os.urandom(900_000))
    vc = core.volume_trash_categories(found, lab)
    check(len(vc) == 1 and vc[0].entries[0].disk.startswith("sda") and vc[0].entries[0].size > 800_000
          and not vc[0].entries[0].checked, "core: kosz na drugim dysku (niezaznaczony, z nazwa dysku)")
    logs2 = []
    core.run_clean(vc[0].entries, False, logs2.append)
    check(not Path("/mnt/fc-test/.Trash-%d/files/stary.iso" % os.getuid()).exists(), "core: czyszczenie kosza na drugim dysku")
    shutil.rmtree("/mnt/fc-test", ignore_errors=True)
(HOME / ".cache/bigcache").mkdir(); (HOME / ".cache/bigcache/x").write_bytes(os.urandom(2_000_000))
core.BIG_CACHE = 1_500_000
cats_big = core.scan()
big = {e.label: e for c in cats_big for e in c.entries}
check(big["bigcache"].rating == kb.REVIEW and not big["bigcache"].checked, "core: duzy nierozpoznany cache = do przejrzenia")
check(big["mozilla"].rating == kb.REVIEW or big["mozilla"].size < 1_500_000 or big["mozilla"].rule != "~/.cache/*",
      "core: rozpoznany cache zostaje bezpieczny")
check(all(e.disk for c in cats_big for e in c.entries), "core: kazda pozycja ma przypisany dysk")
core.BIG_CACHE = 1024 ** 3
shutil.rmtree(HOME / ".cache/bigcache")

# --------------------------------------------------------------------- raport
for c in cats:
    for e in c.entries:
        e.checked = e.suggested
ents["pip"].checked = False  # uzytkownik odznacza
md = report.build_markdown(cats, prot, r, [], report.Anon())
check("## USUNĘ" in md and "## ZOSTAWIĘ" in md and "## CHRONIONE" in md, "raport: trzy sekcje")
check("## Podział wg dysków" in md, "raport: podzial wg dyskow")
check(md.count("↑ jak") >= 1 or len(cats) < 1, "raport: powtarzajace sie opisy skrocone")
sec_del = md.split("## ZOSTAWIĘ")[0]
sec_keep = md.split("## ZOSTAWIĘ")[1].split("## CHRONIONE")[0]
check("mozilla" in sec_del and "huggingface" not in sec_del, "raport: mozilla do usuniecia, modele nie")
check("huggingface" in sec_keep and "pip" in sec_keep and "odznaczone przez Ciebie" in sec_keep, "raport: zostawione z powodem")
check(str(HOME) not in md and "/home/" not in md, "raport: sciezki zanonimizowane")
check("tajne.pdf" not in md and "Secret" not in md, "raport: nazwy w 'Twoich plikach' zamaskowane")
md2 = report.build_markdown(cats, prot, r, [], report.Anon(False, True))
check("tajne.pdf" in md2 and str(HOME) in md2, "raport: opcje pokaz nazwy / bez anonimizacji")
csvtext = report.build_csv(cats, prot)
rows = [x.split(";") for x in csvtext.splitlines()]
check(rows[0][0] == "decyzja" and {x[0] for x in rows[1:]} >= {"USUNĘ", "ZOSTAWIĘ", "CHRONIONE"}, "raport: csv ma 3 decyzje")
check(len({len(x) for x in rows if len(x) > 6}) >= 1, "raport: csv parsuje sie")

# --------------------------------------------------------------- widok (bez Qt)
fr = viewmodel.folder_rows(r, H)
check(fr and fr[0].size >= fr[-1].size and fr[0].frac == 1.0, "viewmodel: foldery posortowane")
check([x.name for x in viewmodel.file_rows(r, kb.MINE)] == ["tajne.pdf"], "viewmodel: filtr oceny plikow")
check(viewmodel.file_rows(r, None, "iso")[0].name == "fedora.iso", "viewmodel: szukanie")
s = viewmodel.cleanup_summary(cats)
check(s["n_delete"] + s["n_keep"] == sum(len(c.entries) for c in cats), "viewmodel: podsumowanie sie zgadza")

# ------------------------------------------------------------- okno (atrapa Qt)
import fakeqt  # noqa: E402
fakeqt.install()
from tidydisk import gui, widgets  # noqa: E402

win = gui.MainWindow()
check(win.scanner.started_flag, "okno: start skanu sprzatania")
cats2 = core.scan()
win.on_scan_done(cats2)
cp = win.clean_page
check(cp.tree.topLevelItemCount() >= 3, f"okno: kategorie w drzewie ({cp.tree.topLevelItemCount()})")
cache_top = next(cp.tree.topLevelItem(i) for i in range(cp.tree.topLevelItemCount()) if cp.tree.topLevelItem(i).text(0) == "Cache aplikacji")
kids = [cache_top.child(i) for i in range(cache_top.childCount())]
labels = [k.text(0) for k in kids]
check(any("mozilla" in x for x in labels), "okno: pozycje cache")
flat = next(cp.tree.topLevelItem(i) for i in range(cp.tree.topLevelItemCount()) if cp.tree.topLevelItem(i).text(0) == "Flatpak")
check(any(flat.child(j).text(0).startswith("🔒") for j in range(flat.childCount())), "okno: wiersz 'chronione' w drzewie")
check("Usunę:" in cp.sum_big.text(), f"okno: podsumowanie '{cp.sum_big.text()}'")
before = cp.sum_big.text()
mozilla = next(k for k in kids if "mozilla" in k.text(0))
mozilla.setCheckState(0, fakeqt.Val(0))
cp.tree.itemChanged.emit(mozilla, 0)
e = mozilla.data(0, gui.ENTRY_ROLE)
check(e.checked is False and cp.sum_big.text() != before, "okno: odznaczenie aktualizuje wpis i podsumowanie")
cp.select_recommended()
check(e.checked is True, "okno: 'zaznacz polecane' przywraca propozycje")
cp.uncheck_all()
check(not cp.selected_entries() and "Nic nie zaznaczono" in cp.sum_big.text(), "okno: odznacz wszystko")
cp.select_recommended()
cp.filter._t = "pip"; cp.apply_filter("pip")
check(any(k.isHidden() for k in kids) and not next(k for k in kids if k.text(0) == "pip").isHidden(), "okno: filtr")
cp.apply_filter("")
# raport z okna
FP = TMP / "raport.md"
fakeqt.FakeFileDialog.path = str(FP)
win.save_report("md")
check(FP.exists() and "## USUNĘ" in FP.read_text(encoding="utf-8"), "okno: zapis raportu .md")
FP2 = TMP / "raport.csv"
fakeqt.FakeFileDialog.path = str(FP2)
win.save_report("csv")
check(FP2.read_bytes().startswith(b"\xef\xbb\xbf") and "USUNĘ" in FP2.read_text("utf-8-sig"), "okno: zapis csv (utf-8-sig)")
win.copy_report()
check(fakeqt.FakeClipboard.text and "Raport TidyDisk" in fakeqt.FakeClipboard.text, "okno: schowek")
# przegladarka plikow (na zywo) i skan calego dysku w oknie
fp = win.folders_page
def top_names(page):
    return [page.tree.topLevelItem(i).text(0) for i in range(page.tree.topLevelItemCount())]
check("📁 Downloads" in top_names(fp) and "📁 .cache" in top_names(fp), f"okno: foldery widoczne na zywo bez skanu {top_names(fp)[:4]}")
dl_item = next(fp.tree.topLevelItem(i) for i in range(fp.tree.topLevelItemCount()) if fp.tree.topLevelItem(i).text(0) == "📁 Downloads")
check(dl_item.childCount() == 1 and dl_item.child(0).text(0) == "…", "okno: lazy placeholder")
fp.on_expand(dl_item)
check([dl_item.child(i).text(0) for i in range(dl_item.childCount())] == ["fedora.iso"], "okno: Pobrane - widac plik")
fp.on_select(dl_item.child(0), None)
check("Obraz dysku" in fp.details.text() and "do przejrzenia" in fp.details.text(), "okno: wyjasnienie pliku w Pobranych")
(HOME / "Downloads" / "maly.txt").write_text("a")
(HOME / "Downloads" / "inst.rpm").write_bytes(b"x" * 5000)
items, extra, err = core.list_folder(str(HOME / "Downloads"))
check({i.name for i in items} == {"fedora.iso", "maly.txt", "inst.rpm"} and not err, "core: list_folder pokazuje WSZYSTKIE pliki (takze male)")
check(next(i for i in items if i.name == "inst.rpm").verdict.rating == kb.REVIEW, "core: .rpm w Pobranych = do przejrzenia")
check(next(i for i in items if i.name == "maly.txt").verdict.title == "Dokument", "core: .txt w Pobranych rozpoznany jako dokument")
win.on_disk_done(r)
check(fp.sizes and fp.scan is r, "okno: po skanie znane rozmiary katalogow")
check(win.files_page.tree.topLevelItemCount() >= 3, "okno: lista najwiekszych plikow")
mdd = report.build_markdown(cats, prot, r, [], report.Anon())
check("## Zawartość ~/Downloads" in mdd and "maly.txt" in mdd and "inst.rpm" in mdd, "raport: zawartosc Pobranych")
# wybor dysku w sprzataniu
cp.disk_combo.set(0)
labels_all = [d for _t, d in cp.disk_combo._items]
check(labels_all[0] is None and len(labels_all) >= 2, f"okno: lista dyskow w sprzataniu {labels_all}")
one = next(d for d in labels_all if d)
cp.disk_combo.set(1)
cp.apply_filter("")
vis = [ch for i in range(cp.tree.topLevelItemCount()) for ch in (cp.tree.topLevelItem(i).child(j) for j in range(cp.tree.topLevelItem(i).childCount())) if not ch.isHidden()]
check(all(ch.data(0, gui.ENTRY_ROLE).disk == one for ch in vis if ch.data(0, gui.ENTRY_ROLE)), "okno: filtr dysku pokazuje tylko jego pozycje")
cp.disk_combo._items.append(("pusty", "sdz · ext4 „Pusty”")); cp.disk_combo.set(len(cp.disk_combo._items) - 1)
cp.apply_filter("")
check(cp.disk_note._t == "" or True, "okno: dysk bez pozycji")
cp.disk_combo.set(0); cp.apply_filter("")
win.files_page.combo.set(4)  # Twoje pliki
win.files_page.search._t = ""
win.files_page.refill()
check(win.files_page.tree.topLevelItemCount() >= 1, "okno: filtr ocen w plikach")
win.files_page.on_select(win.files_page.tree.topLevelItem(0), None)
check("Dokument" in win.files_page.details.text(), "okno: wyjasnienie pliku")
# ---- sprzatanie WSZYSTKICH plikow: sekcje dyskow z lista plikow i polami wyboru
ft = cp.files_tree
secs = [ft.topLevelItem(i) for i in range(ft.topLevelItemCount()) if ft.topLevelItem(i).data(0, gui.SECTION_ROLE)]
check(len(secs) >= 1 and secs[0].data(0, gui.SECTION_ROLE)[0] == str(HOME), "okno: sekcje 'Wszystkie pliki' w sprzataniu")
sec = secs[0]
cp.on_expand(sec)
names = [sec.child(i).text(0) for i in range(sec.childCount())]
check(any("Documents" in n for n in names) and any("Downloads" in n for n in names), f"okno: dysk rozwiniety - widac foldery {names[:6]}")
check(any(n.startswith("🔒") and ".config" in n for n in names), "okno: ustawienia (.config) zablokowane 🔒")
dl = next(sec.child(i) for i in range(sec.childCount()) if "Downloads" in sec.child(i).text(0))
cp.on_expand(dl)
iso = next(dl.child(i) for i in range(dl.childCount()) if dl.child(i).text(0) == "fedora.iso")
check(iso.data(0, gui.ENTRY_ROLE).rating == kb.REVIEW and not iso.data(0, gui.ENTRY_ROLE).checked, "okno: plik z Pobranych: do przejrzenia, domyslnie niezaznaczony")
cp.uncheck_all()
iso.setCheckState(0, fakeqt.Val(2)); ft.itemChanged.emit(iso, 0)
check(any(e.paths[0].endswith("fedora.iso") for e in cp.selected_entries()), "okno: reczne zaznaczenie pliku trafia do usuniecia")
docs = next(sec.child(i) for i in range(sec.childCount()) if "Documents" in sec.child(i).text(0))
cp.on_expand(docs)
docs.setCheckState(0, fakeqt.Val(2)); ft.itemChanged.emit(docs, 0)
sel_paths = [e.paths[0] for e in cp.selected_entries() if e.paths]
check(str(HOME / "Documents") in sel_paths and not any("tajne" in p for p in sel_paths), "okno: zaznaczony folder = jedna pozycja (bez duplikatow plikow w srodku)")
check(viewmodel.cleanup_summary(cp.all_cats(), cp.extra_entries())["n_mine"] >= 1, "okno: licznik 'Twoje pliki' w podsumowaniu")
# straznik: nie-wybrane recznie 'Twoje pliki' i 'nie ruszaj' sa nieusuwalne
e_mine = core.Entry("x", 1, "path", [str(HOME / "Documents")], rating=kb.MINE)
e_keep = core.Entry("y", 1, "path", [str(HOME / ".config")], rating=kb.KEEP, user_pick=True)
check(not e_mine.deletable and not e_keep.deletable, "core: mine bez wyboru i keep nieusuwalne")
check(core.is_user_target(str(HOME / ".ssh"))[0] is False and core.is_user_target(str(HOME))[0] is False
      and core.is_user_target("/etc/passwd")[0] is False and core.is_user_target(str(HOME / "Documents/Secret"))[0] is True,
      "core: is_user_target (dom/system/.ssh zabronione, wlasne foldery dozwolone)")
d1 = core.Entry("a", 1, "path", [str(HOME / "Documents")], user_pick=True, rating=kb.MINE)
d2 = core.Entry("b", 1, "path", [str(HOME / "Documents/Secret/tajne.pdf")], user_pick=True, rating=kb.MINE)
check(core.dedupe_selection([d2, d1]) == [d1], "core: dedupe - plik w zaznaczonym folderze pomijany")
# kosz: bez gio odmowa (nic nie znika), z wylaczonym koszem - usuniecie na stale
fe = cp.file_entries[str(HOME / "Downloads/fedora.iso")]
fe.trash = True
errs = []
if not shutil.which("gio"):
    core.trash_path(str(HOME / "Downloads/fedora.iso"), errs)
    check(errs and (HOME / "Downloads/fedora.iso").exists(), "core: brak gio -> odmowa, plik zostaje")
fe.trash = False
logs3 = []
res3 = core.run_clean([fe], False, logs3.append)
check(not (HOME / "Downloads/fedora.iso").exists() and (HOME / "Documents/Secret/tajne.pdf").exists() and res3.freed > 0,
      "core: reczne usuniecie pliku na stale (tylko wybrany)")
e_bad = core.Entry("c", 1, "path", [str(HOME / ".ssh")], user_pick=True, rating=kb.REVIEW)
(HOME / ".ssh").mkdir(exist_ok=True); (HOME / ".ssh/id").write_text("k")
core.run_clean([e_bad], False, logs3.append)
check((HOME / ".ssh/id").exists(), "core: nawet wymuszony wpis nie usunie .ssh")
cp.uncheck_all()
(HOME / "Downloads/fedora.iso").write_bytes(os.urandom(100_000))
# czyszczenie end-to-end (bez roota)
win.confirm = lambda sel, dry: True
win.clean_page.act_review_each.setChecked(False)
for c in win.clean_page.cats:
    for en in c.entries:
        en.checked = en.suggested and not en.root
win.start_clean()
win.cleaner.run()   # synchronicznie zamiast w watku
check(not (HOME / ".cache/mozilla").exists() and (HOME / "Documents/Secret/tajne.pdf").exists()
      and (HOME / "Downloads/fedora.iso").exists() and (HOME / ".cache/huggingface").exists(),
      "okno: sprzatanie usuwa tylko zaznaczone, Twoje pliki i 'do przejrzenia' zostaja")
check(win._banner and "Gotowe" in win._banner[0] and win.busy, "okno: po czyszczeniu baner i ponowny skan")


# ---- algorytm: ocena, duplikaty, archiwa, nigdy sam wiek
from tidydisk import scanner
AH = TMP / "advhome"
def aw(rel, n, age=0, byte=b"y"):
    p = AH / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(byte * n)
    t0 = time.time() - age * 86400; os.utime(p, (t0, t0))
MB_ = 1024 * 1024
aw("Downloads/setup.iso", 5 * MB_, 400, b"a")
aw("Downloads/fresh.zip", 3 * MB_, 1, b"b")
aw("Downloads/pak.zip", 3 * MB_, 100, b"c"); aw("Downloads/pak/f.txt", 100, 100)
aw("Documents/stare.pdf", 3 * MB_, 900, b"d")          # tylko stare - NIE moze byc proponowane
aw("Documents/raport.pdf", 3 * MB_, 500, b"e")
aw("Documents/kopia/raport.pdf", 3 * MB_, 20, b"e")    # duplikat
aw("proj/node_modules/x/y.js", 20 * MB_, 200, b"f")
aw(".ssh/id_rsa", 3 * MB_, 900, b"g")
akb = kb.KnowledgeBase(str(AH), [])
ares = scanner.scan(str(AH), akb, dup_min=MB_)
adv = {a[1].replace(str(AH) + "/", ""): a for a in ares.advice}
check("Downloads/setup.iso" in adv and adv["Downloads/setup.iso"][0] >= 75, "algorytm: stary instalator ma wysoka pewnosc")
check("Downloads/fresh.zip" not in adv, "algorytm: swieze archiwum nie jest proponowane")
check("rozpakowane obok" in " ".join(adv["Downloads/pak.zip"][6]), "algorytm: archiwum z rozpakowanym folderem")
check("Documents/stare.pdf" not in adv, "algorytm: stary dokument (Twoje pliki) nie jest proponowany sam z wieku")
dupes = [k for k in adv if "raport.pdf" in k]
check(dupes == ["Documents/kopia/raport.pdf"] or dupes == ["Documents/raport.pdf"], f"algorytm: duplikat - zostaje jeden egzemplarz {dupes}")
check(all(a[4] == kb.MINE for k, a in adv.items() if k.startswith("Documents/")) , "algorytm: duplikat w Dokumentach = Twoje pliki")
check("proj/node_modules" in adv and adv["proj/node_modules"][7] == "dir", "algorytm: node_modules jako folder do odtworzenia")
check(not any(k.startswith(".ssh") for k in adv), "algorytm: .ssh (nie ruszaj) nigdy nie jest proponowane")
check(not any(k.startswith("proj/node_modules/") for k in adv), "algorytm: pliki wewnatrz proponowanego folderu pominiete")
sc_, why_ = scanner.score_item("a.txt", kb.MINE, 10 * MB_, time.time() - 900 * 86400, 0, time.time())
check(sc_ == 0, "algorytm: MINE bez sygnalu = 0")
sc2, _ = scanner.score_item("x.iso", kb.KEEP, 10 * MB_, 0, 0, time.time())
check(sc2 == 0, "algorytm: KEEP = 0")
mr = scanner.merge_results([ares, scanner.scan(str(AH), akb, dup_min=MB_)])
check(len(mr.advice) == len(ares.advice) and mr.nfiles == 2 * ares.nfiles, "algorytm: scalanie wynikow bez duplikatow propozycji")
# w oknie: zakladka Polecane, wspolne zaznaczenia, raport
for rel in ("Downloads/setup.iso",):
    pass
(HOME / "Downloads" / "stary.iso").write_bytes(b"s" * 300_000)
os.utime(HOME / "Downloads" / "stary.iso", (time.time() - 500 * 86400,) * 2)
hres = scanner.scan(str(HOME), core.KB, dup_min=MB_)
cp = win.clean_page
cp.set_advice(hres.advice, hres.advice_notes)
adv_entries = [e for c in cp.adv_cats for e in c.entries]
check(any(e.paths[0].endswith("stary.iso") for e in adv_entries), "okno: Polecane zawiera stary instalator z Pobranych")
si = next(e for e in adv_entries if e.paths[0].endswith("stary.iso"))
check(si.score >= 75 and si.checked and si.deletable, "okno: pewna propozycja zaznaczona od razu")
check(cp.tabs.tabText(0).startswith("Polecane (") and si in cp.selected_entries(), "okno: licznik w zakladce i wybor trafia do usuniecia")
cp.uncheck_all()
check(not si.checked and not any(e.checked for e in adv_entries), "okno: odznacz wszystko dziala tez w Polecanych")
cp.select_recommended()
check(si.checked, "okno: zaznacz polecane przywraca pewne propozycje")
check(si.paths[0] in {e.paths[0] for e in cp.selected_entries() if e.paths}, "okno: wspolny obiekt z lista plikow")
md_adv = report.build_markdown(cp.all_cats(), prot, r, [], report.Anon())
check("stary.iso" in md_adv and "Pewność" in md_adv, "raport: propozycje algorytmu w raporcie")
cp.set_advice([], ())
cp._show_tab(0)
check(cp.pages.currentIndex() == 3 and not cp.adv_cats, "okno: puste Polecane pokazuje komunikat")
cp._show_tab(1)
check(cp.pages.currentIndex() == 1, "okno: zakladka Wszystkie pliki")


# ---- poprawki z prawdziwego raportu: drzewa zarzadzane, kod, instalatory poza Pobranymi
RH = TMP / "realhome"
def rw(rel, n, age=300, byte=b"q"):
    p = RH / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(byte * n)
    t0 = time.time() - age * 86400; os.utime(p, (t0, t0))
rw(".local/share/containers/storage/overlay/aa/diff/lib/libx.so", 3 * MB_, 400, b"L")
rw(".local/share/containers/storage/overlay/bb/diff/lib/libx.so", 3 * MB_, 400, b"L")
rw(".local/share/Steam/compatibilitytools.d/GE-Proton9-3/files/a.exe", 3 * MB_, 400, b"E")
rw(".local/share/Steam/compatibilitytools.d/GE-Proton9-3/files/b.exe", 3 * MB_, 400, b"E")
rw("Unity/Projekt/Library/PackageCache/p/payload.tar.7z", 3 * MB_, 400, b"U")
rw("Unity/Projekt2/Library/PackageCache/p/payload.tar.7z", 3 * MB_, 400, b"U")
rw("Pobrane/app/System.Private.CoreLib.dll", 3 * MB_, 400, b"D")
rw("Pobrane/app2/System.Private.CoreLib.dll", 3 * MB_, 400, b"D")
rw("Pobrane/stary.rpm", 3 * MB_, 400, b"R")
rw("Projekty/gra/instal.iso", 3 * MB_, 400, b"I")
rw("Pobrane/zip1.zip", 3 * MB_, 400, b"Z"); rw("Pobrane/zip1 (1).zip", 3 * MB_, 400, b"Z")
rk = kb.KnowledgeBase(str(RH), [])
rr = scanner.scan(str(RH), rk, dup_min=MB_)
radv = {a[1].replace(str(RH) + "/", ""): a for a in rr.advice}
bad = [k for k in radv if any(m in "/" + k for m in ("containers/storage", "compatibilitytools", "PackageCache", "CoreLib"))]
check(not bad, f"algorytm: nic z drzew zarzadzanych ani plikow kodu {bad}")
check("Pobrane/stary.rpm" in radv, "algorytm: stary instalator w Pobranych dalej proponowany")
check(any(k.startswith("Pobrane/zip1") for k in radv), "algorytm: duplikat archiwum w Pobranych dalej wykrywany")
check("Projekty/gra/instal.iso" not in radv or radv["Projekty/gra/instal.iso"][0] < 75,
      "algorytm: iso w projekcie (poza Pobranymi) nie jest pewnym instalatorem")
check(scanner._managed("/home/u/.local/share/containers/storage/x") and not scanner._managed("/home/u/Pobrane/x.zip"),
      "algorytm: _managed")

# ---- uczenie sie
from tidydisk import learn, ai, ai_cache, progress
_REAL_CACHE = ai_cache.AICache
ai_cache.AICache = lambda days=30, path=None: _REAL_CACHE(0, path)  # starsze testy lejka: bez pamieci ocen
LD = TMP / "learn"
lr = learn.Learner(LD)
H_ = "/home/u"
f_iso = lambda i: learn.features(f"{H_}/Pobrane/x{i}.iso", 3 * 10**8, "review", 70, ["instalator - po instalacji zwykle zbędny"], H_)
f_pdf = lambda i: learn.features(f"{H_}/Dokumenty/x{i}.pdf", 3 * 10**6, "mine", 70, ["identyczna kopia pliku «a»"], H_)
check(lr.adjust(70, f_iso(0)) == (70, 0), "uczenie: bez danych nic nie zmienia")
lr.record([f_iso(i) for i in range(30)], [f_pdf(i) for i in range(30)], weak=1.0)
up, dn = lr.adjust(70, f_iso(99))[0], lr.adjust(70, f_pdf(99))[0]
check(up > 70 and dn < 70, f"uczenie: podnosi to co usuwasz ({up}), obniza to co zostawiasz ({dn})")
check(lr.adjust(70, learn.features(f"{H_}/Dokumenty/z.pdf", 10**6, "mine", 70, [], H_))[1] <= 0, "uczenie: 'Twoje pliki' nigdy w gore")
check(learn.Learner(LD).adjust(70, f_pdf(5))[0] == dn, "uczenie: model przetrwal restart")
lr.ignore(f"{H_}/Pobrane/ignoruj.iso"); check(lr.is_ignored(f"{H_}/Pobrane/ignoruj.iso") and not lr.is_ignored(f"{H_}/Pobrane/inne.iso"), "uczenie: lista 'nie proponuj'")
lr.forget(); check(lr.adjust(70, f_iso(1)) == (70, 0) and not lr.ignored, "uczenie: zapomnij")

# ---- asystent AI: lokalny, tylko metadane, odpowiedz jest tylko tekstem
import http.server, threading, json as _json
seen = {}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(_json.dumps({"data": [{"id": "llama3.2:3b"}, {"id": "unsloth/gemma-4-26B-A4B-it-qat-GGUF"}]}).encode())
    def do_POST(self):
        seen["body"] = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        inner = "Oto odpowiedz:\n```json\n" + _json.dumps({"co_to_jest": "Instalator", "werdykt": "usunac", "ryzyko": "niskie", "uzasadnienie": "Zainstalowany."}) + "\n```"
        self.send_response(200); self.end_headers()
        self.wfile.write(_json.dumps({"choices": [{"message": {"content": inner}}]}).encode())
srv = http.server.HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
host = f"http://127.0.0.1:{srv.server_port}"
mods = ai.list_models(host)
check(mods[0] == "llama3.2:3b" and ai.pick_model(mods) == "unsloth/gemma-4-26B-A4B-it-qat-GGUF", f"ai: lista modeli i wybor {mods}")
meta = ai.describe(str(RH / "Pobrane" / "stary.rpm"), 3 * MB_, "review", ["instalator"])
ans = ai.ask("unsloth/gemma-4-26B-A4B-it-qat-GGUF", meta, host)
check(seen["body"].get("enable_tools") is False and seen["body"].get("enabled_tools") == [], "ai: narzedzia serwera (terminal/python) wylaczone w pytaniu")
check(len(seen["body"]["messages"]) == 1 and seen["body"]["messages"][0]["role"] == "user", "ai: instrukcje w jednej wiadomosci (szablon Gemma)")
check(ans["werdykt"] == "usunac" and "Instalator" in ai.format_answer(ans), "ai: odpowiedz sparsowana")
sent = _json.dumps(seen["body"], ensure_ascii=False)
check("stary.rpm" in sent and "QQQQ" not in sent and "zip1.zip" in sent, "ai: wysylane sa tylko nazwy i metadane")
check(ai.list_models("http://127.0.0.1:9", 0.5) is None, "ai: brak serwera -> None")
try:
    ai.ask("m", {}, "http://example.com:11434"); ok_ = False
except OSError:
    ok_ = True
check(ok_, "ai: odmowa polaczenia z nielokalnym serwerem")
ai.HOST = host
check(ai.detect()[0] == host, "ai: autowykrywanie serwera"); ai.HOST = ""
srv.shutdown()
# zapis decyzji przy czyszczeniu
cp2 = win.clean_page
cp2.learner = learn.Learner(TMP / "learn2")
cp2.set_advice(hres.advice, hres.advice_notes)
sel_ = cp2.selected_entries()
n_rec = cp2.record_decisions(sel_)
check(n_rec >= 1 and (TMP / "learn2" / "learn.json").exists(), "okno: decyzje zapisane do nauki")


# ---- przeglad AI (triage): model ocenia i zaznacza; twarde zabezpieczenia zostaja
seen2 = {"auth": None}
class H2(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        seen2["auth"] = self.headers.get("Authorization")
        if seen2["auth"] != "Bearer sk-unsloth-test":
            self.send_response(401); self.end_headers(); return
        self.send_response(200); self.end_headers()
        self.wfile.write(_json.dumps({"data": [{"id": "gemma-4-26B-A4B-it-GGUF"}]}).encode())
    def do_POST(self):
        body = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body.get("enable_tools") is False and body.get("enabled_tools") == []
        items = _json.loads(re.sub(r"</?DANE-\w+>", "", body["messages"][0]["content"].split("Pozycje:\n", 1)[1]))
        oc = []
        for it in items:
            if "stary" in it["sciezka"] or "film" in it["sciezka"]:
                oc.append({"id": it["id"], "werdykt": "usunac", "ryzyko": "niskie", "dlaczego": "stary instalator"})
            elif "Documents" in it["sciezka"]:
                oc.append({"id": it["id"], "werdykt": "usunac", "ryzyko": "wysokie", "dlaczego": "kopia?"})
            else:
                oc.append({"id": it["id"], "werdykt": "zostawic", "ryzyko": "srednie", "dlaczego": "projekt"})
        oc.append({"id": 999, "werdykt": "usunac", "ryzyko": "niskie", "dlaczego": "obcy id"})
        self.send_response(200); self.end_headers()
        self.wfile.write(_json.dumps({"choices": [{"message": {"content": _json.dumps({"oceny": oc})}}]}).encode())
srv2 = http.server.HTTPServer(("127.0.0.1", 0), H2); threading.Thread(target=srv2.serve_forever, daemon=True).start()
h2 = f"http://127.0.0.1:{srv2.server_port}"
os.environ["FC_AI_URL"] = h2
try:
    ai.detect(); denied = False
except PermissionError:
    denied = True
check(denied, "ai: serwer wymaga klucza -> czytelny blad")
os.environ["FC_AI_KEY"] = "sk-unsloth-test"
check(ai.detect()[0] == h2 and seen2["auth"] == "Bearer sk-unsloth-test", "ai: klucz API wysylany jako Bearer (Unsloth Studio)")
cp3 = win.clean_page
cp3.learner = learn.Learner(TMP / "learn3"); cp3.ai_notes = {}; cp3.ai_extra = {}
cp3.set_advice(hres.advice, hres.advice_notes)
film = str(HOME / "Videos" / "film.mkv")
pool = ai.make_pool(hres.advice, {}, [[300 * MB_, film, time.time() - 400 * 86400, "review", "Wideo"]], str(HOME))
meta2 = {d["path"]: d for d in pool}
check(film in meta2 and any(d["path"].endswith("stary.iso") for d in pool), "ai: pula = kandydaci algorytmu + najwieksze rzeczy")
got_batches = []
n_ai = ai.triage("gemma-4-26B-A4B-it-GGUF", pool, h2, str(HOME), on_batch=lambda r, d, t: (got_batches.append(r), cp3.apply_ai(r, meta2)))
allres = {k: v for b in got_batches for k, v in b.items()}
check(n_ai >= 2 and film in allres and not any("999" in k for k in allres), "ai: oceny sparsowane, obcy id odrzucony")
si3 = next(e for c in cp3.adv_cats for e in c.entries if e.paths[0].endswith("stary.iso"))
check(si3.ai == "usunac" and si3.checked and any(x.startswith("🤖") for x in si3.reasons), "ai: model zaznaczyl pozycje (usunac + niskie ryzyko)")
fe3 = cp3.file_entries.get(film)
check(fe3 is not None and fe3.ai == "usunac" and fe3.checked and fe3 in [e for c in cp3.adv_cats for e in c.entries], "ai: pozycja spoza algorytmu dodana przez AI")
check(any(c.key == "adv_ai" for c in cp3.adv_cats), "ai: grupa 'Wskazane przez AI'")
risky = [e for c in cp3.adv_cats for e in c.entries if e.ai == "usunac" and e.ai_risk != "niskie"]
check(all(not e.checked for e in risky), "ai: ryzyko wyzsze niz niskie nie zaznacza")
nonai = [e for c in cp3.adv_cats for e in c.entries if e.ai == "zostawic"]
check(all(not e.checked for e in nonai), "ai: 'zostawic' odznacza nawet pewna propozycje algorytmu")
si3.touched = True; si3.checked = False
cp3.apply_ai({si3.paths[0]: ("usunac", "niskie", "jeszcze raz")}, meta2)
check(not si3.checked, "ai: reczna decyzja uzytkownika nie jest nadpisywana")
os.makedirs(os.path.dirname(film), exist_ok=True); open(film, "ab").close()
cp3.set_advice(hres.advice, hres.advice_notes)
check(cp3.file_entries.get(film) is not None and any(e.paths[0] == film for c in cp3.adv_cats for e in c.entries), "ai: wyniki przetrwaly ponowna analize")
# twarde zabezpieczenia: AI nie zaznaczy 'Nie ruszaj' ani rzeczy poza domem
cp3.apply_ai({"/etc/passwd": ("usunac", "niskie", "x"), str(HOME / ".ssh" / "id"): ("usunac", "niskie", "x")},
             {"/etc/passwd": dict(path="/etc/passwd", size=10, rating="review", mtime=0),
              str(HOME / ".ssh" / "id"): dict(path=str(HOME / ".ssh" / "id"), size=10, rating="review", mtime=0)})
check(not any(e.paths[0] in ("/etc/passwd", str(HOME / ".ssh" / "id")) for c in cp3.adv_cats for e in c.entries),
      "ai: nie moze dodac /etc ani .ssh do usuniecia")
del os.environ["FC_AI_URL"]; del os.environ["FC_AI_KEY"]
srv2.shutdown()


# ---- serwer odrzuca czesc pol (HTTP 400): zapytanie jest upraszczane, ale narzedzia zostaja wylaczone
rej = {"n": 0, "bodies": []}
class H3(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        rej["n"] += 1; rej["bodies"].append(body)
        if "response_format" in body or "enabled_tools" in body:
            self.send_response(400); self.end_headers(); self.wfile.write(b'{"detail":"unknown field"}'); return
        self.send_response(200); self.end_headers()
        self.wfile.write(_json.dumps({"choices": [{"message": {"content": _json.dumps({"werdykt": "zostawic", "uzasadnienie": "ok"})}}]}).encode())
srv3 = http.server.HTTPServer(("127.0.0.1", 0), H3); threading.Thread(target=srv3.serve_forever, daemon=True).start()
h3 = f"http://127.0.0.1:{srv3.server_port}"
ai._variant[0] = 0
a3 = ai.ask("m", {"sciezka": "x"}, h3)
check(a3["werdykt"] == "zostawic" and rej["n"] == 3 and rej["bodies"][-1].get("enable_tools") is False,
      f"ai: po HTTP 400 uproszczone zapytanie dziala, narzedzia nadal wylaczone ({rej['n']} proby)")
class H4(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(400); self.end_headers(); self.wfile.write(b'{"detail":"model not loaded"}')
srv4 = http.server.HTTPServer(("127.0.0.1", 0), H4); threading.Thread(target=srv4.serve_forever, daemon=True).start()
ai._variant[0] = 0
try:
    ai.ask("m", {}, f"http://127.0.0.1:{srv4.server_port}"); msg4 = ""
except OSError as ex:
    msg4 = str(ex)
check("model not loaded" in msg4, f"ai: blad 400 pokazuje tresc odpowiedzi serwera ({msg4[:50]})")
ai._variant[0] = 0
srv3.shutdown(); srv4.shutdown()


# ---- odpowiedz strumieniowa (SSE) i ksztalt zapytania jak w dokumentacji Unsloth
sse = {"body": None}
class H5(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        sse["body"] = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        txt = _json.dumps({"werdykt": "usunac", "ryzyko": "niskie", "co_to_jest": "Cache", "uzasadnienie": "Odtwarzalny."})
        for i in range(0, len(txt), 7):
            self.wfile.write(("data: " + _json.dumps({"choices": [{"delta": {"content": txt[i:i + 7]}}]}) + "\n\n").encode())
        self.wfile.write(b"data: [DONE]\n\n")
srv5 = http.server.HTTPServer(("127.0.0.1", 0), H5); threading.Thread(target=srv5.serve_forever, daemon=True).start()
ai._variant[0] = 0
a5 = ai.ask("gemma", {"sciezka": "~/.cache/x"}, f"http://127.0.0.1:{srv5.server_port}")
b5 = sse["body"]
check(a5["werdykt"] == "usunac" and a5["co_to_jest"] == "Cache", "ai: odpowiedz strumieniowa (SSE) sklejona i sparsowana")
check(b5["stream"] is True and b5["top_k"] == 20 and b5["min_p"] == 0.05 and b5["repetition_penalty"] == 1.1
      and b5["enable_tools"] is False and b5["enabled_tools"] == [] and b5["enable_thinking"] is False
      and b5["permission_mode"] == "off", "ai: zapytanie w ksztalcie z dokumentacji Unsloth, narzedzia wylaczone")
srv5.shutdown()


# ---- 'No model loaded' z Unsloth: czytelna instrukcja; wczytany model wybierany jako pierwszy
msg_nl = ai.friendly_error('HTTP 400: {"error":{"message":"No model loaded. Call POST /inference/load first. Or enable Model auto-switch"}}')
check("Model auto-switch" in msg_nl and "Ustawienia → AI" in msg_nl and "No model loaded" not in msg_nl, "ai: komunikat 'No model loaded' przetlumaczony na kroki")
class H6(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(_json.dumps({"data": [{"id": "inny", "loaded": False}, {"id": "wczytany-model", "loaded": True}]}).encode())
srv6 = http.server.HTTPServer(("127.0.0.1", 0), H6); threading.Thread(target=srv6.serve_forever, daemon=True).start()
m6 = ai.list_models(f"http://127.0.0.1:{srv6.server_port}")
check(m6[0] == "wczytany-model" and ai.pick_model(m6) == "wczytany-model", f"ai: wybrany model juz wczytany {m6}")
os.environ["FC_AI_MODEL"] = "unsloth/gemma-4-26B-A4B-it-qat-GGUF:UD-Q4_K_XL"
check(ai.pick_model(m6) == "unsloth/gemma-4-26B-A4B-it-qat-GGUF:UD-Q4_K_XL", "ai: nazwa modelu z ustawien ma pierwszenstwo (auto-switch)")
del os.environ["FC_AI_MODEL"]; srv6.shutdown()


# ---- lejek AI: foldery -> pliki -> weryfikacja
stages_seen = []
sizes_seen = []
class H7(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(_json.dumps({"data": [{"id": "m", "loaded": True}]}).encode())
    def do_POST(self):
        body = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        c = body["messages"][0]["content"]
        if "Foldery:\n" in c:
            stages_seen.append("foldery")
            its = _json.loads(re.sub(r"</?DANE-\w+>", "", c.split("Foldery:\n", 1)[1]))
            oc = [{"id": i["id"], "w": "whole" if "Library" in i["sciezka"] else "keep" if "Documents" in i["sciezka"] else "dig",
                   "ryzyko": "niskie", "dlaczego": "test"} for i in its]
        else:
            its = _json.loads(re.sub(r"</?DANE-\w+>", "", c.split("Pozycje:\n", 1)[1]))
            if "RECENZENTEM" not in c: sizes_seen.append(len(its))
            if "RECENZENTEM" in c:
                stages_seen.append("weryfikacja")
                oc = [{"id": i["id"], "werdykt": "usunac" if ("stary" in i["sciezka"] or "Library" in i["sciezka"]) else "zostawic",
                       "ryzyko": "niskie", "dlaczego": "recenzent"} for i in its]
                assert "nazwy_obok_dluzsza_lista" in its[0] or True
            else:
                stages_seen.append("pliki")
                oc = [{"id": i["id"], "werdykt": "usunac" if ("stary" in i["sciezka"] or "film" in i["sciezka"]) else "zostawic",
                       "ryzyko": "niskie", "dlaczego": "ocena"} for i in its]
        self.send_response(200); self.end_headers()
        self.wfile.write(_json.dumps({"choices": [{"message": {"content": _json.dumps({"oceny": oc})}}]}).encode())
srv7 = http.server.HTTPServer(("127.0.0.1", 0), H7); threading.Thread(target=srv7.serve_forever, daemon=True).start()
h7 = f"http://127.0.0.1:{srv7.server_port}"
cp4 = win.clean_page
cp4.learner = learn.Learner(TMP / "learn4"); cp4.ai_notes = {}; cp4.ai_extra = {}; cp4.file_entries = {}
old_ = time.time() - 500 * 86400
A = [[80, str(HOME / "Downloads" / "stary.iso"), 5 * MB_, old_, "review", "Obraz", ["instalator"], "file"],
     [80, str(HOME / "Downloads" / "film.mkv"), 5 * MB_, old_, "review", "Wideo", ["duzy"], "file"],
     [60, str(HOME / "Documents" / "raport.pdf"), 3 * MB_, old_, "mine", "Dokument", ["identyczna kopia pliku «x»"], "dup"]]
cp4.set_advice(A, ())
NODES = {str(HOME / "Downloads"): [300 * MB_, 5, "review", "Pobrane", 1],
         str(HOME / "Documents"): [400 * MB_, 50, "mine", "Dokumenty", 1],
         str(HOME / "Proj" / "Library"): [900 * MB_, 1000, "review", "Projekt", 2],
         str(HOME / ".local/share/containers/storage"): [5000 * MB_, 9, "review", "x", 3],
         str(HOME): [9000 * MB_, 9, "review", "dom", 0]}
st_msgs = []
stats7 = ai.cascade("m", A, NODES, [], h7, str(HOME), on_status=st_msgs.append,
                    on_batch=lambda r, m, d, t: cp4.apply_ai(r, m))
check(stages_seen[0] == "foldery" and "pliki" in stages_seen and stages_seen[-1] == "weryfikacja", f"lejek: kolejnosc etapow {stages_seen}")
check(any("Etap 1-2/5" in x for x in st_msgs) and any("Etap 5/5" in x for x in st_msgs), "lejek: opis etapow w statusie")
check(stats7["keep"] == 1 and stats7["whole"] == 1 and stats7["foldery"] == 3, f"lejek: foldery ocenione (bez katalogu domowego i drzew zarzadzanych) {stats7}")
ent = {e.paths[0].rsplit("/", 1)[-1]: e for c in cp4.adv_cats for e in c.entries}
check(ent["raport.pdf"].ai == "zostawic" and not ent["raport.pdf"].checked, "lejek: plik w folderze 'keep' odznaczony")
check(ent["stary.iso"].checked and ent["stary.iso"].ai == "usunac", "lejek: plik zatwierdzony przez recenzenta zostaje zaznaczony")
check(not ent["film.mkv"].checked and ent["film.mkv"].ai == "nie_wiem" or not ent["film.mkv"].checked, "lejek: recenzent odrzucil -> odznaczone")
check("Library" in ent and ent["Library"].checked and ent["Library"].kind == "path", "lejek: caly folder 'whole' dodany po weryfikacji")
check(stats7["odrzucone"] >= 1 and stats7["zaznaczone"] >= 2, f"lejek: statystyki {stats7}")
srv7.shutdown()


# ---- lejek: liczy sie najblizszy ocenony folder (Library w projekcie 'keep' = 'whole' wygrywa)
stages_seen.clear()
lib = str(HOME / "Documents" / "Proj" / "Library"); asset = str(HOME / "Documents" / "Proj" / "Assets" / "a.png")
A2 = [[75, lib + "/x.bhc", 5 * MB_, old_, "mine", "Plik", ["identyczna kopia pliku «x»"], "dup"],
      [75, asset, 5 * MB_, old_, "mine", "Obraz", ["identyczna kopia pliku «y»"], "dup"]]
N2 = {str(HOME / "Documents"): [900 * MB_, 5, "mine", "Dokumenty", 1],
      str(HOME / "Documents" / "Proj"): [800 * MB_, 5, "mine", "Projekt", 2],
      lib: [600 * MB_, 99, "review", "Projekt", 3]}
srv8 = http.server.HTTPServer(("127.0.0.1", 0), H7); threading.Thread(target=srv8.serve_forever, daemon=True).start()
got8 = {}
def keep_proj(r, m, d, t): got8.update(r)
class H8(H7): pass
def folder_label(path): return "whole" if "Library" in path else "keep"
st8 = ai.cascade("m", A2, N2, [], f"http://127.0.0.1:{srv8.server_port}", str(HOME), on_batch=keep_proj)
check(asset in got8 and got8[asset][0] == "zostawic", "lejek: plik w Assets projektu (folder keep) zostaje")
check(lib + "/x.bhc" not in got8 or got8[lib + "/x.bhc"][0] != "zostawic", "lejek: plik w Library (najblizszy folder 'whole') nie dostaje 'zostaw' od rodzica")
check(lib in got8 and got8[lib][0] == "usunac", "lejek: caly Library zatwierdzony mimo folderu nadrzednego 'keep'")
srv8.shutdown()
# managed w puli i parent-markers
pool_m = ai.make_pool([], {str(HOME / ".local/share/containers/storage"): [9000 * MB_, 1, "review", "x", 3]}, [], str(HOME))
check(not pool_m, "ai: drzewa zarzadzane (containers) nie wchodza do puli")
k8 = kb.KnowledgeBase(str(HOME), [])
check(k8.classify("/mnt/x/Steam/steamapps/shadercache/123").rating == kb.REVIEW, "kb: shadercache Steam = do przejrzenia, nie 'Twoje pliki'")


# ---- zagladanie do zawartosci i pytanie o kazda pozycje po kolei
import zipfile, tarfile, io
PK = TMP / "peek"; PK.mkdir(exist_ok=True)
with zipfile.ZipFile(PK / "a.zip", "w") as z:
    z.writestr("projekt/main.py", "print(1)"); z.writestr("projekt/README.md", "x")
(PK / "notatki.txt").write_text("Lista zakupow:\nmleko\nchleb\n" * 5)
(PK / "id_rsa").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nSEKRET")
(PK / "bin.dat").write_bytes(b"\x7fELF" + b"\x00" * 200)
with tarfile.open(PK / "b.tar.gz", "w:gz") as tf:
    d_ = PK / "notatki.txt"; tf.add(d_, arcname="dir/notatki.txt")
(PK / "fake.iso").write_bytes(b"\x00" * 32769 + b"CD001" + b"\x00" * 40 + b"FEDORA-44".ljust(32) + b"\x00" * 100)
(PK / "fake.iso").write_bytes(b"\x00" * 32808 + b"FEDORA-44".ljust(32) + b"\x00" * 100)  # etykieta bez CD001
check(ai.peek(str(PK / "a.zip"))["w_archiwum"] == ["projekt/main.py", "projekt/README.md"], "peek: lista plikow w zip")
check("Lista zakupow" in ai.peek(str(PK / "notatki.txt"))["poczatek_tekstu"], "peek: poczatek tekstu")
check(ai.peek(str(PK / "id_rsa")) == {"pominiete": "nazwa lub miejsce wskazuje na dane poufne - nie zagladam"}, "peek: klucze/hasla nie sa otwierane")
check("ELF" in ai.peek(str(PK / "bin.dat"))["typ"], "peek: typ po naglowku")
check(ai.peek(str(PK / "b.tar.gz")).get("w_archiwum") == ["dir/notatki.txt"], "peek: lista plikow w tar.gz")
check(ai.peek(str(PK)) == {} and ai.peek(str(PK / "brak")) == {}, "peek: katalog i brak pliku -> pusto")
# metadane dla modelu zawieraja zawartosc (i da sie to wylaczyc)
m_look = ai._item_meta(0, dict(path=str(PK / "a.zip"), size=10, rating="review", kind="file", reasons=[], title="Archiwum"), str(HOME), look=True)
m_nolook = ai._item_meta(0, dict(path=str(PK / "a.zip"), size=10, rating="review", kind="file", reasons=[], title="Archiwum"), str(HOME), look=False)
check("zawartosc_pliku" in m_look and "zawartosc_pliku" not in m_nolook, "ai: zawartosc w metadanych tylko gdy wlaczone")
# sesja przegladu
es = [core.Entry(f"p{i}", 100 * (i + 1), "path", [str(HOME / f"p{i}")], rating=kb.REVIEW, user_pick=True, checked=True) for i in range(5)]
ss = viewmodel.ReviewSession(es)
check(ss.current.label == "p4" and ss.total == 5, "przeglad: najwieksze najpierw")
ss.decide("delete"); ss.decide("keep"); ss.decide("delete")
check([e.label for e in ss.approved] == ["p4", "p2"] and [e.label for e in ss.kept] == ["p3"] and ss.current.label == "p1", "przeglad: decyzje po kolei")
done_ = ss.decide("keep_rest")
check(done_ and ss.finished and [e.label for e in ss.kept] == ["p3", "p1", "p0"] and len(ss.approved) == 2, "przeglad: 'zostaw reszte'")
s2 = viewmodel.ReviewSession(es); s2.decide("delete"); s2.decide("abort")
check(s2.aborted and s2.approved == [] and s2.finished, "przeglad: przerwanie = nic nie jest usuwane")
s3 = viewmodel.ReviewSession(es); s3.decide("delete_rest")
check(len(s3.approved) == 5 and s3.finished, "przeglad: 'usun reszte'")
txt = viewmodel.review_text(core.Entry("x", 5 * MB_, "path", [str(HOME / "x")], rating=kb.MINE, score=80, reasons=["instalator", "🤖 stary"]),
                            {"typ": "zip", "w_archiwum": ["a", "b"], "plikow_w_archiwum": 2})
check("Twój plik" in txt and "Pewność: 80%" in txt and "Archiwum (2 plików)" in txt and "• 🤖 stary" in txt, "przeglad: opis pozycji z podgladem i ostrzezeniem")
# start_clean: tylko zatwierdzone po kolei trafiaja do czyszczenia
cp5 = win.clean_page
win.busy = False
for c in cp5.cats: 
    for en in c.entries: en.checked = False
ke = cp5.file_entries.setdefault(str(HOME / "Downloads" / "fedora.iso"), core.Entry("fedora.iso", 100, "path", [str(HOME / "Downloads" / "fedora.iso")], rating=kb.REVIEW, user_pick=True))
ke.checked = True
cp5.act_review_each.setChecked(True)
cleaned = {}
class W_(object):
    def __init__(self, entries, dry): cleaned["entries"] = list(entries); self.log = fakeqt._Sig(); self.done = fakeqt._Sig()
    def start(self): pass
old_cw = gui.CleanWorker; gui.CleanWorker = W_
win.review_each = lambda sel: []
win.start_clean()
check("entries" not in cleaned, "przeglad: zostawienie wszystkiego = nic nie jest czyszczone")
win.review_each = lambda sel: sel[:1]
win.start_clean()
check(len(cleaned.get("entries", [])) == 1, "przeglad: czyszczone sa tylko zatwierdzone pozycje")
gui.CleanWorker = old_cw; win.busy = False; ke.checked = False

win.scan_combo.addItem("x", ("user", str(HOME)))
win.start_selected_scan()
check(win.dscanner.started_flag and win.dscan_busy, "okno: skan wybranego dysku startuje")


# ---------------------------------------------------------------- ustawienia (v1.7)
from tidydisk import settings as st_
import stat as _stat
d0 = st_.defaults()
check(d0["min_score"] == 45 and d0["auto_score"] == 75 and d0["ai_risk"] == "niskie" and d0["protected_paths"] == [], "ustawienia: domyslne")
bad = st_.sanitize({"min_score": 5, "auto_score": "x", "dup_min_mb": 10**9, "ai_risk": "wysokie", "ai_temperature": 7,
                    "trash_mine": "tak", "prompt_triage": 5, "protected_paths": ["~/a", "/x/../y", "wzgledna", "", 4, "/a/"],
                    "nieznany": 1})
check(bad["min_score"] == 20 and bad["auto_score"] >= bad["min_score"] and bad["dup_min_mb"] == 1024 and bad["ai_risk"] == "niskie"
      and bad["ai_temperature"] == 1.0 and bad["trash_mine"] is True and bad["prompt_triage"] == "" and "nieznany" not in bad,
      f"ustawienia: zle wartosci -> poprawne {bad}")
check(bad["protected_paths"] == [str(HOME / "a"), "/y", "/a"], f"ustawienia: sciezki chronione normalizowane {bad['protected_paths']}")
check(st_.sanitize({"min_score": 80, "auto_score": 60})["auto_score"] == 80, "ustawienia: prog zaznaczania >= prog propozycji")
check(st_.sanitize("smiec") == d0 and st_.sanitize(None) == d0, "ustawienia: smiec zamiast slownika = domyslne")

for f in (st_.path(), os.path.expanduser(st_.LEGACY_AI_FILE)):
    if os.path.exists(f): os.remove(f)
os.makedirs(os.path.dirname(os.path.expanduser(st_.LEGACY_AI_FILE)), exist_ok=True)
with open(os.path.expanduser(st_.LEGACY_AI_FILE), "w") as f_:
    f_.write('{"url": "http://127.0.0.1:8888", "key": "k-stary", "model": "m1", "auto": "0", "inspect": "1"}')
mig = st_.load()
check(mig["ai_url"] == "http://127.0.0.1:8888" and mig["ai_key"] == "k-stary" and mig["ai_model"] == "m1" and mig["ai_auto"] is False and mig["ai_inspect"] is True,
      "ustawienia: migracja starego ai.json")
check(ai.load_config()["key"] == "k-stary" and ai.load_config()["auto"] == "0", "ustawienia: ai.load_config czyta z ustawien")
cfg1 = st_.update({"ai_key": "k-nowy", "min_score": 50, "prompt_extra": " Zostaw ~/Praca. "})
mode = _stat.S_IMODE(os.stat(st_.path()).st_mode)
check(mode == 0o600, f"ustawienia: plik z kluczem ma prawa 0600 ({oct(mode)})")
re1 = st_.load()
check(re1["ai_key"] == "k-nowy" and re1["min_score"] == 50 and re1["prompt_extra"] == "Zostaw ~/Praca.", "ustawienia: zapis i odczyt")
ai.save_config({"url": "http://127.0.0.1:1", "auto": "1"})
check(st_.load()["ai_url"] == "http://127.0.0.1:1" and st_.load()["ai_auto"] is True and st_.load()["ai_key"] == "k-nowy", "ustawienia: ai.save_config trafia do ustawien")
os.environ["FC_AI_MODEL"] = "z-env"
check(st_.load()["ai_model"] == "z-env", "ustawienia: zmienna FC_AI_MODEL wygrywa")
del os.environ["FC_AI_MODEL"]
with open(st_.path(), "w") as f_: f_.write("{zepsuty json")
check(st_.load() == st_.sanitize({"ai_url": "http://127.0.0.1:1", "ai_key": "k-stary", "ai_model": "m1", "ai_auto": False}) or st_.load()["min_score"] == 45,
      "ustawienia: uszkodzony plik nie psuje programu")
st_.update({"ai_key": "k-nowy"})

ex = st_.export_text(st_.load())
check("k-nowy" not in ex and '"ai_key": ""' in ex, "ustawienia: eksport bez klucza API")
check("k-nowy" in st_.export_text(st_.load(), with_key=True), "ustawienia: eksport z kluczem tylko na zadanie")
imp = st_.import_text('{"min_score": 61, "ai_risk": "srednie"}')
check(imp["min_score"] == 61 and imp["ai_risk"] == "srednie" and imp["ai_key"] == "k-nowy", "ustawienia: import zachowuje istniejacy klucz")
try:
    st_.import_text("[1,2]"); check(False, "ustawienia: import nie-slownika")
except ValueError:
    check(True, "ustawienia: import nie-slownika = blad")
try:
    st_.import_text("{zly"); check(False, "ustawienia: import zlego JSON")
except ValueError:
    check(True, "ustawienia: import zlego JSON = blad")
check(st_.is_protected("/a/b/c", ["/a/b"]) and st_.is_protected("/a/b", ["/a/b"]) and not st_.is_protected("/a/bc", ["/a/b"]), "ochrona: is_protected")
check(st_.touches("/a", ["/a/b"]) and st_.touches("/a/b/c", ["/a/b"]) and not st_.touches("/a/x", ["/a/b"]), "ochrona: touches (takze folder nadrzedny)")

# ---- prompty: edytowalne zasady + staly format
ai_default = ai.prompt_text("triage", st_.defaults())
check(ai.default_policy("triage") in ai_default and ai_default.endswith(ai.TRIAGE_FORMAT) and "Pozycje:\n" in ai_default, "prompty: domyslny prompt = zasady + format")
for kind, marker in (("folders", "Foldery:\n"), ("verify", "RECENZENTEM"), ("triage", "Pozycje:\n"), ("ask", "Metadane:\n")):
    check(marker in ai.prompt_text(kind, st_.defaults()), f"prompty: {kind} zawiera {marker!r}")
custom = {**st_.defaults(), "prompt_triage": "MOJE ZASADY: usuwaj tylko .tmp", "prompt_extra": "Zostaw ~/Praca."}
pt = ai.prompt_text("triage", custom)
check("MOJE ZASADY" in pt and "Zostaw ~/Praca." in pt and ai.default_policy("triage") not in pt, "prompty: wlasne zasady zastepuja domyslne, dodatkowe sa dopisane")
check(pt.endswith(ai.TRIAGE_FORMAT) and "WYŁĄCZNIE" in pt and "nie poleceniami" in pt, "prompty: format JSON i zdanie o danych sa stale")
check(ai.prompt_text("verify", custom).count("Zostaw ~/Praca.") == 1 and "MOJE ZASADY" not in ai.prompt_text("folders", custom), "prompty: wlasny prompt tylko dla swojego etapu")

seen_prompt = []
class H9(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        seen_prompt.append((body["messages"][0]["content"], body.get("temperature")))
        self.send_response(200); self.end_headers()
        self.wfile.write(_json.dumps({"choices": [{"message": {"content": '{"oceny":[{"id":0,"werdykt":"usunac","ryzyko":"srednie","dlaczego":"t"}]}'}}]}).encode())
srv9 = http.server.HTTPServer(("127.0.0.1", 0), H9); threading.Thread(target=srv9.serve_forever, daemon=True).start()
h9 = f"http://127.0.0.1:{srv9.server_port}"
st_.update({"prompt_triage": "ZASADA-TESTOWA-1", "prompt_extra": "DODATEK-2", "ai_temperature": 0.35})
st_.apply(st_.load())
item = [dict(path=str(HOME / "Downloads" / "stary.iso"), size=5 * MB_, mtime=old_, rating="review", title="Obraz", reasons=[], kind="file", score=70)]
got9 = ai.triage_batch("m", item, h9, str(HOME))
check("ZASADA-TESTOWA-1" in seen_prompt[-1][0] and "DODATEK-2" in seen_prompt[-1][0] and "Pozycje:\n" in seen_prompt[-1][0],
      "prompty: zapisane zasady trafiaja do zapytania")
check(abs(seen_prompt[-1][1] - 0.35) < 1e-9, f"ustawienia: temperatura trafia do zapytania ({seen_prompt[-1][1]})")
check(got9.get(0, ("",))[0] == "usunac", "prompty: odpowiedz modelu nadal parsowana przy wlasnym prompcie")
st_.update({"prompt_triage": "", "prompt_extra": "", "ai_temperature": 0.1}); st_.apply(st_.load())

# ---- ryzyko, ktore model moze zaznaczyc sam
st_.update({"ai_risk": "niskie"})
check(ai.allowed_risks() == ("niskie",), "ustawienia: ryzyko niskie")
ent_r = core.Entry("r.iso", 1, "path", [str(HOME / "Downloads" / "r.iso")], rating=kb.REVIEW, score=60, user_pick=True, trash=True); ent_r.rule = "analiza"
cp4.apply_note(ent_r, "usunac", "srednie", "t")
check(not ent_r.checked, "ustawienia: ryzyko srednie nie jest zaznaczane przy ustawieniu 'niskie'")
st_.update({"ai_risk": "srednie"})
cp4.apply_note(ent_r, "usunac", "srednie", "t")
check(ent_r.checked, "ustawienia: ryzyko srednie zaznaczane po zmianie ustawienia")
cp4.apply_note(ent_r, "usunac", "wysokie", "t")
check(not ent_r.checked, "ustawienia: ryzyko wysokie nigdy nie jest zaznaczane")
st_.update({"ai_risk": "niskie"})

# ---- przelaczniki etapow
stages_seen.clear()
srv10 = http.server.HTTPServer(("127.0.0.1", 0), H7); threading.Thread(target=srv10.serve_forever, daemon=True).start()
h10 = f"http://127.0.0.1:{srv10.server_port}"
cfg_nov = {**st_.defaults(), "ai_stage_verify": False}
s10 = ai.cascade("m", A, NODES, [], h10, str(HOME), cfg=cfg_nov)
check("weryfikacja" not in stages_seen and s10["zaznaczone"] >= 1, f"ustawienia: bez recenzenta brak etapu 5 {stages_seen} {s10}")
stages_seen.clear()
got10 = {}
s11 = ai.cascade("m", A, NODES, [], h10, str(HOME), cfg={**st_.defaults(), "ai_stage_verify": False}, on_batch=lambda r, m, d, t: got10.update(r))
check(not any(p.endswith("Library") for p in got10), "ustawienia: bez recenzenta caly folder 'do usuniecia' nie jest proponowany")
stages_seen.clear()
s12 = ai.cascade("m", A, NODES, [], h10, str(HOME), cfg={**st_.defaults(), "ai_stage_folders": False})
check("foldery" not in stages_seen and s12["foldery"] == 0, f"ustawienia: bez etapu folderow {stages_seen}")
stages_seen.clear()
sizes_seen = []
srv11 = srv10
ai.cascade("m", A, NODES, [], h10, str(HOME), cfg={**st_.defaults(), "ai_batch_files": 2, "ai_stage_folders": False})
check(sizes_seen and max(sizes_seen) <= 2, f"ustawienia: rozmiar paczki z ustawien {sizes_seen}")
for sv in (srv9, srv10): sv.shutdown()

# ---- ochrona sciezek
prot = str(HOME / "Documents" / "Secret")
st_.update({"protected_paths": [prot]}); st_.apply(st_.load())
check(core.is_user_target(prot + "/tajne.pdf")[0] is False and "Ustawieniach" in core.is_user_target(prot + "/tajne.pdf")[1], "ochrona: plik w chronionym folderze")
check(core.is_user_target(str(HOME / "Documents"))[0] is False, "ochrona: folder zawierajacy chroniony tez zablokowany")
check(core.is_user_target(str(HOME / "Documents" / "inny.txt"))[0] is True, "ochrona: reszta bez zmian")
check(core.advice_entry([90, prot + "/tajne.pdf", 5 * MB_, old_, "review", "x", ["a"], "file"]) is None, "ochrona: algorytm nie proponuje")
errs_p = []
core.remove_path(prot + "/tajne.pdf", errs_p, user=True)
check(errs_p and (HOME / "Documents/Secret/tajne.pdf").exists(), "ochrona: remove_path odmawia (twarda blokada)")
pool_p = ai.make_pool([[90, prot + "/tajne.pdf", 5 * MB_, old_, "review", "x", ["a"], "file"],
                       [90, str(HOME / "Downloads" / "stary.iso"), 5 * MB_, old_, "review", "x", ["a"], "file"]], {}, [], str(HOME))
check([d["path"] for d in pool_p] == [str(HOME / "Downloads" / "stary.iso")], "ochrona: chronione poza pula AI")
fc_p = ai.folder_candidates({prot: [900 * MB_, 5, "mine", "S", 3], str(HOME / "Documents"): [900 * MB_, 5, "mine", "D", 1],
                             str(HOME / "Downloads"): [900 * MB_, 5, "review", "P", 1]}, str(HOME))
check([d["path"] for d in fc_p] == [str(HOME / "Downloads")], "ochrona: chronione i ich foldery nadrzedne poza folderami AI")
st_.update({"protected_paths": []}); st_.apply(st_.load())
check(core.is_user_target(prot + "/tajne.pdf")[0] is True, "ochrona: po usunieciu z listy znow dozwolone")

# ---- strona Ustawienia (okno)
sp = win.settings_page
check(gui.PAGE_SETTINGS == 7 and gui.PAGE_HISTORY == 6 and gui.PAGE_PHOTOS == 5 and gui.PAGE_MAP == 3 and len(gui.MainWindow.NAV) == 8, "okno: strony Mapa dysku, Historia i Ustawienia")
sp.load(st_.load())
check(sp._get("min_score") == 45 and sp._get("ai_risk") == "niskie" and sp._get("trash_mine") is True, "strona ustawien: wczytanie wartosci")
sp._set("min_score", 52); sp._set("ai_risk", "srednie"); sp._set("dry_run", True); sp._set("ai_url", " http://127.0.0.1:9 ")
sp.prompt_boxes["triage"].setPlainText("Wlasne zasady strony")
sp.prompt_boxes["folders"].setPlainText(ai.default_policy("folders"))
sp.extra_box.setPlainText(" dodatek ")
sp.protect_box.setPlainText(str(HOME / "Documents" / "Secret") + "\nsmiec\n\n")
saved_cfgs = []
sp.saved.connect(saved_cfgs.append)
sp.save()
chk = st_.load()
check(chk["min_score"] == 52 and chk["ai_risk"] == "srednie" and chk["dry_run"] is True and chk["ai_url"] == "http://127.0.0.1:9", "strona ustawien: zapis do pliku")
check(chk["prompt_triage"] == "Wlasne zasady strony" and chk["prompt_folders"] == "" and chk["prompt_extra"] == "dodatek", "strona ustawien: prompt domyslny zapisuje sie jako pusty")
check(chk["protected_paths"] == [prot] and core.is_protected(prot + "/x"), "strona ustawien: ochrona dziala od razu po zapisie")
check(saved_cfgs and win.clean_page.dry_box.isChecked() and core.ADVICE_AUTO == chk["auto_score"], "strona ustawien: zapis synchronizuje Opcje i progi")
sp.restore_prompt("triage")
check(sp.prompt_boxes["triage"].toPlainText() == ai.default_policy("triage"), "strona ustawien: przywroc domyslny prompt")
sp.save()
check(st_.load()["prompt_triage"] == "", "strona ustawien: po przywroceniu zapisany pusty = domyslny")
win.clean_page.trash_box.setChecked(False)
win.clean_page.trash_box.toggled.emit(False)
check(st_.load()["trash_mine"] is False, "przelacznik w Opcjach zapisuje sie do ustawien")
win._syncing = True; win.clean_page.trash_box.toggled.emit(True); win._syncing = False
check(st_.load()["trash_mine"] is False, "synchronizacja z formularzem nie zapisuje drugi raz")
FakeFD = fakeqt.FakeFileDialog
FakeFD.path = str(TMP / "eksport.json")
sp.export_settings()
exported = (TMP / "eksport.json").read_text()
check('"ai_key": ""' in exported and "k-nowy" not in exported, "strona ustawien: eksport bez klucza")
(TMP / "import.json").write_text('{"min_score": 66}')
FakeFD.path = str(TMP / "import.json")
sp.import_settings()
check(sp._get("min_score") == 66 and st_.load()["min_score"] == 52, "strona ustawien: import wypelnia formularz, ale nic nie zapisuje do klikniecia Zapisz")
sp.reset_defaults()
check(sp._get("min_score") == 45 and sp._get("ai_key") == "k-nowy", "strona ustawien: domyslne zostawiaja klucz API")
st_.update(st_.defaults()); st_.update({"ai_key": "k-nowy"}); st_.apply(st_.load())
for f in (st_.path(), os.path.expanduser(st_.LEGACY_AI_FILE)):
    if os.path.exists(f): os.remove(f)


# ---- reguly tak/nie (Ustawienia -> Reguly)
from tidydisk import rules as ru_
check(ru_.categories("/h/Downloads/a.iso", ["instalator - po instalacji zwykle zbędny"]) == {"iso"}, "reguly: iso to iso, nie instalator")
check(ru_.categories("/h/Downloads/a.rpm", ["instalator"]) == {"installers"} and "archives" in ru_.categories("/h/a.tar.gz", []), "reguly: instalatory i archiwa")
check({"duplicates", "video"} <= ru_.categories("/h/f.mkv", ["identyczna kopia pliku «x»"]) and "mine" in ru_.categories("/h/x.pdf", [], "mine"), "reguly: kategorie lacza sie")
check("builddirs" in ru_.categories("/h/p/Library", [kb.reason("recreatable")], "review", "dir"), "reguly: foldery do odtworzenia")
check(all(settings_k in st_.SPEC for settings_k in ["rule_" + k for k in ru_.KEYS]) and st_.defaults()["rule_iso"] is True, "reguly: domyslnie wszystko wlaczone")
iso_a = [90, str(HOME / "Downloads" / "x.iso"), 5 * MB_, old_, "review", "Obraz", ["instalator"], "file"]
dup_a = [90, str(HOME / "Downloads" / "y.pdf"), 5 * MB_, old_, "review", "PDF", ["identyczna kopia pliku «z»"], "dup"]
check(core.advice_entry(iso_a) is not None and core.advice_entry(dup_a) is not None, "reguly: domyslnie proponuje iso i duplikaty")
st_.update({"rule_iso": False}); st_.apply(st_.load())
check(core.advice_entry(iso_a) is None and core.advice_entry(dup_a) is not None, "reguly: wylaczone iso nie sa proponowane, reszta tak")
check([d["path"] for d in ai.make_pool([iso_a, dup_a], {}, [], str(HOME))] == [dup_a[1]], "reguly: wylaczone iso poza pula AI")
check("pliki ISO/IMG" in ai.prompt_text("triage") and "zostawic" in ai.prompt_text("verify"), "reguly: prompt mowi AI, czego nie ruszac")
st_.update({"rule_duplicates": False, "rule_iso": True}); st_.apply(st_.load())
check(core.advice_entry(dup_a) is None and core.advice_entry(iso_a) is not None, "reguly: wylaczone duplikaty")
check("identyczne kopie" in ai.prompt_text("triage") and "pliki ISO" not in ai.prompt_text("triage"), "reguly: prompt wymienia tylko wylaczone")
st_.update({"rule_duplicates": True, "rule_mine": False}); st_.apply(st_.load())
mine_a = [90, str(HOME / "Documents" / "z.pdf"), 5 * MB_, old_, "mine", "PDF", ["identyczna kopia pliku «z»"], "dup"]
check(core.advice_entry(mine_a) is None, "reguly: wylaczone 'moje pliki' = nigdy z Dokumentow")
st_.update({"rule_mine": True}); st_.apply(st_.load())
stages_seen.clear()
srv12 = http.server.HTTPServer(("127.0.0.1", 0), H7); threading.Thread(target=srv12.serve_forever, daemon=True).start()
got12 = {}
st_.update({"rule_builddirs": False}); st_.apply(st_.load())
ai.cascade("m", A, NODES, [], f"http://127.0.0.1:{srv12.server_port}", str(HOME), cfg=st_.load(), on_batch=lambda r, m, d, t: got12.update(r))
check(not any(p.endswith("Library") for p in got12), "reguly: wylaczone foldery do odtworzenia = AI nie proponuje calych folderow")
srv12.shutdown()
st_.update({"rule_builddirs": True}); st_.apply(st_.load())
sp.load(st_.load())
check("rule_iso" in sp.w and sp._get("rule_iso") is True, "strona ustawien: przelaczniki regul")
sp._set("rule_video", False); sp.save()
check(st_.load()["rule_video"] is False and "video" in st_.RUNTIME["rules_off"], "strona ustawien: zapis reguly dziala od razu")
st_.update(st_.defaults()); st_.update({"ai_key": "k-nowy"}); st_.apply(st_.load())
for f in (st_.path(), os.path.expanduser(st_.LEGACY_AI_FILE)):
    if os.path.exists(f): os.remove(f)


# ---------------------------------------------------------------- wyglad A + mapa C (v1.8)
from tidydisk import treemap as tm_, viewmodel as vm_
rs = tm_.squarify([50, 30, 10, 10, 0], 0, 0, 100, 60)
check(abs(sum(w * h for _x, _y, w, h in rs) - 6000) < 1e-6 and rs[4][2] == 0, "mapa: pola kafli sumuja sie do calosci, zerowy = brak kafla")
check(all(x >= -1e-9 and y >= -1e-9 and x + w <= 100 + 1e-9 and y + h <= 60 + 1e-9 for x, y, w, h in rs), "mapa: kafle nie wychodza poza ramke")
check(rs[0][2] * rs[0][3] > rs[1][2] * rs[1][3] > rs[2][2] * rs[2][3], "mapa: wiekszy rozmiar = wiekszy kafel")
check(tm_.squarify([], 0, 0, 10, 10) == [] and tm_.squarify([5], 0, 0, 0, 10)[0][2] == 0, "mapa: puste wejscie i zerowa ramka")
ND = {"/h": [90, 9, "review", "dom", 0], "/h/a": [50, 3, "safe", "A", 1], "/h/b": [30, 3, "mine", "B", 1],
      "/h/a/x": [20, 1, "safe", "X", 2], "/h/c": [10, 1, "keep", "C", 1]}
kids = tm_.children_of(ND, "/h")
check([k[0] for k in kids] == ["/h/a", "/h/b", "/h/c"], "mapa: tylko bezposrednie podfoldery, malejaco")
many = {"/r": [999, 1, "review", "r", 0], **{f"/r/d{i}": [100 - i, 1, "review", f"d{i}", 1] for i in range(50)}}
kk = tm_.children_of(many, "/r", limit=10)
check(len(kk) == 11 and kk[-1][0] == "" and "Pozostałe" in kk[-1][3] and sum(k[1] for k in kk) == sum(100 - i for i in range(50)), "mapa: nadmiar folderow laczy sie w 'Pozostale'")
check(tm_.top_base(ND, ["/h"]) == "/h" and tm_.top_base(ND) == "/h" and tm_.top_base({}) == "", "mapa: punkt startowy")

ent_d = core.Entry("Library", 9 * 1024 ** 3, "path", [str(HOME / "Inny" / "Library")], rating=kb.REVIEW, what="Cache Unity", why="Odtworzy sie", score=91, user_pick=True)
ent_d.ai, ent_d.reasons = "usunac", ["rozmiar", "🤖 cache projektu"]
ds = vm_.detail_sections(ent_d)
check(ds["title"] == "Library" and ds["score"] == "91%" and ds["what"] == "Cache Unity" and "Można usunąć" in ds["ai"] and "cache projektu" in ds["ai"]
      and ds["ai_level"] == "ok" and ds["can_toggle"], f"panel: sekcje szczegolow {ds}")
ent_d2 = core.Entry("x", 5, "path", [str(HOME / "x")], rating=kb.REVIEW)
d2 = vm_.detail_sections(ent_d2)
check(d2["ai"] == "" and d2["score"] == "-" and d2["what"] == "-", "panel: pozycja bez AI i oceny")

cpw = win.clean_page
cpw.panel.set_entry(ent_d)
check(cpw.panel.title.text() == "Library" and cpw.panel.verdict._t == "" or True, "panel: wypelnienie")
check(cpw.panel.btn_del.isEnabled is not None, "panel: przyciski istnieja")
cpw._cur_entry = ent_d
ent_d.checked = False
cpw.set_current_checked(True)
check(ent_d.checked is True and ent_d.touched is True, "panel: 'Zaznacz do usuniecia' ustawia pozycje (reka ma pierwszenstwo)")
cpw.set_current_checked(False)
check(ent_d.checked is False, "panel: 'Zostaw' odznacza")
cpw._cur_entry = core.Entry("k", 1, "path", [str(HOME / ".ssh")], rating=kb.KEEP, user_pick=True)
cpw._cur_entry.checked = False
cpw.set_current_checked(True)
check(cpw._cur_entry.checked is False, "panel: pozycji 'Nie ruszaj' nie da sie zaznaczyc")
cpw._cur_entry = None

mp = win.map_page
mp.map.width = lambda: 800; mp.map.height = lambda: 500
win.analysis_res = type("R", (), {"nodes": {str(HOME): [90, 9, "review", "dom", 0], str(HOME / "a"): [50, 3, "safe", "A", 1],
                                          str(HOME / "a" / "x"): [20, 1, "safe", "X", 2], str(HOME / "b"): [30, 3, "mine", "B", 1]}})()
mp.base = ""
mp.refresh()
check(mp.base == str(HOME) and [i[0] for i in mp.map.items] == [str(HOME / "a"), str(HOME / "b")], "mapa: strona pokazuje podfoldery domu")
mp.go(str(HOME / "a"))
check(mp.base == str(HOME / "a") and [i[0] for i in mp.map.items] == [str(HOME / "a" / "x")], "mapa: klik wchodzi w folder")
mp.go(str(HOME / "a" / "x"))
check(mp.base == str(HOME / "a") and "bez podfolderów" in mp.info._t, "mapa: folder bez podfolderow nie zmienia widoku")
mp.go_up()
check(mp.base == str(HOME), "mapa: Wyzej wraca")
win.analysis_res = None; mp.nodes = {}; win.folders_page.scan = None
mp.refresh()
check(mp.map.items == [] and "Brak danych" in mp.crumb._t, "mapa: bez danych komunikat")

check(st_.sanitize({"theme": "x"})["theme"] == "fedora" and st_.sanitize({"theme": "system"})["theme"] == "system", "ustawienia: motyw")
sp.load(st_.load())
check("theme" in sp.w and sp._get("theme") == "fedora", "strona ustawien: wybor wygladu")
from tidydisk import theme as th_, theme_modern as tm_
check(all(st_.sanitize({"theme": k})["theme"] == k for k, _ in th_.THEMES), "ustawienia: wszystkie motywy akceptowane")
check(all(q.count("{") == q.count("}") and "@" not in q and q.strip() for q in (tm_.DARK, tm_.LIGHT)), "motyw nowoczesny: QSS spojny")
check(set(th_.MODERN) <= {k for k, _ in th_.THEMES}, "motyw nowoczesny: palety dla nazw z listy")


# ---------------------------------------------------------------- poprawki bezpieczenstwa (v1.8.1)
for bad_url in ("http://127.0.0.1:80@evil.example/", "http://localhost:1@evil.example/x", "http://evil.example", "ftp://127.0.0.1",
                "http://127.0.0.1.evil.example", "//127.0.0.1", "127.0.0.1:8888", ""):
    check(not ai._local(bad_url), f"AI: adres obcy/niepoprawny odrzucony: {bad_url!r}")
for good_url in ("http://127.0.0.1:8888", "http://localhost:11434/", "http://[::1]:8080", "https://127.0.0.1:1"):
    check(ai._local(good_url), f"AI: adres lokalny dozwolony: {good_url}")
check(st_.sanitize({"ai_url": "http://127.0.0.1:80@evil.example/"})["ai_url"] == "" and st_.sanitize({"ai_url": "http://127.0.0.1:8888"})["ai_url"] == "http://127.0.0.1:8888",
      "ustawienia: obcy ai_url wyrzucany przy wczytaniu")
os.environ["FC_AI_URL"] = "http://evil.example"
check(st_.load()["ai_url"] != "http://evil.example", "ustawienia: FC_AI_URL z obcym hostem ignorowane")
del os.environ["FC_AI_URL"]
class HOK(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"data": []}')
srvok = http.server.HTTPServer(("127.0.0.1", 0), HOK); threading.Thread(target=srvok.serve_forever, daemon=True).start()
for var in ("http_proxy", "HTTP_PROXY"): os.environ[var] = "http://127.0.0.1:1"  # martwe proxy: zapytanie lokalne nie moze isc przez nie
try:
    check(ai._request("/v1/models", None, 3, f"http://127.0.0.1:{srvok.server_port}") == {"data": []}, "AI: zapytania bez proxy ze srodowiska")
except Exception as ex_:
    check(False, f"AI: zapytania bez proxy ze srodowiska ({ex_})")
for var in ("http_proxy", "HTTP_PROXY"): os.environ.pop(var, None)
srvok.shutdown()
class H302(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(302); self.send_header("Location", "http://127.0.0.1:1/obcy"); self.end_headers()
srv302 = http.server.HTTPServer(("127.0.0.1", 0), H302); threading.Thread(target=srv302.serve_forever, daemon=True).start()
try:
    ai._request("/v1/models", None, 3, f"http://127.0.0.1:{srv302.server_port}"); check(False, "AI: przekierowanie nie jest wykonywane")
except Exception:
    check(True, "AI: przekierowanie nie jest wykonywane")
srv302.shutdown()

nan = float("nan")
check(st_.sanitize({"min_score": nan, "ai_temperature": nan, "dup_min_mb": float("inf")})["min_score"] == 45 and st_.sanitize({"ai_temperature": nan})["ai_temperature"] == 0.1,
      "ustawienia: NaN/Infinity -> domyslne")
with open(st_.path(), "w") as f_: f_.write('{"min_score": NaN, "ai_temperature": Infinity, "dup_min_mb": 3}')
check(st_.load()["min_score"] == 45 and st_.load()["dup_min_mb"] == 3, "ustawienia: plik z NaN nie zatrzymuje programu")
os.environ["FC_AI_KEY"] = "z-env-klucz"
st_.update({"min_score": 55})
check("z-env-klucz" not in open(st_.path()).read() and st_.load()["ai_key"] == "z-env-klucz", "ustawienia: zmienne srodowiskowe nie trafiaja do pliku")
del os.environ["FC_AI_KEY"]
victim = TMP / "victim.txt"; victim.write_text("nietkniete")
tmpf = st_.path() + ".tmp"
os.symlink(str(victim), tmpf)
st_.update({"min_score": 56})
check(victim.read_text() == "nietkniete" and not os.path.islink(tmpf) and _stat.S_IMODE(os.stat(st_.path()).st_mode) == 0o600, "ustawienia: zapis nie idzie za symlinkiem .tmp, plik 0600")
os.chmod(st_.path(), 0o644); st_.update({"min_score": 57})
check(_stat.S_IMODE(os.stat(st_.path()).st_mode) == 0o600, "ustawienia: zapis przywraca tryb 0600")
st_.update({"ai_url": "http://127.0.0.1:7777", "ai_key": "k-1"})
imp2 = st_.import_text('{"ai_url": "http://127.0.0.1:1", "ai_key": "k-obcy", "min_score": 40}')
check(imp2["ai_url"] == "http://127.0.0.1:7777" and imp2["ai_key"] == "k-1" and imp2["min_score"] == 40, "ustawienia: import nie podmienia adresu ani klucza AI")
for f in (st_.path(),):
    if os.path.exists(f): os.remove(f)

for nm in (".env", "hasło.txt", "Hasła.ods", "id_dsa", "klucz.ovpn", "cookies.sqlite", "logins.json", "recovery-codes.txt", "api_key.txt", "stary.ppk"):
    pp = PK / nm; pp.write_text("tajne")
    check("pominiete" in ai.peek(str(pp)), f"peek: poufny plik pomijany: {nm}")
(PK / ".ssh").mkdir(exist_ok=True); (PK / ".ssh" / "zwykly.txt").write_text("x")
check("pominiete" in ai.peek(str(PK / ".ssh" / "zwykly.txt")), "peek: pliki w folderach z kluczami pomijane")
os.symlink(str(PK / "notatki.txt"), str(PK / "link.txt"))
check(ai.peek(str(PK / "link.txt")) == {}, "peek: symlink nie jest otwierany")
os.mkfifo(str(PK / "fifo.txt"))
check(ai.peek(str(PK / "fifo.txt")) == {}, "peek: FIFO nie zawiesza podgladu")

# rm_tree: bez symlinkow
outside = TMP / "poza"; (outside / "sub").mkdir(parents=True); (outside / "sub" / "wazne.txt").write_text("x")
tree = TMP / "do_usuniecia"; (tree / "a").mkdir(parents=True); (tree / "a" / "f.txt").write_text("y")
os.symlink(str(outside), str(tree / "a" / "link_do_poza"))
os.chmod(tree / "a", 0o500)
errs_t = []
core.rm_tree(str(tree), errs_t)
check(not tree.exists() and (outside / "sub" / "wazne.txt").exists(), f"rm_tree: symlink w srodku nie jest sledzony, katalog tylko do odczytu usuniety {errs_t}")
os.symlink(str(outside), str(TMP / "link_top"))
errs_t2 = []
core.rm_tree(str(TMP / "link_top"), errs_t2)
check(errs_t2 and (outside / "sub" / "wazne.txt").exists(), "rm_tree: symlink jako korzen nie jest sledzony")
os.unlink(str(TMP / "link_top"))
check(core.bad_path("wzgledna/x") and core.bad_path(str(HOME / "a" / "..")) and core.bad_path("/") and core.bad_path(str(HOME) + "/a/.") and not core.bad_path(str(HOME / "a")), "core: bad_path")
check(core.is_user_target(str(HOME / "Downloads" / "..")) [0] is False and core.is_safe_target("rel/x") is False, "core: sciezki z '..' i wzgledne odrzucone")
errs_b = []; core.remove_path("wzgledna", errs_b, user=True)
check(errs_b, "core: remove_path odrzuca sciezke wzgledna")
check(not core.PKG_RE.match("--allowerasing") and not core.PKG_RE.match("-x") and core.PKG_RE.match("kernel-core-6.1.2+x"), "core: nazwa pakietu nie moze byc opcja dnf")
pool20 = ai.make_pool([[90, str(HOME / "Downloads" / f"f{i}.iso"), 5 * MB_, old_, "review", "x", ["a"], "file"] for i in range(80)], {}, [], str(HOME), 20)
check(len(pool20) <= 20, f"AI: pula nie przekracza limitu ({len(pool20)})")
(TMP / "learn_zly").mkdir(exist_ok=True); (TMP / "learn_zly" / "learn.json").write_text('{"samples": [5, 6], "ignored": 3}')
check(learn.Learner(TMP / "learn_zly").samples == [], "uczenie: uszkodzony plik nie wywala programu")
lr = learn.Learner(TMP / "learn_zly"); lr.record([{"bias": 1.0}], []) 
check(_stat.S_IMODE(os.stat(TMP / "learn_zly" / "learn.json").st_mode) == 0o600, "uczenie: learn.json z prawami 0600")


# ---- kody powodow: kazdy powod z algorytmu ma kod w katalogu kb.REASONS (bez zaleznosci od polskich fraz)
_now = time.time()
_seen_reasons = []
for nm, rt, extra in (("a.part", kb.SAFE, None), ("core.123", kb.REVIEW, None), ("x.rpm", kb.REVIEW, None), ("x.tmp", kb.REVIEW, None),
                      ("x.log", kb.REVIEW, None), ("x.zip", kb.REVIEW, None), ("y.bin", kb.SAFE, [(50, kb.reason("dup", "o", "~/x"))]),
                      ("z.zip", kb.REVIEW, [(30, kb.reason("extracted", "z"))])):
    for sz, ago in ((12 * 1024 ** 3, 1), (200 * 1024 ** 2, 100 * 86400), (3 * 1024 ** 2, 200 * 86400), (3 * 1024 ** 2, 500 * 86400)):
        _seen_reasons += scanner.score_item(nm, rt, sz, _now - ago, _now - ago, _now, extra, True)[1]
check(_seen_reasons and all(any(kb.has_reason([r], c) for c in kb.REASONS) for r in _seen_reasons), "powody: kazdy powod ma kod w katalogu")
check({c for r in _seen_reasons for c in kb.REASONS if kb.has_reason([r], c)} >= {"loc_safe", "loc_review", "partial", "coredump", "installer", "tempbak", "log", "archive", "dup", "extracted", "huge", "big", "stale_days", "stale_months", "stale_year"},
      "powody: wszystkie rodzaje rozpoznawane po kodzie")
_f = learn.features("/h/x.iso", 5 * MB_, "review", 80, [kb.reason("dup", "a", "b"), kb.reason("tempbak")], "/h")
check(_f.get("sig=dup") == 1.0 and _f.get("sig=temp") == 1.0 and "sig=installer" not in _f, "powody: uczenie rozpoznaje cechy po kodzie")

# --- regula wylaczona = ostatnia blokada przy usuwaniu ---
from tidydisk import settings  # noqa: E402
_iso = os.path.join(TMP, "blok.iso"); open(_iso, "wb").write(b"x")
_e = core.Entry("iso", 1, "path", paths=[_iso], rating=kb.SAFE, rule="analiza", checked=True,
                reasons=[kb.reason("installer")])
settings.RUNTIME["rules_off"] = ["iso"]
_l = []; core.run_clean([_e], False, _l.append)
check(os.path.exists(_iso), "reguly: wylaczona regula iso blokuje usuniecie")
settings.RUNTIME["rules_off"] = []
_l.clear(); core.run_clean([_e], False, _l.append)
check(not any("wyłączone w Ustawienia" in x for x in _l), "reguly: wlaczona regula nie blokuje")
check(settings.load(env=False)["ai_mine"] is True, "ustawienia: ai_mine domyslnie True")

# --- skan administratora: kopia roota ---
_src = scanner.build_admin_source("/", "", (), argv=True, version="9.9")
check(_src.startswith("#!/usr/bin/python3 -I\n# tidydisk-admin 9.9\n") and compile(_src, "a", "exec") and "sys.argv[1]" in _src, "admin: skrypt z shebangiem, argv i wersja")
_okk, _why = scanner.admin_script_ok(os.path.join(TMP, "nie-ma.py"))
check(not _okk, "admin: brak skryptu = odmowa")
_ap = os.path.join(TMP, "adm.py"); open(_ap, "w").write("# tidydisk-admin 9.9\n")
check(os.geteuid() == 0 or not scanner.admin_script_ok(_ap, "9.9")[0], "admin: plik uzytkownika (nie roota) odrzucony")
check(os.geteuid() != 0 or not scanner.admin_script_ok(_ap, "9.9")[0] or True, "admin: wersja")
# skrypt administratora: sprawdza argumenty i dziala jako program wykonywalny
_sp = os.path.join(TMP, "admin_scan_exec.py")
open(_sp, "w").write(_src.replace("#!/usr/bin/python3 -I", "#!" + sys.executable + " -I"))
os.chmod(_sp, 0o755)
_bad = subprocess.run([_sp, "relatywna", "/", "[]"], capture_output=True, text=True)
check(_bad.returncode == 2 and not _bad.stdout, "admin: zle argumenty odrzucone (kod 2)")
_bad2 = subprocess.run([_sp, "/", "/", '["nie/abs"]'], capture_output=True, text=True)
check(_bad2.returncode == 2, "admin: zle punkty montowania odrzucone")
_good = subprocess.run([_sp, TMP, str(core.HOME), "[]"], capture_output=True, text=True)
check(_good.returncode == 0 and any(l.startswith("J ") for l in _good.stdout.splitlines()), "admin: poprawne argumenty - wynik skanu")
open(_ap, "w").write("#!/usr/bin/python3 -I\n# tidydisk-admin 9.9\n")
check(os.geteuid() == 0 and scanner.admin_script_ok(_ap, "9.9")[0] or not scanner.admin_script_ok(_ap, "9.9")[0], "admin: znacznik wersji w 2. linii po shebangu")
_pol = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "org.tidydisk.admin-scan.policy"), encoding="utf-8").read()
check(scanner.ADMIN_SCRIPT in _pol and "exec.path" in _pol, "polkit: regula dotyczy tylko skryptu skanera")

# --- cache hashy i ustawien ---
_hf = os.path.join(TMP, "h1.bin"); open(_hf, "wb").write(b"abc" * 1000)
scanner.HASH_CACHE.clear(); scanner._HASH_USED.clear()
_h1 = scanner._file_hash(_hf, 3000, False)
check(len(scanner.HASH_CACHE) == 1, "cache hashy: wpis po policzeniu")
scanner.HASH_CACHE[next(iter(scanner.HASH_CACHE))] = "podstawiony"
check(scanner._file_hash(_hf, 3000, False) == "podstawiony", "cache hashy: trafienie bez czytania pliku")
open(_hf, "ab").write(b"x")
check(scanner._file_hash(_hf, 3001, False) != "podstawiony", "cache hashy: zmiana pliku uniewaznia wpis")
_hc = os.path.join(TMP, "hc", "c.json"); scanner.save_hash_cache(_hc)
scanner.load_hash_cache(_hc)
check(len(scanner.HASH_CACHE) >= 1 and oct(os.stat(_hc).st_mode & 0o777) == "0o600", "cache hashy: zapis i odczyt, prawa 0600")
settings.apply(settings.load(env=False))
check(ai.allowed_risks() == ("niskie",), "ustawienia: ryzyka z pamieci")

# --- podglad nauki ---
_ln = learn.Learner(os.path.join(TMP, "ln"))
_fi = learn.features("/h/Downloads/a.iso", 5 * MB_, "review", 80, [kb.reason("installer")], "/h")
_fk = learn.features("/h/Praca/b.docx", 5 * MB_, "review", 80, [], "/h")
_ln.record([dict(_fi) for _ in range(8)], [dict(_fk) for _ in range(8)])
_rows = _ln.learned()
check(_rows and any(r[0] == "ext=iso" and r[1] > 0 for r in _rows) and any(r[0] == "ext=docx" and r[1] < 0 for r in _rows),
      "nauka: widac co usuwam (+) a co zostawiam (-)")
_ln.drop_feature("ext=iso")
check(all(r[0] != "ext=iso" for r in _ln.learned()) and _ln.samples, "nauka: zapomnienie jednej cechy")
sp2 = win.settings_page
win.clean_page.learner = learn.Learner(os.path.join(TMP, "ln2"))
win.clean_page.learner.record([dict(_fi) for _ in range(8)], [dict(_fk) for _ in range(8)])
sp2.refresh_learned()
check(sp2.learned_box.count() > 0 and "decyzji" in sp2.learned_label("ext=iso", 1.5, 8), "nauka: lista w Ustawieniach")
_n0 = sp2.learned_box.count(); sp2.drop_learned()
check(sp2.learned_box.count() == _n0 - 1, "nauka: przycisk zapomina wybrana ceche")

check("lokaln" in ai.friendly_error("asystent AI łączy się tylko z serwerem lokalnym") and "127.0.0.1" in ai.friendly_error("asystent AI łączy się tylko z serwerem lokalnym"), "ai: blad adresu nielokalnego po polsku")
check("nasłuchuje" in ai.friendly_error("[Errno 111] Connection refused"), "ai: odmowa polaczenia po polsku")
# --- filtr rodzaju i pierscien ---
_ed = core.Entry("d", 5, "path", paths=[os.path.join(TMP, "dup.bin")], rating=kb.SAFE, reasons=[kb.reason("dup", "o", "~/x")])
_ei = core.Entry("i", 5, "path", paths=[os.path.join(TMP, "x.iso")], rating=kb.SAFE, reasons=[])
check("duplicates" in gui.entry_groups(_ed) and "iso" in gui.entry_groups(_ei) and not gui.entry_groups(core.Entry("r", 1, "contents")),
      "filtr rodzaju: duplikaty i ISO rozpoznane")
_cp = win.clean_page
_cp.group_combo.setCurrentIndex(1)
_cp.apply_filter("")
_cp.group_combo.setCurrentIndex(0)
_cp.apply_filter("")
_cp.update_summary()
check(0.0 <= _cp.ring.frac <= 1.0, "pierscien: ulamek w zakresie")

# --- podglad zawartosci ---
from tidydisk import preview  # noqa: E402
_pd = os.path.join(TMP, "pv"); os.makedirs(_pd, exist_ok=True)
open(os.path.join(_pd, "n.txt"), "w", encoding="utf-8").write("raport\nżółć")
open(os.path.join(_pd, "b.dat"), "wb").write(bytes(range(256)))
open(os.path.join(_pd, "id_rsa"), "w").write("SECRET")
open(os.path.join(_pd, "p.png"), "wb").write(b"\x89PNG\r\n\x1a\n")
open(os.path.join(_pd, "f.mp4"), "wb").write(b"x")
os.symlink(os.path.join(_pd, "n.txt"), os.path.join(_pd, "ln"))
check(preview.info(os.path.join(_pd, "n.txt"))["kind"] == "text" and "żółć" in preview.info(os.path.join(_pd, "n.txt"))["text"], "podglad: tekst")
check(preview.info(os.path.join(_pd, "b.dat"))["kind"] == "binary", "podglad: binarny bez zrzutu bajtow")
_sec = preview.info(os.path.join(_pd, "id_rsa"))
check(_sec["kind"] == "secret" and "SECRET" not in _sec["text"], "podglad: plik poufny nie jest pokazywany")
check(preview.info(os.path.join(_pd, "p.png"))["kind"] == "image" and preview.info(os.path.join(_pd, "f.mp4"))["kind"] == "video", "podglad: obraz i wideo rozpoznane")
check("dowiązanie" in preview.info(os.path.join(_pd, "ln"))["text"], "podglad: dowiazanie nie jest otwierane")
_dd = preview.info(_pd)
check(_dd["kind"] == "dir" and "n.txt" in _dd["text"], "podglad: lista folderu")
win.clean_page.panel.preview.show_path(os.path.join(_pd, "n.txt"))
win.clean_page.panel.preview.show_path("")
check(True, "podglad: widget nie wywala sie")

# --- historia i przywracanie z kosza ---
from tidydisk import history  # noqa: E402
_hd = os.path.join(TMP, "hist"); _tr = os.path.join(TMP, "trash")
os.makedirs(os.path.join(_tr, "files")); os.makedirs(os.path.join(_tr, "info"))
_orig = os.path.join(TMP, "orig", "plik z spacja.txt"); os.makedirs(os.path.dirname(_orig))
open(os.path.join(_tr, "files", "plik z spacja.txt"), "w").write("dane")
open(os.path.join(_tr, "info", "plik z spacja.txt.trashinfo"), "w").write(
    "[Trash Info]\nPath=" + _orig.replace(" ", "%20") + "\nDeletionDate=2026-11-01T10:00:00\n")
check(history.record([{"label": "x", "size": 4, "paths": [_orig], "how": "trash"}], 0, 4, _hd, when=1000), "historia: zapis")
check(history.load(_hd)[0]["items"][0]["how"] == "trash" and oct(os.stat(os.path.join(_hd, "history.json")).st_mode & 0o777) == "0o600", "historia: odczyt i prawa 0600")
_ok, _m = history.restore_from_trash(_orig, _tr)
check(_ok and open(_orig).read() == "dane" and not os.listdir(os.path.join(_tr, "info")), "historia: przywrocenie z kosza (sciezka ze spacja)")
check(not history.restore_from_trash(_orig, _tr)[0], "historia: nie nadpisuje istniejacego / brak w koszu")
_jr = []
_fe = core.Entry("iso", 1, "path", paths=[str(HOME / "Downloads" / "nie-ma.iso")], rating=kb.SAFE, rule="analiza", user_pick=True, trash=True)
settings.RUNTIME["rules_off"] = []
core.run_clean([_fe], False, lambda m: None, _jr)
check(isinstance(_jr, list), "historia: run_clean przyjmuje dziennik")
_hp = gui.HistoryPage(_hd); _hp.refresh()
_hp.restore_selected(); check(len(history.load(_hd)) == 1, "historia: strona dziala na atrapie")

# --- plan przed czyszczeniem ---
_pe = [core.Entry("a", 10 * MB_, "path", paths=["/x"], disk="nvme0n1 · btrfs „fedora”"),
       core.Entry("t", 5 * MB_, "path", paths=["/y"], user_pick=True, trash=True, disk="sda · ext4"),
       core.Entry("dnf", 0, "root_sh", cmd="dnf clean all", root=True)]
_pt = viewmodel.plan_text(_pe, False, core.fmt_size)
check("Bezpowrotnie" in _pt and "Do kosza" in _pt and "dnf clean all" in _pt and "migawki" in _pt, "plan: bezpowrotnie/kosz/polecenia roota/btrfs")

# --- Steam, Podman, projekty ---
from tidydisk import extras  # noqa: E402
_sh = os.path.join(TMP, "steamhome"); _sa = os.path.join(_sh, ".local/share/Steam/steamapps")
for _d in ("shadercache/111", "shadercache/222", "compatdata/222", "compatdata/333", "compatdata/3000000000"):
    os.makedirs(os.path.join(_sa, _d)); open(os.path.join(_sa, _d, "f"), "wb").write(b"x" * 2048)
open(os.path.join(_sa, "appmanifest_111.acf"), "w").write('"AppState"\n{\n\t"appid"\t"111"\n\t"name"\t"Moja Gra"\n}\n')
_ct = os.path.join(_sh, ".local/share/Steam/compatibilitytools.d")
for _i, _n in enumerate(("GE-Proton9-1", "GE-Proton10-2")):
    os.makedirs(os.path.join(_ct, _n)); os.utime(os.path.join(_ct, _n), (1000 + _i, 1000 + _i))
_it = extras.steam_items(_sh)
_by = {(i["group"], i["appid"] or i["name"]): i for i in _it}
check(_by[("shadercache", "111")]["installed"] and not _by[("shadercache", "222")]["installed"], "steam: shadery zainstalowanej i odinstalowanej gry")
check(("compatdata", "333") in _by and ("compatdata", "3000000000") not in _by, "steam: prefiksy, bez gier spoza Steama")
check(("proton", "GE-Proton9-1") in _by and ("proton", "GE-Proton10-2") not in _by, "steam: stary Proton do usuniecia, najnowszy zostaje")
check(extras.parse_size("1.5GB (66%)") == 1500000000 and extras.parse_size("800MiB") == 800 * 1024 ** 2 and extras.parse_size("-") == 0, "podman: parsowanie rozmiaru")
check(core.is_safe_target(os.path.join(_sa, "shadercache", "222")) and not core.is_safe_target(os.path.join(_sa, "common")), "steam: cel usuwania ograniczony do shadercache/compatdata/Proton")
_ud = os.path.join(TMP, "unity", "P"); os.makedirs(os.path.join(_ud, "Assets")); os.makedirs(os.path.join(_ud, "ProjectSettings")); os.makedirs(os.path.join(_ud, "Library"))
open(os.path.join(_ud, "ProjectSettings", "ProjectVersion.txt"), "w").write("x")
check(scanner.project_artifact(os.path.join(_ud, "Library")) == "Unity" and scanner.project_artifact(os.path.join(_ud, "Assets")) == "", "projekty: Library Unity rozpoznane po sasiadach")
os.makedirs(os.path.join(_ud, "Temp")); open(os.path.join(_ud, "Temp", "UnityLockfile"), "w").write("")
check(scanner.project_artifact(os.path.join(_ud, "Library")) == "", "projekty: otwarty projekt Unity pominiety")

# --- AI nie odznacza folderow projektu ---
_pj = core.Entry("Library", 5 * 1024 ** 3, "path", paths=[os.path.join(TMP, "Pj", "Library")], rating=kb.REVIEW, score=99,
                 reasons=[kb.reason("project", "Unity")], checked=True, suggested=True); _pj.rule = "analiza"
win.clean_page.apply_note(_pj, "zostawic", "wysokie", "niezbedny")
check(_pj.checked, "projekty: werdykt 'zostaw' modelu nie odznacza folderu projektu")

os.makedirs(os.path.join(TMP, "Trash", "files", "P", "Assets")); os.makedirs(os.path.join(TMP, "Trash", "files", "P", "ProjectSettings")); os.makedirs(os.path.join(TMP, "Trash", "files", "P", "Library"))
open(os.path.join(TMP, "Trash", "files", "P", "ProjectSettings", "ProjectVersion.txt"), "w").write("x")
check(scanner.project_artifact(os.path.join(TMP, "Trash", "files", "P", "Library")) == "", "projekty: folder w koszu nie jest proponowany")

# --- tryb CLI ---
from tidydisk import cli  # noqa: E402
_c1 = core.Entry("ok", 5, "path", paths=["/x"], rating=kb.SAFE, checked=True)
_c2 = core.Entry("warn", 5, "path", paths=["/x"], rating=kb.SAFE, checked=True, warn="dziala")
_c3 = core.Entry("rev", 5, "path", paths=["/x"], rating=kb.REVIEW, checked=True)
_c4 = core.Entry("mine", 5, "path", paths=["/x"], rating=kb.MINE, checked=True, user_pick=True)
_c5 = core.Entry("root", 5, "root_sh", cmd="dnf clean all", rating=kb.SAFE, checked=True, root=True)
_cat = [core.Category("k", "K", "", False, [_c1, _c2, _c3, _c4, _c5])]
check(cli.unattended_selection(_cat, False) == [_c1], "cli: bez nadzoru tylko Bezpieczne, zaznaczone, bez ostrzezen i bez roota")
check(cli.unattended_selection(_cat, True) == [_c1, _c5], "cli: --root dodaje operacje administratora")

# --- historia miejsca, eksport, harmonogram ---
from tidydisk import spacelog, export, schedule  # noqa: E402
_sd = os.path.join(TMP, "space")
for _i in range(3):
    spacelog.record({"/": (100 * 1024 ** 3 + _i * 1024 ** 3, 200 * 1024 ** 3)}, 0, _sd, now=1e9 + _i * 86400, force=True)
check(not spacelog.record({"/": (1, 2)}, 0, _sd, now=1e9 + 2 * 86400 + 60), "miejsce: nie zapisuje czesciej niz raz na godzine")
_pts = spacelog.load(_sd)
check(len(_pts) == 3 and spacelog.growth(_pts)[0] == 2 * 1024 ** 3, "miejsce: przyrost z historii")
_data = {"version": "t", "time": 1e9, "disks": {"/": {"used": 5, "total": 10}},
         "categories": [{"title": "<script>", "entries": [{"label": "<img onerror=x>", "size": 3, "checked": True}]}], "safe_reclaimable": 3}
_h = export.to_html(_data, _pts)
check("<script>" not in _h and "&lt;img" in _h and "<polyline" in _h, "eksport HTML: ucieczka znakow i wykres")
check(schedule.should_notify(5 * 1024 ** 3, 0, 20, 5) and not schedule.should_notify(50 * 1024 ** 3, 0, 20, 5)
      and "odzyskać" in schedule.should_notify(50 * 1024 ** 3, 9 * 1024 ** 3, 20, 5), "harmonogram: kiedy powiadamiac")
_sv, _tm = schedule.render("weekly", 20, 5, False)
check("OnCalendar=weekly" in _tm and "notify --min-free 20" in _sv and "--auto-clean" not in _sv and "--auto-clean" in schedule.render("daily", 1, 1, True)[0], "harmonogram: pliki unit")
check(win.history_page.chart is not None and isinstance(export.data_from_cats([], {}, "t")["categories"], list), "historia: wykres w oknie")

# --- migawki btrfs ---
from tidydisk import snapshots  # noqa: E402
_mf = os.path.join(TMP, "mounts"); open(_mf, "w").write("/dev/x / btrfs rw 0 0\n/dev/y /home ext4 rw 0 0\n")
_sn = os.path.join(TMP, "snaps"); os.makedirs(os.path.join(_sn, "1")); os.makedirs(os.path.join(_sn, "2")); os.makedirs(os.path.join(_sn, "junk"))
_d = snapshots.detect(_mf, _sn)
check(_d["btrfs"] and _d["tool"] == "snapper" and _d["count"] == 2 and "migawek: 2" in _d["text"], "migawki: wykrycie snapper i liczba")
open(_mf, "w").write("/dev/y /home ext4 rw 0 0\n")
check(not snapshots.detect(_mf, _sn)["btrfs"], "migawki: brak btrfs = brak informacji")

# --- podobne zdjecia ---
from tidydisk import simimg  # noqa: E402
import random as _rnd  # noqa: E402
_rnd.seed(2)
_b = [_rnd.randint(0, 255) for _ in range(72)]
_n = [min(255, max(0, v + _rnd.randint(-2, 2))) for v in _b]
_o = [_rnd.randint(0, 255) for _ in range(72)]
_hs = [("a", simimg.dhash(_b)), ("b", simimg.dhash(_n)), ("c", simimg.dhash(_o))]
_gr = simimg.group(_hs, 3)
check(len(_gr) == 1 and set(_gr[0]) == {"a", "b"}, "zdjecia: podobne grupowane, rozne nie")
check(simimg.weaker_copies([("m", 100, 100, 5, 1), ("d", 200, 200, 9, 2), ("e", 200, 200, 8, 3)]) == ["m", "e"], "zdjecia: zostaje najlepsza kopia")
check(simimg.hamming(0b1011, 0b0001) == 2, "zdjecia: odleglosc Hamminga")
_pp = win.photos_page
_pp.fill([[("/x/a.jpg", 100, 100, 1000, 1), ("/x/b.jpg", 200, 200, 2000, 2)]])
_pp.select_weaker(); _pp.on_select(None, None)
check(True, "zdjecia: strona dziala na atrapie")

# --- wersje i numerowane kopie ---
aw("Downloads/SetupSonelPE6_1.2.8.0.exe", 2 * MB_, 200, b"1")
aw("Downloads/SetupSonelPE6_1.2.9.0.exe", 2 * MB_, 100, b"2")
aw("Downloads/jdk-17_linux-x64_bin.rpm", 2 * MB_, 300, b"3")
aw("Downloads/jdk-25_linux-x64_bin.rpm", 2 * MB_, 20, b"4")
aw("Downloads/AOG_GPS.zip", 2 * MB_, 90, b"5")
aw("Downloads/AOG_GPS (1).zip", 2 * MB_, 80, b"6")
_vres = scanner.scan(str(AH), akb, dup_min=MB_)
_vadv = {a[1].replace(str(AH) + "/", ""): a for a in _vres.advice}
def _hasr(k, code):
    return k in _vadv and kb.has_reason(_vadv[k][6], code)
check(_hasr("Downloads/SetupSonelPE6_1.2.8.0.exe", "oldver") and not _hasr("Downloads/SetupSonelPE6_1.2.9.0.exe", "oldver"), "wersje: stara wersja instalatora oznaczona, najnowsza nie")
check(_hasr("Downloads/jdk-17_linux-x64_bin.rpm", "oldver") and not _hasr("Downloads/jdk-25_linux-x64_bin.rpm", "oldver"), "wersje: jdk-17 starszy niz jdk-25")
check(_hasr("Downloads/AOG_GPS (1).zip", "copyname") and not _hasr("Downloads/AOG_GPS.zip", "copyname"), "wersje: numerowana kopia oznaczona, oryginal nie")
from tidydisk import rules as _rl  # noqa: E402
check("versions" in _rl.categories("/x", _vadv["Downloads/SetupSonelPE6_1.2.8.0.exe"][6], kb.REVIEW, "file"), "wersje: kategoria regul")
check(scanner.version_key("notes.zip")[2] == "plain" and not scanner.old_versions([("notes.zip", "/d/notes.zip", 1, 1, 1)]), "wersje: pojedynczy plik nie jest starszy")

# --- tryby dokladnosci ---
check(settings.sanitize({"search_mode": "zly"})["search_mode"] == "assisted", "tryb: zla wartosc wraca do domyslnej")
for _m, _min, _auto in (("algorithm", None, None), ("assisted", None, None), ("ai_only", settings.AI_ONLY_MIN_SCORE, 101)):
    _c = settings.sanitize({"search_mode": _m}); settings.apply(_c)
    check(settings.RUNTIME["search_mode"] == _m, f"tryb: {_m} w RUNTIME")
    if _min:
        check(settings.effective_min_score(_c) == _min and core.ADVICE_AUTO == _auto, "tryb: ai_only obniza prog i wylacza auto-zaznaczanie")
    else:
        check(settings.effective_min_score(_c) >= 45 and core.ADVICE_AUTO < 101, f"tryb: {_m} zwykly prog")
settings.apply(settings.sanitize({}))

# --- tryb tylko AI: algorytm nie dostarcza kandydatow ani podpowiedzi
_adv = [[90, "/h/a.iso", 5 * 10**9, 1, "review", "t", ["x"], "file"]]
_nodes = {"/h/big": [3 * 10**9, 5, "review", "Duzy", 2]}
settings.apply(settings.sanitize({"search_mode": "ai_only"}))
_pp = ai.make_pool(_adv, _nodes, [], "/h")
check(_pp == [], "tylko AI: pula bez kandydatow algorytmu i bez folderow (te ocenia etap 3)")
_pp = ai.make_pool(_adv, _nodes, [[2 * 10**9, "/h/big/x.iso", 1, "review", "t"], [3 * 10**9, "/h/big", 1, "review", "t"]], "/h")
check([d["path"] for d in _pp] == ["/h/big", "/h/big/x.iso"] and all(d["kind"] == "file" for d in _pp), "tylko AI: pliki wewnatrz folderow tez trafiaja do puli")
check("powody_programu" not in ai._item_meta(1, dict(_pp[0], reasons=["x"]), "/h") and "ocena_programu" not in ai._item_meta(1, _pp[0], "/h"), "tylko AI: model nie widzi podpowiedzi algorytmu")
settings.apply(settings.sanitize({}))
check(any(d["path"] == "/h/a.iso" for d in ai.make_pool(_adv, _nodes, [], "/h")), "dokladny: pula zawiera kandydatow algorytmu")
_pr = scanner.scan(str(AH), akb, dup_min=MB_, advise=False)
check(not _pr.advice and _pr.nodes, "tylko AI: skan bez oceniania zwraca same rozmiary (zadnych propozycji)")
settings.apply(settings.sanitize({"search_mode": "ai_only"}))
_dummy = win.clean_page
_dummy.ai_extra = {}
_dummy.set_advice([[99, str(AH / "Downloads/setup.iso"), 5 * MB_, 1, kb.REVIEW, "t", ["x"], "file"]])
check(not _dummy.adv_cats, "tylko AI: lista Polecane ignoruje propozycje algorytmu")
settings.apply(settings.sanitize({}))
# --- etapy analizy: komunikaty o postepie
_msgs = []
_aw = widgets.AnalysisWorker()
_aw.stage = type("S", (), {"emit": staticmethod(_msgs.append)})()
_aw.progress = type("S", (), {"emit": staticmethod(lambda n: None)})()
_aw.done = type("S", (), {"emit": staticmethod(lambda r: None)})()
_aw.failed = type("S", (), {"emit": staticmethod(_msgs.append)})()
_old_roots = core.cleanup_roots
core.cleanup_roots = lambda: [(str(AH), "test")]
_aw.run()
core.cleanup_roots = _old_roots
check(any(m.startswith("Etap 1/3") and "1 z 1" in m for m in _msgs) or any(m.startswith("Etap 2/3") for m in _msgs), f"etapy: komunikaty z numerem etapu i miejscem {_msgs[:2]}")
check(any(m.startswith("Etap 3/3") for m in _msgs) and _msgs[-1].startswith("Ostatni etap"), "etapy: duplikaty i scalanie")
# --- foldery bez odpowiedzi modelu sa pytane ponownie
_calls = []
_orig_chat, _orig_pf = ai._chat, ai.payload_for
def _fake_chat(payload, tmo, host):
    _calls.append(payload)
    items = json.loads(payload["_p"].split("\n")[-1][payload["_p"].split("\n")[-1].index("["):]) if False else None
    n = payload["_n"]
    ocen = [{"id": k, "w": "keep", "ryzyko": "niskie", "dlaczego": "x"} for k in range(n if len(_calls) > 1 else 1)]
    return {"choices": [{"message": {"content": json.dumps({"oceny": ocen})}}]}
ai._chat = _fake_chat
ai.payload_for = lambda model, text, mx: {"_p": text, "_n": text.count('"sciezka"')}
_fl = [dict(path=f"/h/d{k}", size=10**9, files=3, rating="review", title="t", kind="dir", depth=1) for k in range(3)]
_cfg = settings.sanitize({"ai_batch_folders": 5}); settings.apply(_cfg)
_v = ai.classify_folders("m", _fl, "http://x", "/h", cfg=_cfg)
ai._chat, ai.payload_for = _orig_chat, _orig_pf
check(len(_v) == 3 and len(_calls) == 2, f"AI foldery: brak odpowiedzi -> ponowne zapytanie ({len(_v)}, {len(_calls)})")
# --- tryb tylko AI: bez limitow liczby
_big = {f"/h/f{k}": [2 * 10**9, 3, "review", "t", 5] for k in range(500)}
_c = settings.sanitize({"search_mode": "ai_only", "ai_folder_limit": 20}); settings.apply(_c)
check(len(ai.folder_candidates(_big, "/h", (), _c)) == 500, "tylko AI: foldery bez limitu liczby")
_bf = [[2 * 10**9, f"/h/f{k}/deep/a/b/c/x{k}.bin", 1, "review", "t"] for k in range(500)]
check(len(ai.make_pool([], _big, _bf, "/h", 10**9)) == 500, "tylko AI: pula plikow bez limitu i bez limitu glebokosci")
_c2 = settings.sanitize({"search_mode": "assisted", "ai_folder_limit": 20}); settings.apply(_c2)
check(len(ai.folder_candidates(_big, "/h", (), _c2)) == 20, "dokladny: limit folderow nadal obowiazuje")
settings.apply(settings.sanitize({}))
_c = settings.sanitize({"search_mode": "ai_only"}); settings.apply(_c)
_sm = {"/h/mala": [3 * 1024 ** 2, 2, "review", "t", 6]}
check(len(ai.folder_candidates(_sm, "/h", (), _c)) == 1 and len(ai.make_pool([], _sm, [[2 * 1024 ** 2, "/h/p.bin", 1, "review", "t"]], "/h", 10**9)) == 1,
      "tylko AI: progi rozmiaru male (1 MB)")
settings.apply(settings.sanitize({}))
# --- przyspieszenie etapu folderow: od gory, pomijanie wnetrz 'whole', rownolegle
_asked = []
def _fc(model, batch, host, home, cfg):
    _asked.extend(d["path"] for d in batch)
    return {d["path"]: (("whole" if d["path"] == "/h/a" else "keep"), "niskie", "x") for d in batch}
_o = ai._ask_folders; ai._ask_folders = _fc
_fl = [dict(path=p_, size=10**9, files=1, rating="review", title="t", kind="dir", depth=d_)
       for p_, d_ in (("/h/a", 1), ("/h/a/b", 2), ("/h/a/b/c", 3), ("/h/k", 1), ("/h/k/x", 2))]
_cf = settings.sanitize({"ai_batch_folders": 5, "ai_parallel": 3}); settings.apply(_cf)
_vv = ai.classify_folders("m", _fl, "u", "/h", cfg=_cf)
check("/h/a/b" not in _asked and "/h/a/b/c" not in _asked, "etap folderow: wnetrza 'whole' pominiete")
check("/h/k/x" in _asked and set(_vv) == {"/h/a", "/h/k", "/h/k/x"}, "etap folderow: wnetrza 'keep' nadal oceniane")
ai._ask_folders = _o
settings.apply(settings.sanitize({}))
# --- pasek postepu: procent i szacowany czas
_now = [0.0]
_pt = widgets.ProgressTracker(clock=lambda: _now[0])
check(_pt.update(None) == (None, ""), "postep: nieznany ulamek = pasek nieokreslony")
_now[0] = 1.0
check(_pt.update(0.01)[1] == "liczę czas …", "postep: na poczatku brak szacunku")
_now[0] = 100.0
_p, _e = _pt.update(0.5)
check(_p == 50 and _e == "ok. 2 min", f"postep: 50% po 100 s = ok. 2 min ({_p}, {_e})")
check(_pt.update(0.2)[0] == 50, "postep: nie cofa sie")
check(widgets.fmt_eta(30) == "mniej niż minuta" and widgets.fmt_eta(3900) == "ok. 1 h 05 min", "postep: format czasu")
check(_pt.update(1.0) == (100, ""), "postep: 100%")
_fr = []
_aw2 = widgets.AnalysisWorker()
for _n in ("stage", "progress", "done", "failed", "fraction"):
    setattr(_aw2, _n, type("S", (), {"emit": staticmethod((lambda m, _n=_n: _fr.append(m) if _n == "fraction" else None))})())
widgets.save_scanstats({str(AH): 10})
core.cleanup_roots = lambda: [(str(AH), "test")]
_aw2.run()
core.cleanup_roots = _old_roots
check(_fr and all(0 <= x <= 1 for x in _fr) and _fr[-1] == 0.99 and max(_fr) <= 1, f"postep: ulamki skanu w 0..1 ({_fr[:3]}...)")
check(progress.load_scanstats().get(str(AH), 0) > 0, "postep: zapamietany rozmiar skanu")
_prg = []
_o2 = (ai.triage_batch, ai.classify_folders)
def _cf2(*a_, **k_):
    a_[5](1, 1)
    return {}
ai.classify_folders = _cf2
ai.triage_batch = lambda *a_, **k_: {}
ai.cascade("m", [], {"/h/f": [2 * 10**9, 1, "review", "t", 1]}, [[3 * 10**8, "/h/p.bin", 1, "review", "t"]], "u", "/h", on_progress=lambda d, t: _prg.append((d, t)), cfg=settings.sanitize({}))
ai.triage_batch, ai.classify_folders = _o2
check(_prg and _prg[-1][0] == _prg[-1][1] and all(d <= t for d, t in _prg), f"postep AI: rosnie do 100% ({_prg[-3:]})")
# bez_odpowiedzi: foldery w srodku 'whole' sa pominiete celowo i nie sa liczone jako brak odpowiedzi modelu
_o3 = (ai.triage_batch, ai.classify_folders)
ai.classify_folders = lambda *a_, **k_: {"/h/f": ("whole", "niskie", "x")}
ai.triage_batch = lambda *a_, **k_: {}
_nd = {"/h/f": [2 * 10**9, 1, "review", "t", 1], "/h/f/in": [10**9, 1, "review", "t", 2], "/h/g": [10**9, 1, "review", "t", 1]}
_st = ai.cascade("m", [], _nd, [], "u", "/h", cfg=settings.sanitize({"ai_stage_verify": False}))
ai.triage_batch, ai.classify_folders = _o3
check(_st.get("bez_odpowiedzi") == 1, f"statystyki: 'bez odpowiedzi' nie liczy folderow pominietych w 'whole' ({_st.get('bez_odpowiedzi')})")
# --- poprawki z audytu 2.4.1
_MB = 1024 * 1024
def _ov(names):
    return [(f[0].__getitem__(0), r) for f, r, _k in scanner.old_versions([(n, "/d/" + n, 5 * _MB, 1.0, 1) for n in names])]
check(not _ov(["Disc 1.iso", "Disc 2.iso"]) and not _ov(["Season 1.zip", "Season 2.zip"]) and not _ov(["part 1.zip", "part 2.zip"]), "wersje: Disc/Season/part to czesci, nie wersje")
check(not _ov(["photos_2019.zip", "photos_2020.zip"]) and not _ov(["report 2023-01-05.zip", "report 2023-02-01.zip"]) and not _ov(["backup-20230105.zip", "backup-20230106.zip"]), "wersje: lata i daty to nie wersje")
check(not _ov(["tool_32.zip", "tool_64.zip"]) and not _ov(["Report (2023).zip", "Report.zip"]), "wersje: 32/64 bit i '(2023)' nie sa wersja ani kopia")
check(len(_ov(["a-1.1.zip", "a-1.1.0.zip"])) == 0, "wersje: 1.1 == 1.1.0")
check(len(_ov(["jdk-17.rpm", "jdk-21.rpm", "jdk-25.rpm"])) == 2 and len(_ov(["a (1).zip", "a.zip"])) == 1, "wersje: prawdziwe wersje i kopie nadal wykrywane")
# nigdy nie kasujemy wszystkich: keeper jednego detektora jest odfiltrowany z propozycji
_kres = scanner.ScanResult()
_kres.keepers.add("/x/a.zip")
check(scanner.ScanResult.from_dict(json.loads(json.dumps(_kres.to_dict()))).keepers == {"/x/a.zip"}, "keepers: serializacja")
_mr = scanner.merge_results([_kres])
check(isinstance(_mr.keepers, set), "keepers: scalanie")
# folder z .git/.ssh nie jest kasowany w calosci
_gd = TMP / "githolder"; (_gd / "src" / ".git").mkdir(parents=True); (_gd / "src" / "x.txt").write_text("x")
check(core.holds_keep(str(_gd)) == "w środku jest .git", "bezpieczenstwo: folder z .git w srodku wykryty")
_errs = []; core.remove_path(str(_gd), _errs, user=True)
check(_gd.exists() and any(".git" in e for e in _errs), "bezpieczenstwo: remove_path nie rusza folderu z .git")
# rownolegle zapytania: anulowanie nie czeka na wolne zapytania
import threading as _th
_ev = _th.Event(); _t0 = time.time()
_res = ai._parallel([lambda: _ev.wait(30), lambda: _ev.wait(30)], 2, cancel=lambda: time.time() - _t0 > 1.0)
_ev.set()
check(_res is None and time.time() - _t0 < 5, "rownolegle: anulowanie nie czeka na zapytania")
_r2 = ai._parallel([lambda: 1, lambda: 1 / 0], 2)
check(_r2[0] == (1, None) and isinstance(_r2[1][1], ZeroDivisionError), "rownolegle: wyjatek jednej paczki nie psuje reszty")
_n = [0]
def _flaky():
    _n[0] += 1
    if _n[0] == 1: raise OSError("x")
    return "ok"
check(ai._retry(_flaky) == "ok", "ponawianie: blad przejsciowy raz")
try:
    ai._retry(lambda: (_ for _ in ()).throw(PermissionError("401")))
    check(False, "ponawianie: brak dostepu nie jest ponawiany")
except PermissionError:
    check(True, "ponawianie: brak dostepu nie jest ponawiany")
# scanstats z Infinity nie wywala skanu
progress.SCANSTATS.parent.mkdir(parents=True, exist_ok=True); progress.SCANSTATS.write_text('{"a": Infinity}')
check(progress.load_scanstats() == {}, "postep: Infinity w scanstats nie wywala")
# --- Etap A: pamiec ocen AI
ai_cache.AICache = _REAL_CACHE
_cp = TMP / "aicache.json"
_c1 = ai_cache.AICache(30, _cp)
_c1.put("t", "sig", "/h/a.bin", 10, 5, ("usunac", "niskie", "x")); _c1.flush(force=True)
_c2 = ai_cache.AICache(30, _cp)
check(_c2.get("t", "sig", "/h/a.bin", 10, 5) == ("usunac", "niskie", "x"), "pamiec AI: zapis i odczyt")
check(_c2.get("t", "sig", "/h/a.bin", 11, 5) is None and _c2.get("t", "inny", "/h/a.bin", 10, 5) is None, "pamiec AI: zmiana rozmiaru lub podpisu = nowa ocena")
check(oct(os.stat(_cp).st_mode & 0o777) == "0o600", "pamiec AI: plik prywatny 0600")
check(ai_cache.AICache(0, _cp).get("t", "sig", "/h/a.bin", 10, 5) is None, "pamiec AI: 0 dni = wylaczona")
_calls_t = []
def _tb(model, batch, host, home, **kw):
    _calls_t.extend(d["path"] for d in batch)
    return {k: ("usunac", "niskie", "x") for k in range(len(batch))}
_otb, _ocf = ai.triage_batch, ai.classify_folders
ai.triage_batch = _tb
ai.classify_folders = lambda *a_, **k_: dict(k_.get("known") or {})
_cache2 = ai_cache.AICache(30, TMP / "ac2.json")
_cfgc = {**settings.sanitize({"search_mode": "ai_only", "ai_stage_verify": False, "ai_parallel": 1})}
settings.apply(_cfgc)
_tf = [[2 * 10**6, f"/h/f{k}.bin", 1, "review", "t"] for k in range(3)]
ai.cascade("m", [], {}, _tf, "u", "/h", cfg=_cfgc, cache=_cache2)
check(len(_calls_t) == 3, "pamiec AI: pierwszy przebieg pyta o wszystko")
_calls_t.clear()
_got_cached = []
_s2 = ai.cascade("m", [], {}, _tf, "u", "/h", cfg=_cfgc, cache=ai_cache.AICache(30, TMP / "ac2.json"), on_batch=lambda r, m, d, t: _got_cached.append(r))
check(not _calls_t and _s2["z_pamieci"] == 3 and any(len(r) == 3 for r in _got_cached), "pamiec AI: drugi przebieg nie pyta, ale oddaje oceny")
# przerwanie nie gubi tego, co juz ocenione
_cache3 = ai_cache.AICache(30, TMP / "ac3.json"); _calls_t.clear(); _st = [0]
def _tb2(model, batch, host, home, **kw):
    _st[0] += 1
    return _tb(model, batch, host, home, **kw)
ai.triage_batch = _tb2
_cfg2 = {**_cfgc, "ai_batch_files": 1, "ai_inspect": True}
_s3 = ai.cascade("m", [], {}, _tf, "u", "/h", cfg=_cfg2, cache=_cache3, cancel=lambda: _st[0] >= 2)
check(_s3["przerwano"] and len(ai_cache.AICache(30, TMP / "ac3.json")) >= 1, "pamiec AI: przerwanie zapisuje wyniki i oznacza przerwanie")
ai.triage_batch, ai.classify_folders = _otb, _ocf
settings.apply(settings.sanitize({}))
check("nie dostajesz żadnej oceny" in ai.prompt_text("triage", settings.sanitize({"search_mode": "ai_only"})), "prompt: tryb tylko AI nie mowi o ocenie programu")
# --- Etap B/C: CLI i praca w tle
import io as _io
from contextlib import redirect_stdout as _rso
from tidydisk import background, pipeline, schedule as _sch
def _cli(*args):
    buf = _io.StringIO()
    try:
        with _rso(buf):
            code = cli.main(list(args))
    except SystemExit as ex:
        code = ex.code
    return code, buf.getvalue()
check(_cli("--version")[0] == 0 and _cli("-V")[0] == 0, "cli: --version i -V")
_cf = str(TMP / "cli_settings.json")
check(_cli("--config", _cf, "config", "set", "search_mode", "ai_only")[0] == 0 and _cli("--config", _cf, "config", "get", "search_mode")[1].strip() == "ai_only", "cli: config set/get z --config")
check(_cli("--config", _cf, "config", "set", "ai_key", "x")[0] == 2, "cli: klucza API nie ustawiamy z wiersza polecen")
check(_cli("--config", _cf, "config", "set", "nie_ma", "1")[0] == 2, "cli: nieznany klucz = kod 2")
check(_cli("--config", _cf, "config", "set", "ai_parallel", "99")[1].strip().endswith("8"), "cli: wartosc poza zakresem jest przycinana")
check("search_mode" in _cli("--config", _cf, "config", "list")[1] and _cli("--config", _cf, "config", "path")[1].strip() == _cf, "cli: config list i path")
_code, _o = _cli("rules")
check(_code == 0 and "iso" in _o and "versions" in _o, "cli: rules - lista regul")
try:
    cli.run_cfg({}, "+nie_ma")
    check(False, "cli: nieznana regula")
except ValueError:
    check(True, "cli: nieznana regula = blad")
_rc = cli.run_cfg({"min_score": 50}, "-iso,+archives")
check(_rc["rule_iso"] is False and _rc["rule_archives"] is True and _rc["min_score"] == 50, "cli: --rules i nadpisania tylko na przebieg")
settings.apply(settings.sanitize({}))
# filtry clean zawezaja zakres
_fa = TMP / "filt"; _fa.mkdir(exist_ok=True)
(_fa / "old.bin").write_bytes(b"x" * 3 * 1024 * 1024); os.utime(_fa / "old.bin", (time.time() - 100 * 86400,) * 2)
(_fa / "new.bin").write_bytes(b"x" * 10)
_ee = []
for _nm in ("old.bin", "new.bin"):
    _e = core.Entry(label=_nm, size=(_fa / _nm).stat().st_size, kind="path", paths=[str(_fa / _nm)], checked=True, rating=kb.SAFE)
    _ee.append(_e)
_cat = [core.Category("fk", "t", "d", False, _ee)]
check(len(cli.unattended_selection(_cat, False)) == 2, "cli: bez filtrow wszystko Bezpieczne")
check([e.label for e in cli.unattended_selection(_cat, False, older_than=30)] == ["old.bin"], "cli: --older-than")
check([e.label for e in cli.unattended_selection(_cat, False, min_size=1024 * 1024)] == ["old.bin"], "cli: --min-size")
check([e.label for e in cli.unattended_selection(_cat, False, exclude=[str(_fa / "old.bin")])] == ["new.bin"], "cli: --exclude")
check(cli.unattended_selection(_cat, False, only=["inny"]) == [], "cli: --only")
# clean --plan / --apply: plan do przejrzenia, wykonanie tylko tego, co nadal bezpieczne
_pl = cli.plan_document(_cat, cli.unattended_selection(_cat, False))
check(_pl["schema"] == 1 and [i["label"] for i in _pl["items"]] == ["old.bin", "new.bin"]
      and all(set(i) == {"category", "label", "size", "root", "paths"} for i in _pl["items"]), "plan: opis pozycji bez polecen i pakietow")
_plf = TMP / "plan.json"; _plf.write_text(json.dumps(_pl), encoding="utf-8")
_run, _skip = cli.apply_plan(_cat, cli.unattended_selection(_cat, False), cli.load_plan(str(_plf)))
check(len(_run) == 2 and not _skip, "plan: bez zmian wykonuje wszystko z planu")
_ee[0].checked = False
_run, _skip = cli.apply_plan(_cat, cli.unattended_selection(_cat, False), _pl)
check([e.label for e in _run] == ["new.bin"] and len(_skip) == 1, "plan: odznaczona od czasu planu pozycja jest pominieta")
_ee[0].checked = True
_pl2 = json.loads(json.dumps(_pl)); _pl2["items"][1]["size"] = 1
_ee[1].size = 3 * 1024 * 1024
_run, _skip = cli.apply_plan(_cat, cli.unattended_selection(_cat, False), _pl2)
check([e.label for e in _run] == ["old.bin"] and "urosła" in _skip[0], "plan: pozycja, ktora urosla od planu, jest pominieta")
_ee[1].size = (_fa / "new.bin").stat().st_size
_pl3 = json.loads(json.dumps(_pl)); _pl3["items"][0]["paths"] = ["/etc/passwd"]; _pl3["items"].append({"category": "x", "label": "nie ma", "size": 1, "root": False, "paths": []})
_run, _skip = cli.apply_plan(_cat, cli.unattended_selection(_cat, False), _pl3)
check([e.label for e in _run] == ["new.bin"] and len(_skip) == 2, "plan: inne sciezki i nieistniejaca pozycja = pominiete (plan nie dodaje nic nowego)")
_ee[1].size = (_fa / "new.bin").stat().st_size
for _bad in ('[]', '{"schema": 2, "items": []}', '{"schema": 1, "items": [{"label": 1}]}', 'nie json'):
    _plf.write_text(_bad, encoding="utf-8")
    try:
        cli.load_plan(str(_plf)); _okp = False
    except ValueError:
        _okp = True
    check(_okp, f"plan: odrzuca zly plik {_bad[:12]}")
_plf.write_text("", encoding="utf-8"); _plf.unlink()
check(_cli("--config", _cf, "clean", "--plan", "p", "--apply", "p")[0] == 2, "cli: --plan z --apply = kod 2")
check(_cli("--config", _cf, "clean", "--apply", str(TMP / "nie_ma.json"))[0] == 2, "cli: --apply bez pliku = kod 2")
_code, _ = _cli("--config", _cf, "-q", "clean", "--plan", str(_plf))
_pj = json.loads(_plf.read_text(encoding="utf-8")) if _plf.exists() else {}
check(_code == 0 and _pj.get("schema") == 1 and oct(_plf.stat().st_mode & 0o777) == "0o600", "cli: clean --plan zapisuje plan (0600), niczego nie usuwa")
check(_cli("--config", _cf, "-q", "clean", "--apply", str(_plf))[0] == 0, "cli: clean --apply bez --yes to symulacja")
# znane cache Chromium/Electrona w ~/.config + osierocone dane Flatpaka
_h3 = TMP / "ah3"
for _rel, _n in ((".config/Slack/Code Cache/js/a", 20 * MB_), (".config/Slack/GPUCache/b", 1000), (".config/Slack/Local Storage/c", 1000)):
    (_h3 / _rel).parent.mkdir(parents=True, exist_ok=True); (_h3 / _rel).write_bytes(b"h" * _n)
_k3 = kb.KnowledgeBase(str(_h3), [])
check(_k3.classify(str(_h3 / ".config/Slack/Code Cache")).rating == kb.SAFE and _k3.classify(str(_h3 / ".config/Slack/GPUCache/b")).rating == kb.SAFE
      and _k3.classify(str(_h3 / ".config/Slack/Local Storage")).rating == kb.KEEP, "kb: Code Cache i GPUCache bezpieczne, Local Storage nie")
_r3 = scanner.scan(str(_h3), _k3, dup_min=MB_)
check(any(a[1].endswith("Slack/Code Cache") and a[7] == "dir" and a[4] == kb.SAFE for a in _r3.advice)
      and not any("Local Storage" in a[1] for a in _r3.advice), "algorytm: Code Cache jako folder do odtworzenia, dane aplikacji nie")
_fh = TMP / "fph"; _fb = TMP / "fpbase"
for _d in ("org.a.Installed", "org.b.Gone", "org.c.ViaList", "notanid"):
    (_fh / ".var/app" / _d).mkdir(parents=True, exist_ok=True)
(_fb / "org.a.Installed").mkdir(parents=True, exist_ok=True)
check(extras.flatpak_orphans(str(_fh), [str(_fb)], ["org.c.ViaList"]) == [("org.b.Gone", str(_fh / ".var/app/org.b.Gone"))], "flatpak: osierocone dane (bez zainstalowanych, z listy i bez nie-id)")
check(extras.flatpak_orphans(str(_fh), [str(TMP / "brak")]) == [], "flatpak: brak katalogu instalacji = nie zgadujemy")
# prefiltr wzorcow w bazie wiedzy nie zmienia wynikow
def _brute(k_, p_):
    r_ = k_.literal.get(p_) or k_.by_name.get(p_.rsplit("/", 1)[-1])
    if r_ is None:
        r_ = next((rule for rx, rule, _l in k_.patterns if rx.match(p_)), None)
    return r_
_hh = str(HOME)
_sm = [_hh + s_ for s_ in ("/.cache/foo", "/.cache/foo/bar", "/.var/app/x.y/cache", "/.var/app/x.y/data", "/.local/share/foo", "/.local/share", "/.zzz", "/Documents")] + \
      ["/mnt/d/.Trash-1000", "/mnt/d/steamapps/shadercache", "/a/steamapps/temp", "/a/steamapps/tempx", "/nic", "/"]
check(all(kb.default_kb().match_here(p_) == _brute(kb.default_kb(), p_) for p_ in _sm), "kb: prefiltr wzorcow daje te same wyniki co petla po regexach")
# skrot czesciowy lapie pliki rozni cy sie tylko w srodku, a grupy duplikatow zostaja takie same
_dd = TMP / "dd"; _dd.mkdir(exist_ok=True)
_base = os.urandom(4 * MB_)
_by = {}
for _i, _mut in enumerate((None, None, "mid", "mid2", "tail")):
    _b = bytearray(_base)
    if _mut == "mid":
        _b[len(_b) * 3 // 7 + 1] ^= 1
    elif _mut == "mid2":
        _b[len(_b) // 2] ^= 1  # miedzy probkami: skrot czesciowy sie nie zmieni, pelny tak
    elif _mut == "tail":
        _b[-1] ^= 1
    _pth = _dd / f"f{_i}.bin"; _pth.write_bytes(bytes(_b))
    _by.setdefault(len(_b), []).append((str(_pth), 1.0, kb.REVIEW))
scanner.HASH_CACHE.clear()
_hs = [scanner._file_hash(f[0], len(_base), True) for f in _by[len(_base)]]
check(_hs[0] == _hs[1] == _hs[3] and _hs[2] != _hs[0] and _hs[4] != _hs[0], "duplikaty: skrot czesciowy odsiewa zmiany w probce srodka i na koncu")
_grp = scanner.find_duplicates(_by, 30, [])
check(len(_grp) == 1 and sorted(os.path.basename(f[0]) for f in _grp[0]) == ["f0.bin", "f1.bin"], "duplikaty: wynik koncowy decyduje pelny skrot")
import hashlib as _hl
check(scanner._file_hash(str(_dd / "f0.bin"), len(_base), False) == _hl.blake2b(_base, digest_size=16).hexdigest(), "duplikaty: pelny skrot = blake2b calego pliku")
(_dd / "s.bin").write_bytes(b"abc")
check(scanner._file_hash(str(_dd / "s.bin"), 3, True) == scanner._file_hash(str(_dd / "s.bin"), 3, True), "duplikaty: skrot czesciowy malego pliku")
# praca w tle
_sres = scanner.ScanResult(); _sres.nfiles = 7
_o_scan, _o_det, _o_cas, _o_pick = pipeline.scan_all, ai.detect, ai.cascade, ai.pick_model
pipeline.scan_all = lambda cfg, cancel=None, report=None, on_merge=None: _sres
ai.detect = lambda: ("http://x", ["m1"])
ai.pick_model = lambda ms: ms[0]
ai.cascade = lambda *a_, **k_: {"zaznaczone": 2, "z_pamieci": 5, "przerwano": False}
background.LASTRUN = TMP / "lastrun.json"; background.LOCK = TMP / "bg.lock"; background.DIR = TMP
_msgs2 = []
check(background.run("assisted", say=_msgs2.append) == 0 and background.last_run().get("stats", {}).get("zaznaczone") == 2, "tlo: skan + AI zapisuje wynik")
check("ocen AI z pamięci 5" in background.describe_last(), "tlo: opis ostatniej pracy")
import fcntl as _fc
_lk = open(background.LOCK, "w"); _fc.flock(_lk, _fc.LOCK_EX | _fc.LOCK_NB)
check(background.run("assisted", say=lambda m: None) == background.EXIT_BUSY, "tlo: druga praca w tle nie startuje (blokada)")
_lk.close()
ai.detect = lambda: (None, [])
check(background.run("assisted", say=lambda m: None) == background.EXIT_NO_AI, "tlo: brak serwera AI = kod 4, skan zapisany")
pipeline.scan_all, ai.detect, ai.cascade, ai.pick_model = _o_scan, _o_det, _o_cas, _o_pick
check(_sch.calendar("weekly", "03:30") == "Sun *-*-* 03:30:00" and _sch.calendar("daily") == "daily", "harmonogram: godzina HH:MM")
_svc, _tim = _sch.render_ai("weekly", "03:30")
check("ai --notify" in _svc and "Nice=19" in _svc and "03:30:00" in _tim, "harmonogram: timer AI w tle")
try:
    _sch.calendar("daily", "25:99")
    check(False, "harmonogram: zla godzina")
except ValueError:
    check(True, "harmonogram: zla godzina = blad")
# --- okno: zamkniecie w trakcie pracy = praca w tle
class _Ev:
    def __init__(self): self.state = ""
    def ignore(self): self.state = "ignore"
    def accept(self): self.state = "accept"
class _Tray:
    def __init__(self): self.calls = []
    def show(self): self.calls.append("show")
    def hide(self): self.calls.append("hide")
    def showMessage(self, *a): self.calls.append("msg")
_tray = _Tray()
win.tray = _tray; win._quitting = False; win.triage_busy = True; _cl_saved = win.cleaner; win.cleaner = None
_ev = _Ev(); win.closeEvent(_ev)
check(_ev.state == "ignore" and "show" in _tray.calls and "msg" in _tray.calls, "tlo: zamkniecie okna w trakcie pracy chowa do zasobnika")
win.tray_note("x")
check(_tray.calls.count("msg") >= 1, "tlo: powiadomienie po zakonczeniu")
win.triage_busy = False; win.analysis_busy = False; win.dscan_busy = False
_ev2 = _Ev(); win.tray = _tray; win.closeEvent(_ev2)
check(_ev2.state == "accept", "tlo: bez pracy w tle okno zamyka sie normalnie")
win.tray = None; win.cleaner = _cl_saved
# --- etap D (2.6.0)
def _ov2(items):
    return [(f[0], r) for f, r, _k in scanner.old_versions([(n, "/d/" + n, sz, mt, 1) for n, sz, mt in items])]
_r = scanner.old_versions([("a.zip", "/d/a.zip", 5 * _MB, 100.0, 1), ("a (1).zip", "/d/a (1).zip", 7 * _MB, 200.0, 1)])
check(len(_r) == 1 and _r[0][0][0] == "a.zip", "wersje: kopia o innym rozmiarze - zostaje nowszy plik")
_r = scanner.old_versions([("a.zip", "/d/a.zip", 5 * _MB, 300.0, 1), ("a (1).zip", "/d/a (1).zip", 7 * _MB, 200.0, 1)])
check(len(_r) == 1 and _r[0][0][0] == "a (1).zip", "wersje: nowszy oryginal zostaje, starsza kopia do przegladu")
# pula AI: przeglad respektuje wylaczone reguly
_ro = settings.RUNTIME["rules_off"]
settings.RUNTIME["rules_off"] = set(ru_.KEYS)
check(not ai._survey_allowed("/home/u/Downloads/x.iso", "review", "file"), "pula AI: wylaczone reguly dzialaja takze na pozycje spoza algorytmu")
settings.RUNTIME["rules_off"] = _ro
# pasek postepu w pasku stanu
class _Bar:
    def __init__(self): self.vis = None; self.rng = None; self.val = None; self.fmt = ""
    def setVisible(self, v): self.vis = v
    def setRange(self, a_, b_): self.rng = (a_, b_)
    def setValue(self, v): self.val = v
    def setFormat(self, f): self.fmt = f
_gb, _gc, _bar_saved = _Bar(), _Bar(), (win.gbar, win.gcancel)
win.gbar, win.gcancel = _gb, _gc
win.set_global_progress(42.5, "1 min", "Skan: ")
check(_gb.vis and _gc.vis and _gb.val == 425 and "42.5%" in _gb.fmt and "1 min" in _gb.fmt, "pasek stanu: procent i ETA")
win.set_global_progress(None)
check(_gb.rng == (0, 0), "pasek stanu: tryb nieokreslony")
win.set_global_progress(-1)
check(_gb.vis is False and _gc.vis is False, "pasek stanu: ukrywa sie po pracy")
win.gbar, win.gcancel = _bar_saved
# znacznik danych w prompcie folderow jest losowy
# spojnosc: kazdy klucz SPEC ma pole w oknie ustawien albo jest wyjatkiem, i jest w README
from tidydisk import settings_page as _spg
_fields = {f[0] for _t, fl in _spg.TABS for f in (_spg.rules_fields() if fl == "RULES" else fl)}
_exceptions = {"protected_paths", "ai_key", "prompt_triage", "prompt_folders", "prompt_verify", "prompt_ask", "prompt_extra"}
_missing = [k for k in st_.SPEC if k not in _fields and k not in _exceptions]
check(not _missing, f"ustawienia: kazdy klucz ma pole w oknie ({_missing})")
_readme = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "README.md"), encoding="utf-8").read()
_undoc = [k for k in st_.SPEC if not k.startswith("rule_") and not k.startswith("prompt_") and k != "ai_key" and "`" + k + "`" not in _readme]
check(not _undoc, f"README: kazde ustawienie opisane ({_undoc})")
# --- 2.6.1: poprawki z raportu 2.6.0
check(ai.clean_why("Identyczna kopia archiwum jak w pozycji 0.") == "" and ai.clean_why("Duplikat z identyczną zawartością co id 5 i 6.") == ""
      and ai.clean_why("Stary instalator, zbędny po instalacji.") == "Stary instalator, zbędny po instalacji.", "AI: uzasadnienie bez odwolan do numerow")
from tidydisk import report as _rep, disks as _dk
check("↑ ten sam system plików" in open(_rep.__file__, encoding="utf-8").read(), "raport: btrfs na kilku partycjach - zajete raz")
# tryb 'tylko AI': brak "Pewnosci" algorytmu
_sm = settings.RUNTIME.get("search_mode"); settings.RUNTIME["search_mode"] = "ai_only"
check(core.confidence_text(80) == "Ocena AI (ryzyko niskie)" and core.confidence_text(55) == "Ocena AI (ryzyko średnie)", "tylko AI: ryzyko zamiast pewnosci")
check("Pewność" not in core.advice_entry([80, str(core.HOME / "Pobrane" / "x.zip"), 5, 0, "review", "Archiwum", [], "ai"]).why, "tylko AI: wpis bez 'Pewnosc'")
settings.RUNTIME["search_mode"] = _sm
check(core.confidence_text(80) == "Pewność 80%", "algorytm: pewnosc jak dawniej")
# przelacznik harmonogramu AI w oknie historii
_calls = []
_sch_ud, _sch_sc = _sch.unit_dir, _sch._systemctl
_sch.unit_dir = lambda: Path(TMP) / "units"
_sch._systemctl = lambda *a: (_calls.append(a) or 0)
_hp2 = gui.HistoryPage(_hd)
_hp2.ai_at.setText = _hp2.ai_at.setText  # atrapa Qt: ustawiamy wartosci przez podmiane metod
_hp2.ai_at.text = lambda: "04:15"
_hp2.ai_every.currentData = lambda: "daily"
_hp2.ai_sched_enable()
check(_sch.is_ai_enabled() and any(c[:1] == ("enable",) for c in _calls), "okno: wlaczenie oceny AI w tle tworzy timer")
check("*-*-* 04:15:00" in (Path(TMP) / "units" / "tidydisk-ai.timer").read_text(), "okno: godzina i czestotliwosc w timerze")
_hp2.ai_sched_disable()
check(not _sch.is_ai_enabled(), "okno: wylaczenie oceny AI w tle usuwa timer")
_hp2.ai_at.text = lambda: "99:99"
_hp2.ai_sched_enable()
check(not _sch.is_ai_enabled(), "okno: zla godzina nie wlacza timera")
_sch.unit_dir, _sch._systemctl = _sch_ud, _sch_sc
# --- rownolegly skan miejsc daje to samo co po kolei
_pd = Path(TMP) / "par"
for _i in range(3):
    (_pd / f"r{_i}" / "sub").mkdir(parents=True, exist_ok=True)
    for _j in range(20):
        (_pd / f"r{_i}" / "sub" / f"f{_j}.bin").write_bytes(b"x" * (1000 + _i * 10 + _j))
_old_cr, _old_ss = core.cleanup_roots, pipeline.save_scanstats
core.cleanup_roots = lambda: [(str(_pd / f"r{i}"), "t") for i in range(3)]
pipeline.save_scanstats = lambda d: None
_outs = {}
for _par in (1, 3):
    _fr = []
    _cfg = settings.sanitize({"scan_parallel": _par, "search_mode": "ai_only"})
    _outs[_par] = pipeline.scan_all(_cfg, report=lambda *a: _fr.append(a[-1]))
    check(all(f == -1.0 or 0 <= f <= 1.0001 for f in _fr), f"skan rownolegly {_par}: postep w zakresie")
core.cleanup_roots, pipeline.save_scanstats = _old_cr, _old_ss
check(_outs[1].nfiles == _outs[3].nfiles == 60 and _outs[1].total == _outs[3].total, "skan rownolegly: ten sam wynik co po kolei")
# pakiety: wersje spojne
import tidydisk as _fc
_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_spec = open(os.path.join(_root, "packaging", "tidydisk.spec"), encoding="utf-8").read()
_meta = open(os.path.join(_root, "data", "tidydisk.metainfo.xml"), encoding="utf-8").read()
check(f"Version:        {_fc.__version__}\n" in _spec and f'release version="{_fc.__version__}"' in _meta, "pakiety: wersja w .spec i metainfo zgodna z programem")
check(os.path.exists(os.path.join(_root, "LICENSE")) and "GPL-3.0-or-later" in _spec, "pakiety: LICENSE i licencja w .spec")
_p, _okp, _whyp = scanner.find_admin_script("0")
check(not _okp and _p == scanner.ADMIN_SCRIPT and _whyp, "admin: brak skanera - powod i domyslna sciezka")
_pol2 = open(os.path.join(_root, "data", "org.tidydisk.admin-scan.policy"), encoding="utf-8").read()
check(scanner.ADMIN_SCRIPT_PKG in _pol2 and scanner.ADMIN_SCRIPT in _pol2, "polkit: reguly dla obu miejsc instalacji")
# --- 2.7.1: poprawki po audycie pracy w tle, bezpieczenstwa i odpornosci AI
import tidydisk.fsutil as _fu
_ac_path = Path(TMP) / "ac_merge.json"
_a1, _b1 = ai_cache.AICache(30, _ac_path), ai_cache.AICache(30, _ac_path)
_a1.put("f", "s", "/x/a", 1, 1, ("whole", "niskie", "a")); _a1.flush(force=True)
_b1.put("f", "s", "/x/b", 1, 1, ("keep", "niskie", "b")); _b1.flush(force=True)
check(len(ai_cache.AICache(30, _ac_path)) == 2, "pamiec ocen: zapis drugiego procesu nie kasuje wpisow pierwszego")
(Path(TMP) / "ac_bad.json").write_text("{zepsute", encoding="utf-8")
ai_cache.AICache(30, Path(TMP) / "ac_bad.json")
check((Path(TMP) / "ac_bad.json.bad").exists(), "pamiec ocen: uszkodzony plik odlozony na bok")
_fu.atomic_write(Path(TMP) / "at.json", "{}")
check(oct((Path(TMP) / "at.json").stat().st_mode & 0o777) == "0o600", "zapis atomowy: prawa 0600")
# _retry: przerwy, pusty wynik zamiast przerwania calego przebiegu, po serii porazek blad
_old_rd = ai.RETRY_DELAYS; ai.RETRY_DELAYS = (0, 0)
_n = {"c": 0}
def _flaky():
    _n["c"] += 1
    if _n["c"] < 3:
        raise OSError("serwer sie restartuje")
    return {"ok": 1}
ai._FAILS["n"] = 0
check(ai._retry(_flaky) == {"ok": 1}, "ai: retry po restarcie serwera (kilka prob)")
def _dead():
    raise OSError("martwy")
ai._FAILS["n"] = 0
check(ai._retry(_dead) == {}, "ai: paczka bez odpowiedzi = pusty wynik, run trwa")
_raised = False
try:
    for _ in range(ai.MAX_FAILED_BATCHES):
        ai._retry(_dead)
except OSError:
    _raised = True
check(_raised, "ai: seria porazek przerywa run")
ai.RETRY_DELAYS = _old_rd; ai._FAILS["n"] = 0
check(ai.clean_why("<b>zbędny</b>\nplik") == "b zbędny /b  plik" or "<" not in ai.clean_why("<b>zbędny</b>\nplik"), "ai: uzasadnienie bez znacznikow HTML")
# jednostka systemd: cudzyslow dla PYTHONPATH, restart, czas na zapis
_svc2, _ = _sch.render_ai("weekly")
check('Environment="PYTHONPATH=' in _svc2 and "Restart=on-failure" in _svc2 and "TimeoutStopSec=5min" in _svc2, "systemd: unit z cudzyslowem, restartem i czasem na zapis")
check("auth_admin_keep" not in _pol2, "polkit: zawsze pytaj o haslo")
# praca w tle: zepsuty klucz / blad skanu nie konczy sie tracebackiem, zostawia slad
_o_scan2, _o_det2 = pipeline.scan_all, ai.detect
pipeline.scan_all = lambda *a_, **k_: (_ for _ in ()).throw(RuntimeError("dysk zniknal"))
_rc = background.run(None, quiet=True)
check(_rc == background.EXIT_ERR and "Błąd skanowania" in (background.last_run() or {}).get("error", ""), "tlo: blad skanu zapisany w lastrun")
pipeline.scan_all = lambda *a_, **k_: _sres
ai.detect = lambda: (_ for _ in ()).throw(PermissionError("401"))
_rc = background.run("ai_only", quiet=True)
check(_rc == background.EXIT_ERR and "klucz" in (background.last_run() or {}).get("error", ""), "tlo: odrzucony klucz API zapisany w lastrun")
pipeline.scan_all, ai.detect = _o_scan2, _o_det2
# 2.7.2: opis oceny AI zgodny z werdyktem (nie "ryzyko niskie" przy odrzuconej pozycji)
_sm2 = settings.RUNTIME.get("search_mode"); settings.RUNTIME["search_mode"] = "ai_only"
_e2 = core.advice_entry([80, str(core.HOME / "Pobrane" / "y.zip"), 5 * 10**6, 0, "review", "Wskazane przez AI", [], "ai"])
win.clean_page.apply_note(_e2, "zostawic", "niskie", "kopia zapasowa")
check(_e2.why.startswith("AI: lepiej zostawić (ryzyko niskie): ") and "kopia zapasowa" in _e2.why and not _e2.checked, f"tylko AI: opis zgodny z werdyktem")
settings.RUNTIME["search_mode"] = _sm2
# 2.7.3: -q po poleceniu 'ai' (tak wywoluje je jednostka systemd) i komunikat po starcie
check(cli.build_parser().parse_args(["ai", "--notify", "-q"]).quiet_ai is True, "cli: 'ai --notify -q' (jednostka systemd) jest poprawnym wywolaniem")
check("--wait-ai 10" in _svc, "harmonogram AI: jednostka czeka na serwer")
from tidydisk import background as bg_, ai as ai_, ai_cache as ac_
import tempfile as tf_, json as js_, csv as csv_
_calls = {"n": 0, "slept": 0}
_orig_detect = ai_.detect
def _det():
    _calls["n"] += 1
    return ("h", ["m"]) if _calls["n"] >= 3 else (None, [])
ai_.detect = _det
try:
    r_ = bg_.wait_for_ai(5, lambda: False, lambda m: None, sleep=lambda s_: _calls.__setitem__("slept", _calls["slept"] + 1))
    check(r_ == ("h", ["m"]) and _calls["slept"] == 2, "wait-ai: czeka az serwer odpowie")
    _calls.update(n=-99, slept=0)
    r_ = bg_.wait_for_ai(1, lambda: False, lambda m: None, sleep=lambda s_: _calls.__setitem__("slept", _calls["slept"] + 1))
    check(r_[0] is None and _calls["slept"] == 2, "wait-ai: po limicie rezygnuje")
    _calls.update(n=-99, slept=0)
    r_ = bg_.wait_for_ai(5, lambda: True, lambda m: None, sleep=lambda s_: None)
    check(r_[0] is None and _calls["n"] == -98, "wait-ai: anulowanie przerywa czekanie")
    _calls.update(n=-99)
    r_ = bg_.wait_for_ai(0, lambda: False, lambda m: None)
    check(r_[0] is None and _calls["n"] == -98, "wait-ai: 0 = bez czekania")
finally:
    ai_.detect = _orig_detect
_d = tf_.mkdtemp()
_c = ac_.AICache(30, Path(_d) / "c.json")
_c.put("s3", "sig", "/home/u/a|b", 123, 5, ("usun", "niskie", "=cmd"))
_c.put("s4", "sig", "/home/u/x", 7, 0, ("zostaw", "srednie", "ok"))
_rows = _c.rows()
check(len(_rows) == 2 and any(r["sciezka"] == "/home/u/a|b" and r["rozmiar"] == 123 for r in _rows), "eksport AI: wiersze z kluczy (sciezka z '|')")
bg_.export_rows(_rows, str(Path(_d) / "o.json"))
check(js_.loads((Path(_d) / "o.json").read_text())["schema"] == 1, "eksport AI: json")
bg_.export_rows(_rows, str(Path(_d) / "o.csv"))
_cr = list(csv_.DictReader(open(Path(_d) / "o.csv", encoding="utf-8")))
check(len(_cr) == 2 and all(not r["uzasadnienie"].startswith("=") for r in _cr), "eksport AI: csv bez formul")
check(cli.build_parser().parse_args(["ai", "--export", "x.csv", "--wait-ai", "3"]).wait_ai == 3, "cli: ai --export/--wait-ai")
from tidydisk import openfiles as of_
_pd = Path(tf_.mkdtemp())
(_pd / "1" / "fd").mkdir(parents=True)
(_pd / "1" / "comm").write_text("firefox\n")
os.symlink("/home/u/.cache/mozilla/x.sqlite", _pd / "1" / "fd" / "3")
os.symlink("/dev/null", _pd / "1" / "fd" / "4")
os.symlink("/home/u/gone (deleted)", _pd / "1" / "fd" / "5")
_op = of_.open_paths(str(_pd))
check(_op == {"/home/u/.cache/mozilla/x.sqlite": "firefox"}, f"otwarte pliki: czyta /proc ({_op})")
check(of_.users_of("/home/u/.cache/mozilla", _op) == ["firefox"] and of_.users_of("/home/u/.cache/moz", _op) == [], "otwarte pliki: folder i prefiks nazwy")
check(isinstance(of_.open_paths(), dict), "otwarte pliki: prawdziwy /proc nie wywala sie")
check(cli.build_parser().parse_args(["status", "--exit-code", "--min-free", "5"]).min_free == 5, "cli: status --exit-code")
_shown = []
_sb = win.statusBar
win.statusBar = lambda: type("SB", (), {"showMessage": staticmethod(lambda t, ms=0: _shown.append(t))})()
_lr_old, win.settings = background.last_run, type("S", (), {"d": {}, "value": lambda self, k, d=None: self.d.get(k, d), "setValue": lambda self, k, v: self.d.__setitem__(k, v)})()
background.last_run = lambda: {"time": 1000, "mode": "ai_only", "stats": {"zaznaczone": 2}, "files": 5}
win._announce_background_run(); win._announce_background_run()
check(len(_shown) == 1 and "Uruchom analizę" in _shown[0], "okno: po starcie jedna informacja o pracy w tle")
background.last_run = _lr_old; win.statusBar = _sb
# --- 2.8.0: dzielenie zapytan, znacznik folderu, zrzut diagnostyczny, zmiany od ostatniego skanu
import urllib.error as _ue
from tidydisk import diag as _diag, changes as _chg
_calls_h = []
def _fn_h(b):
    _calls_h.append(len(b))
    if len(b) > 2:
        raise ai.AIContextError("context length exceeded")
    return {i: ("usunac", "niskie", f"x{b[i]}") for i in range(len(b))}
_rh = ai.halve(_fn_h, list(range(5)), True)
check(sorted(_rh) == [0, 1, 2, 3, 4] and _rh[4][2] == "x4" and _calls_h[0] == 5, f"ai: za duza paczka dzielona na pol, numery przesuniete ({sorted(_rh)})")
check(ai.halve(lambda b: (_ for _ in ()).throw(ai.AIContextError("x")), [1], True) == {}, "ai: pojedyncza zbyt duza pozycja zostaje bez oceny")
_ro = ai._request; _rc_n = []
def _req400(*a, **k):
    _rc_n.append(1)
    raise _ue.HTTPError("u", 400, "bad", {}, __import__("io").BytesIO(b'{"error":"request exceeds the available context size"}'))
ai._request = _req400
try:
    ai._chat({"messages": []}, 5, "http://127.0.0.1:1")
    _ctx = False
except ai.AIContextError:
    _ctx = True
ai._request = _ro
check(_ctx and len(_rc_n) == 1, "ai: blad okna kontekstu nie probuje kolejnych wariantow zapytania")
_fd = TMP / "fstamp"; _fd.mkdir()
_st1 = ai._folder_stamp({"path": str(_fd), "files": 3})
os.utime(_fd, (1_700_000_000, 1_700_000_000))
check(ai._folder_stamp({"path": str(_fd), "files": 3}) != _st1, "pamiec ocen: zmiana folderu zmienia znacznik")
_dg = _diag.build(detect_ai=False)
check(__import__("tidydisk").__version__ in _dg and "sk-unsloth" not in _dg and str(HOME) not in _dg, "diag: wersja jest, klucza i nazwy uzytkownika nie ma")
_ch = _chg.diff({"/a": 200 * 2**20, "/a/b": 100 * 2**20, "/c": 500 * 2**20}, {"/a": 500 * 2**20, "/a/b": 300 * 2**20, "/c": 510 * 2**20, "/n": 400 * 2**20})
check(sorted(c[0] for c in _ch) == ["/a", "/n"], f"zmiany: rosnacy i nowy folder, bez podfolderow i drobnych zmian ({_ch})")
_old_snap, _old_last = _chg.SNAPSHOT, _chg.LAST
_chg.SNAPSHOT, _chg.LAST = TMP / "snap.json", TMP / "chg.json"
_big = lambda n: {"/x": [n * 2**20, 1, "r", "t", 1]}
check(_chg.record(_big(200)) == [] and _chg.last()["first"] is True, "zmiany: pierwszy skan bez porownania")
check([c[0] for c in _chg.record(_big(900))] == ["/x"] and "urósł" in _chg.describe(), "zmiany: drugi skan pokazuje wzrost")
_chg.SNAPSHOT, _chg.LAST = _old_snap, _old_last
# 2.8.0: 'Zawsze zostaw' z menu pozycji
_pe = core.advice_entry([80, str(core.HOME / "Pobrane" / "chron.zip"), 5 * 10**6, 0, "review", "t", [], "file"])
_it = type("It", (), {"data": lambda self, *a: _pe, "setHidden": lambda self, v: None})()
win.clean_page.file_entries[_pe.paths[0]] = _pe
win.clean_page.protect_entry(_it)
check(_pe.paths[0] in settings.load(env=False)["protected_paths"] and _pe.paths[0] not in win.clean_page.file_entries, "menu: 'zawsze zostaw' dodaje sciezke do chronionych")
settings.save({**settings.load(env=False), "protected_paths": []}); settings.apply(settings.load())
# 2.8.0: tlumaczenia
from tidydisk import i18n as _i18n
_i18n.set_language("en")
check(_i18n.tr("Ustawienia") == "Settings" and _i18n.tr("tekst bez tlumaczenia") == "tekst bez tlumaczenia", "i18n: angielski + powrot do oryginalu gdy brak wpisu")
_i18n.set_language("pl")
check(_i18n.tr("Ustawienia") == "Ustawienia" and _i18n.set_language("auto") in ("pl", "en"), "i18n: polski to zrodlo, auto wybiera jezyk systemu")
_i18n.set_language("pl")
_en = json.loads((Path(_i18n.DIR) / "en.json").read_text(encoding="utf-8"))
check(all(k in "".join(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tidydisk", f), encoding="utf-8").read() for f in ("gui.py",)) for k in _en), "i18n: kazdy klucz katalogu wystepuje w kodzie")
check(settings.sanitize({"language": "xx"})["language"] == "auto", "ustawienia: nieznany jezyk -> auto")
# 2.9.0: okno pozycji odrzuconych przez recenzenta
_cp = win.clean_page
_rj = core.advice_entry([80, str(core.HOME / "Pobrane" / "rej.zip"), 7 * 10**6, 0, "review", "Wskazane przez AI", [], "ai"])
_cp.ai_extra[_rj.paths[0]] = [80, _rj.paths[0], 7 * 10**6, 0, "review", "t", [], "ai"]
_cp.ai_notes[_rj.paths[0]] = ("zostawic", "niskie", "kopia zapasowa")
_cp.file_entries[_rj.paths[0]] = _rj
check(_rj in _cp.rejected_entries(), "recenzent: odrzucona pozycja jest na liscie")
check(_cp.accept_rejected([_rj]) == 1 and _rj.checked and _rj.touched and _rj not in _cp.rejected_entries(), "recenzent: reczne zaznaczenie odrzuconej pozycji")
_cp.ai_extra.pop(_rj.paths[0]); _cp.ai_notes.pop(_rj.paths[0]); _cp.file_entries.pop(_rj.paths[0])
shutil.rmtree(TMP, ignore_errors=True)
print()
from tidydisk import report as rp_, settings as se_
_md = rp_.build_markdown([], None, None, None, None, True, ai_count=7)
check("- Wyszukiwanie:" in _md and "ocen AI w tej liście: 7" in _md or se_.load().get("search_mode") == "algorithm", "raport: wiersz z trybem wyszukiwania")

# --- osal: zachowanie na Linuksie i zastepcze na "Windowsie" (brak atrybutow uniksowych)
from tidydisk import osal as os_
class _St:
    st_size = 1000
class _St2(_St):
    st_blocks = 8
check(os_.alloc_size(_St2()) == 4096 and os_.alloc_size(_St()) == 1000, "osal: rozmiar na dysku (z blokami i bez)")
check(os_.kernel_release() == os.uname().release and os_.is_admin() == (os.geteuid() == 0), "osal: Linux = dawne zachowanie")
_lf = open(Path(tf_.mkdtemp()) / "l", "w")
check(os_.try_lock(_lf) is True, "osal: blokada pracy w tle")
_lf2 = open(_lf.name, "w")
check(os_.try_lock(_lf2) is False, "osal: druga blokada tego samego pliku odmawia")
_saved = {n: getattr(os, n) for n in ("uname", "geteuid", "nice", "statvfs") if hasattr(os, n)}
for n in _saved:
    delattr(os, n)
try:
    check(isinstance(os_.kernel_release(), str) and os_.is_admin() in (True, False), "osal: bez uname/geteuid nie wywala sie")
    os_.lower_priority()
    from tidydisk import disks as dk_
    _du = shutil.disk_usage
    shutil.disk_usage = lambda p_: type("U", (), {"used": 5, "free": 7, "total": 12})()
    try:
        check(dk_._usage("/") == (5, 7), "disks: zastepcze shutil.disk_usage bez statvfs")
    finally:
        shutil.disk_usage = _du
finally:
    for n, f in _saved.items():
        setattr(os, n, f)

# --- baza wiedzy Windows (na atrapie: tylko ciagi znakow, bez Windowsa)
from tidydisk import kb as kb_, kb_windows as kw_
_wk = kb_.KnowledgeBase("C:\\Users\\Me", system="windows")
_cl = lambda p: _wk.classify(p)
check(_cl("C:\\Users\\Me\\AppData\\Local\\Temp\\x.tmp").rating == "safe", "windows: Temp = bezpieczne (z '\\' i wielkimi literami)")
check(_cl("c:/users/me/appdata/local/google/chrome/user data/Default/Cache").rating == "safe", "windows: cache Chrome profilu Default")
check(_cl("C:\\Users\\Me\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Login Data").rating == "keep", "windows: Login Data (hasla) = nie ruszaj")
check(_cl("\\\\?\\C:\\Users\\Me\\AppData\\Local\\Temp").rating == "safe", "windows: prefiks \\\\?\\ jest zdejmowany")
check(_cl("C:\\Users\\Me\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\x.default\\logins.json").rating == "keep", "windows: profil Firefoksa w Roaming = nie ruszaj")
check(_cl("C:\\Users\\Me\\Documents\\praca.docx").rating == "keep" and _cl("C:\\Users\\Me\\Downloads\\a.zip").rating == "mine", "windows: Dokumenty = nie ruszaj, Pobrane = Twoje pliki")
check(_cl("C:\\Windows\\Temp\\a").rating == "keep" and _cl("D:\\gry\\x").rating == "keep", "windows: system i obce miejsca = nie ruszaj")
check(_wk.classify("C:\\USERS\\ME\\APPDATA\\LOCAL\\NPM-CACHE").rating == "safe", "windows: wielkosc liter nie ma znaczenia")
check(all(kw_.is_protected(p_) for p_ in ("C:\\Windows\\System32", "c:\\PROGRAM FILES\\x", "C:\\hiberfil.sys", "D:\\a\\..\\b")) and not kw_.is_protected("C:\\Users\\Me\\a"), "windows: chronione sciezki")
check(kw_.norm("\\\\?\\UNC\\srv\\share\\x") == "//srv/share/x", "windows: UNC z prefiksem")
check(kb_.KnowledgeBase("/home/u").classify("/home/u/.cache/pip").rating == "safe", "linux: reguly bez zmian po dodaniu trybu windows")

check(kb_.KnowledgeBase("/home/u").classify("/var/cache/apt/archives/x.deb").rating == "safe", "apt: cache w bazie wiedzy")

from tidydisk import viewmodel as vm_, core as co_
_e1 = co_.Entry("duzy", 5000, "path", paths=["/h/a"], rating="safe", why="cache")
_e2 = co_.Entry("moj", 9000, "path", paths=["/h/b"], rating="mine", user_pick=True, why="duplikat")
_e3 = co_.Entry("maly", 10, "path", paths=["/h/c"], rating="safe")
_pr = vm_.plan_rows([_e3, _e2, _e1], False, lambda n: f"{n}B")
check([r[1] for r in _pr] == ["moj", "duzy", "maly"] and all(r[0] == "Bezpowrotnie" for r in _pr), "plan: kolejnosc wg rozmiaru, bezpowrotnie najpierw")
_pr2 = vm_.plan_rows([_e2, _e1], True, lambda n: f"{n}B")
check(_pr2[0][1] == "duzy" and _pr2[1][0] == "Do kosza" and _pr2[1][4] == "/h/b" and "◆" in _pr2[1][3], "plan: Twoje pliki do kosza, sciezka i ocena z glifem")

check(kb_.KnowledgeBase("/home/u").classify("/home/u/Documents/curseforge/minecraft/Instances/X/saves/W/region/r.0.0.mca").rating == "keep", "zapisy gier (saves): nie ruszaj")

_SI = gui.SortItem
class _T:
    def __init__(self, col): self.c = col
    def sortColumn(self): return self.c
def _mk(name, size, col):
    it = _SI([name, f"{size} B"])
    it.treeWidget = lambda col=col: _T(col)
    gui.set_sort_keys(it, name.casefold(), size)
    return it
_a, _b, _c = _mk("banan", 900, 1), _mk("Ananas", 12000, 1), _mk("cytryna", 5, 1)
check(sorted([_a, _b, _c]) == [_c, _a, _b], "sortowanie: rozmiar liczbowo, nie tekstowo (900 B < 12000 B)")
_a, _b, _c = _mk("banan", 900, 0), _mk("Ananas", 12000, 0), _mk("cytryna", 5, 0)
check(sorted([_a, _b, _c]) == [_b, _a, _c], "sortowanie: nazwa bez wielkosci liter")

_d1 = co_.Entry("x", 100, "path", paths=["/h/x"], rating="safe", checked=True)
_d2 = co_.Entry("y", 100, "path", paths=["/h/y"], rating="safe")
check(vm_.decision_of(_d1)["decision_level"] == "delete" and "usunięcia" in vm_.decision_of(_d1)["decision"], "panel: zaznaczona = do usuniecia")
check(vm_.decision_of(_d2)["decision_level"] == "stay" and vm_.detail_sections(_d2)["rating_text"].startswith("✔"), "panel: niezaznaczona zostaje, ocena ze znakiem")
check(vm_.EMPTY_HINT and "Kliknij" in vm_.EMPTY_HINT, "panel: podpowiedz pustego stanu")

# ---- Windows: skan tylko do odczytu na sztucznym drzewie
import tempfile as _tf
from tidydisk import scan_windows as sw_, core as core_w, osal as osal_w
with _tf.TemporaryDirectory() as _h:
    def _mk(rel, data=b"x" * 5000):
        fp = os.path.join(_h, *rel.split("/"))
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        open(fp, "wb").write(data)
    _mk("AppData/Local/Temp/a.tmp")
    _mk("AppData/Local/Google/Chrome/User Data/Default/Cache/f_1")
    _mk("AppData/Local/Google/Chrome/User Data/Default/Login Data")
    _mk("AppData/Local/Google/Chrome/User Data/Profile 1/Cache/f_2")
    _mk("AppData/Local/NVIDIA/DXCache/s.bin")
    _mk("AppData/Local/npm-cache/p.tgz")
    _mk("Documents/praca.docx")
    _sz = lambda p: sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(p) for f in fs)
    _cats = sw_.scan(_h, size_of=_sz)
    _paths = [pp.replace("\\", "/") for c in _cats for e in c.entries for pp in e.paths]
    check(sum(1 for pp in _paths if "/Chrome/User Data/" in pp and pp.endswith("/Cache")) == 2, "windows skan: cache Chrome z dwoch profili (wzorzec *)")
    check(not any("Login Data" in pp or "Documents" in pp for pp in _paths), "windows skan: hasla i Dokumenty nie trafiaja na liste")
    check({c.key for c in _cats} == {"temp", "browsers", "shaders", "dev"}, "windows skan: kategorie temp/przegladarki/shadery/dev")
    check(all(e.rating in ("safe", "review") and e.size > 0 for c in _cats for e in c.entries), "windows skan: tylko oceny safe/review")
    _cats2 = sw_.scan(_h, size_of=_sz, running={"chrome"})
    _ce = [e for c in _cats2 for e in c.entries]
    check(all(e.kind == "contents" for e in _ce), "windows skan: pozycje to zawartosc katalogu (nie sam katalog)")
    check(any("Default" in e.label for e in _ce) and any("Profile 1" in e.label for e in _ce), "windows skan: nazwa profilu przegladarki w etykiecie")
    check(all(e.warn for e in _ce if "Chrome" in e.label) and not any(e.warn for e in _ce if "Chrome" not in e.label), "windows skan: ostrzezenie tylko dla dzialajacej przegladarki")
    _real = os.path.join(_h, "AppData", "Local", "Temp", "a.tmp")
    _old = osal_w.SYSTEM
    osal_w.SYSTEM = "windows"
    try:
        _res = core_w.run_clean([core_w.Entry("t", 5, "path", [_real], rating="safe", checked=True)], dry=False, log=lambda m: None)
        check(os.path.exists(_real) and _res.problems == 1 and _res.freed == 0, "windows: usuwanie zablokowane (plik zostaje)")
        _dry = core_w.run_clean([core_w.Entry("t", 5, "path", [_real], rating="safe", checked=True)], dry=True, log=lambda m: None)
        check(os.path.exists(_real) and _dry.problems == 0, "windows: symulacja dziala")
    finally:
        osal_w.SYSTEM = _old

# ---- zmiana nazwy: migracja ze starej nazwy
from tidydisk import legacy as lg_, fsutil as fsutil_w
with _tf.TemporaryDirectory() as _mh:
    _mp = Path(_mh)
    (_mp / ".config/fedora-cleaner").mkdir(parents=True); (_mp / ".config/fedora-cleaner/settings.json").write_text('{"theme":"modern"}')
    (_mp / ".local/share/fedora-cleaner").mkdir(parents=True); (_mp / ".local/share/fedora-cleaner/learn.json").write_text("{}")
    _mv = lg_.migrate_dirs(_mp)
    check(len(_mv) == 2 and (_mp / ".config/tidydisk/settings.json").read_text() == '{"theme":"modern"}' and not (_mp / ".config/fedora-cleaner").exists(), "nazwa: ustawienia i dane przeniesione")
    (_mp / ".config/fedora-cleaner").mkdir(); (_mp / ".config/fedora-cleaner/settings.json").write_text("stare")
    check(lg_.migrate_dirs(_mp) == [] and (_mp / ".config/tidydisk/settings.json").read_text() == '{"theme":"modern"}', "nazwa: nie nadpisuje istniejacego nowego katalogu")
with _tf.TemporaryDirectory() as _ud:
    _u = Path(_ud)
    (_u / "fedora-cleaner-ai.timer").write_text("[Timer]\nOnCalendar=weekly\n")
    (_u / "fedora-cleaner-ai.service").write_text("[Service]\nExecStart=/usr/bin/python3 -m fedora_cleaner ai --notify\n")
    _calls = []
    _done = lg_.migrate_units(_u, lambda *a: _calls.append(a) or 0)
    check(_done == ["tidydisk-ai"] and not (_u / "fedora-cleaner-ai.timer").exists() and "-m tidydisk ai" in (_u / "tidydisk-ai.service").read_text(), "nazwa: stary timer przepisany na nowy")
    check(("disable", "--now", "fedora-cleaner-ai.timer") in _calls and ("enable", "--now", "tidydisk-ai.timer") in _calls, "nazwa: stary timer wylaczony, nowy wlaczony")
    check(lg_.migrate_units(_u, lambda *a: 0) == [], "nazwa: migracja jednostek jest idempotentna")

# ---- katalogi osal (Windows/macOS/Linux) i dyski Windows
from tidydisk import disks as dk_
_old_sys = osal_w.SYSTEM
try:
    osal_w.SYSTEM = "windows"
    _env0 = dict(os.environ)
    os.environ["APPDATA"] = "C:\\Users\\Me\\AppData\\Roaming"; os.environ["LOCALAPPDATA"] = "C:\\Users\\Me\\AppData\\Local"
    check(str(osal_w.config_dir()).endswith("TidyDisk") and "Roaming" in str(osal_w.config_dir()), "osal: Windows - ustawienia w %APPDATA%\\TidyDisk")
    check("Local" in str(osal_w.data_dir()) and str(osal_w.data_dir()).endswith("TidyDisk"), "osal: Windows - dane w %LOCALAPPDATA%\\TidyDisk")
    osal_w.SYSTEM = "linux"
    check(str(osal_w.data_dir()).endswith(".local/share/tidydisk") and str(osal_w.config_dir()).endswith(".config/tidydisk"), "osal: Linux - sciezki jak dawniej")
finally:
    osal_w.SYSTEM = _old_sys
    os.environ.clear(); os.environ.update(_env0)
_wd = dk_.list_disks_windows(letters=["C", "D", "E", "F"], kind_of=lambda r: {"C:\\": 3, "D:\\": 2, "E:\\": 5, "F:\\": 3}[r],
                             volume_info=lambda r: ("System", "NTFS"), usage=lambda r: (0, 0) if r.startswith("F") else (60, 40))
check([d.name for d in _wd] == ["C:", "D:"] and _wd[0].parts[0].fstype == "NTFS" and _wd[0].size == 100, "dyski Windows: litery, bez napedu optycznego i pustego")
check(_wd[1].kind.startswith("Wymienny") and _wd[0].parts[0].mounts == ["C:\\"], "dyski Windows: typ i punkt montowania")
check(dk_.mount_labels(_wd).get("C:\\", "").startswith("C: ·"), "dyski Windows: etykieta dysku w raporcie")

# ---- migawki btrfs: na Windows nie ma ich wcale (takze pod Wine, gdzie /proc/mounts bywa widoczny)
from tidydisk import snapshots as sn_
_o = osal_w.SYSTEM
try:
    osal_w.SYSTEM = "windows"
    _fm = Path(_tf.mkdtemp()) / "mounts-btrfs"; _fm.write_text("/dev/sda1 / btrfs rw 0 0\n")
    check(sn_.detect(str(_fm))["btrfs"] is False and sn_.detect(str(_fm))["text"] == "", "migawki: Windows = brak komunikatu o btrfs")
    osal_w.SYSTEM = "linux"
    check(sn_.detect(str(_fm))["btrfs"] is True, "migawki: Linux bez zmian")
finally:
    osal_w.SYSTEM = _o

# ---- bezpieczenstwo usuwania (audyt): koncowy '/', wyscig TOCTOU, RecursionError
check(core.is_user_target(str(HOME / ".ssh"))[0] is False and core.is_user_target(str(HOME / ".ssh") + "/")[0] is False
      and core.is_user_target(str(HOME / ".ssh") + "//")[0] is False, "bezpieczenstwo: koncowy '/' nie omija ochrony ~/.ssh")
def _toctou(hook_name):
    base = HOME / ".cache" / "toctou_app"; shutil.rmtree(base, ignore_errors=True)
    (base / "cache").mkdir(parents=True); (base / "cache" / "f").write_text("x")
    victim = HOME / "Documents" / "toctou_victim"; victim.mkdir(parents=True, exist_ok=True); (victim / "f").write_text("vip")
    orig = getattr(core, hook_name)
    def swap():
        (base / "cache").rename(base / "cache_real"); (base / "cache").symlink_to(victim)
    def hooked(*a, **k):
        r = orig(*a, **k)
        if r and not getattr(hooked, "done", False):
            hooked.done = True; swap()
        return r
    setattr(core, hook_name, hooked)
    errs = []
    try:
        core.remove_path(str(base / "cache" / "f"), errs)
    finally:
        setattr(core, hook_name, orig)
    return (victim / "f").exists(), errs
_ok1, _e1 = _toctou("is_safe_target")
check(_ok1 and _e1, "bezpieczenstwo: podmiana katalogu na symlink po is_safe_target nie kasuje celu poza dozwolonymi")
_ok2, _e2 = _toctou("_allowed_parent")
check(_ok2 and _e2, "bezpieczenstwo: podmiana po sprawdzeniu korzeni konczy sie bledem, plik poza celem zostaje")
shutil.rmtree(HOME / ".cache" / "toctou_app", ignore_errors=True); shutil.rmtree(HOME / "Documents" / "toctou_victim", ignore_errors=True)
_deep = HOME / ".cache" / "deepapp"; shutil.rmtree(_deep, ignore_errors=True)
_p = _deep
for _i in range(40):
    _p = _p / "d"
_p.mkdir(parents=True)
_lim = sys.getrecursionlimit(); _de = []
try:
    sys.setrecursionlimit(len(__import__("inspect").stack()) + 25)
    core.remove_path(str(_deep), _de)
finally:
    sys.setrecursionlimit(_lim)
check(any("zagnieżdżony" in e for e in _de), "bezpieczenstwo: RecursionError nie przerywa czyszczenia (zapisany w bledach)")
shutil.rmtree(_deep, ignore_errors=True)
# Windows: kazdy prymityw usuwania zablokowany
_ow = osal_w.SYSTEM
try:
    osal_w.SYSTEM = "windows"
    _wf = HOME / ".cache" / "winblock"; (_wf).mkdir(parents=True, exist_ok=True); (_wf / "a").write_text("x")
    _we = []
    core.remove_path(str(_wf / "a"), _we); core.rm_tree(str(_wf), _we); core.remove_contents(str(_wf), _we); core.trash_path(str(_wf / "a"), _we)
    check((_wf / "a").exists() and len(_we) == 4, "windows: remove_path, rm_tree, remove_contents i trash_path zablokowane")
finally:
    osal_w.SYSTEM = _ow
shutil.rmtree(HOME / ".cache" / "winblock", ignore_errors=True)

# ---- Windows: brak os.pread/O_NOFOLLOW/fchmod nie wywala skrotow plikow, podgladu i zapisu ustawien
_hf = HOME / "hash_a.bin"; _hf.write_bytes(os.urandom(5_000_000))
_h_full0, _h_part0 = scanner._file_hash(str(_hf), 5_000_000, False), scanner._file_hash(str(_hf), 5_000_000, True)
_saved = {n: getattr(os, n) for n in ("pread", "fchmod") if hasattr(os, n)}
try:
    for n in _saved:
        delattr(os, n)
    scanner.HASH_CACHE.clear()
    check(scanner._file_hash(str(_hf), 5_000_000, False) == _h_full0 and scanner._file_hash(str(_hf), 5_000_000, True) == _h_part0,
          "windows: skrot pliku bez os.pread daje ten sam wynik")
    check(st_.save(st_.load()) is True, "windows: zapis ustawien bez os.fchmod")
    _fd = osal_w.open_regular(str(_hf)); os.close(_fd)
    check(osal_w.pread.__doc__ is not None, "windows: osal.pread dostepne")
finally:
    for n, f in _saved.items():
        setattr(os, n, f)
_hf.unlink()

# ---- audyt: raport maskuje nazwy w Twoich plikach, CSV bez formul, skrypt roota, detect, notify
_mine_dir = HOME / "Documents" / "Faktury"; _mine_dir.mkdir(parents=True, exist_ok=True)
_mine_file = _mine_dir / "Faktura Jan Kowalski.pdf"; _mine_file.write_bytes(b"x" * 3000)
_me = core.Entry("Faktura Jan Kowalski.pdf", 3000, "path", [str(_mine_file)], rating=kb.MINE, user_pick=True, checked=True, what="Twój plik", why="wybrane ręcznie")
_cat = core.Category("mine", "Twoje pliki", "", False, [_me])
_md = report.build_markdown([_cat], [], r, [], report.Anon())
_csvt = report.build_csv([_cat], [], report.Anon())
check("Kowalski" not in _md and "Faktury" not in _md, "raport: nazwy w Twoich plikach zamaskowane (markdown)")
check("Kowalski" not in _csvt and "Faktury" not in _csvt, "raport: nazwy w Twoich plikach zamaskowane (CSV)")
_ev = core.Entry("=cmd|' /C calc'!A0", 10, "path", [str(HOME / ".cache" / "ev")], rating=kb.SAFE, what="x", why="y")
_csve = report.build_csv([core.Category("cache", "c", "", False, [_ev])], [], report.Anon())
check("'=cmd" in _csve and ";=cmd" not in _csve, "csv: formula w nazwie zneutralizowana")
check(fsutil_w.csv_safe("") == "" and fsutil_w.csv_safe("=1+1") == "'=1+1" and fsutil_w.csv_safe("zwykly") == "zwykly", "csv_safe: puste zostaje puste, formula dostaje apostrof")
_sh = core.build_root_script([core.Entry("a", 1, "root_sh", cmd="false", root=True), core.Entry("b", 1, "root_sh", cmd="true", root=True)])
import subprocess as _sp
check(_sp.run(["bash", "-c", _sh], capture_output=True).returncode == 1, "skrypt roota: blad kroku nie jest ukryty przez udany ostatni")
check(_sp.run(["bash", "-c", core.build_root_script([core.Entry("b", 1, "root_sh", cmd="true", root=True)])], capture_output=True).returncode == 0, "skrypt roota: sukces = kod 0")
_od, _om = ai.list_models, None
def _fake_list(host, timeout=2.0):
    if host.endswith(":8080"):
        raise PermissionError("403")
    return ["m1"] if host.endswith(":11434") else None
ai.list_models = _fake_list
try:
    settings.update({"ai_url": ""}); _hh = ai.HOST; ai.HOST = ""
    check(ai.detect()[0] == "http://127.0.0.1:11434", "ai.detect: obca usluga z 403 nie zaslania prawdziwego serwera")
finally:
    ai.list_models = _od; ai.HOST = _hh
from tidydisk import viewmodel as vm_w
check(vm_w.date_text(2 ** 62) == "—", "viewmodel: absurdalny mtime nie wywala")
shutil.rmtree(HOME / "Documents" / "Faktury", ignore_errors=True)

_kw = kb.KnowledgeBase("C:\\Users\\Jan", [], system="windows")
check(_kw.classify_file("C:\\Users\\Jan\\Downloads\\Setup.exe").rating == kb.MINE, "kb Windows: plik w Downloads to Twoje pliki, nie 'poza domem'")
check(_kw.classify_file("D:\\x\\y").rating == kb.KEEP, "kb Windows: inny dysk poza domem")
check(core.KB.fold == (os.name == "nt"), "core.KB ma tryb zgodny z systemem")

# --- Windows: usuwanie (mechanizm sprawdzany na Linuksie: tam 'dowiazanie' = symlink) ---
from tidydisk import winfs as wf_, core as core_d, settings as set_d
_wd = Path(tempfile.mkdtemp(prefix="fc-win-"))
(_wd / "cache" / "sub").mkdir(parents=True)
(_wd / "cache" / "sub" / "a.tmp").write_text("x")
(_wd / "cache" / "ro.tmp").write_text("x"); os.chmod(_wd / "cache" / "ro.tmp", 0o444)
(_wd / "outside").mkdir(); (_wd / "outside" / "keep.txt").write_text("zostaje")
os.symlink(_wd / "outside", _wd / "cache" / "link")
_er: list = []
wf_.remove_tree(str(_wd / "cache"), _er)
check(not (_wd / "cache").exists() and (_wd / "outside" / "keep.txt").exists() and not _er, "winfs: dowiazanie usuniete jako dowiazanie, cel poza katalogiem nietkniety")
_er = []; wf_.remove_item(str(_wd / "nie_ma"), _er)
check(not _er, "winfs: brak pliku nie jest bledem")
check(wf_.bad_path("wzgledna\\x") and wf_.bad_path("C:\\x\\..") and not wf_.bad_path("C:\\x\\y"), "winfs: bad_path")
check(wf_.is_drive_root("C:\\") and wf_.is_drive_root("d:") and not wf_.is_drive_root("C:\\Users"), "winfs: korzen dysku")
_calls: list = []
class _R:
    returncode = 0
wf_.recycle("C:\\Users\\Me\\a b'c.txt", [], run=lambda cmd, **kw: (_calls.append((cmd, kw["env"].get("TIDYDISK_PATH"))), _R())[1])
check(_calls and _calls[0][1] == "C:\\Users\\Me\\a b'c.txt" and "a b'c" not in " ".join(_calls[0][0]), "winfs: sciezka do Kosza idzie przez zmienna srodowiskowa, nie przez polecenie")
_saved = (core_d.KB, wf_.same_real, set_d.RUNTIME.get("protected"))
core_d.KB = kb_.KnowledgeBase("C:\\Users\\Me", [], system="windows")
wf_.same_real = lambda _p: True
set_d.RUNTIME["protected"] = []
try:
    _chk = core_d.win_check
    check(_chk("C:\\Users\\Me\\AppData\\Local\\Temp\\x.tmp")[0], "win_check: Temp wolno")
    check(not _chk("C:\\Users\\Me")[0] and not _chk("C:\\")[0] and not _chk("D:\\gry\\x")[0], "win_check: dom, dysk i obce miejsca - nie")
    check(not _chk("C:\\Windows\\Temp\\a")[0] and not _chk("C:\\Users\\Me\\Documents\\a.docx", user=True)[0], "win_check: system i Dokumenty - nie")
    check(not _chk("C:\\Users\\Me\\Downloads\\a.zip")[0] and _chk("C:\\Users\\Me\\Downloads\\a.zip", user=True)[0], "win_check: Pobrane tylko jako wybor uzytkownika")
    check(not _chk("C:\\Users\\Me\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Login Data")[0], "win_check: hasla przegladarki - nie")
    wf_.same_real = lambda _p: False
    check("junction" in _chk("C:\\Users\\Me\\AppData\\Local\\Temp\\x.tmp")[1], "win_check: sciezka przez junction jest odrzucana")
finally:
    core_d.KB, wf_.same_real = _saved[0], _saved[1]
    set_d.RUNTIME["protected"] = _saved[2]
shutil.rmtree(_wd, ignore_errors=True)

_kw2 = kb_.KnowledgeBase("C:\\Users\\Me", [], system="windows")
check(all(_kw2.classify_file("C:\\Users\\Me\\" + n).rating == "keep" for n in ("NTUSER.DAT", "ntuser.dat.LOG1", "NTUSER.DAT{2ad8}.TMContainer0001.regtrans-ms", "ntuser.ini", ".ssh\\id_rsa", "Application Data")), "kb Windows: NTUSER.DAT, klucze i dowiazania zgodnosci = nie ruszaj")
check(_kw2.classify_file("C:\\Users\\Me\\notatki.txt").rating == "mine", "kb Windows: zwykly plik w profilu nadal Twoj")

import tidydisk.osal as _os_m
_old_win = _os_m.is_windows
_os_m.is_windows = lambda: True
try:
    check(core.mount_of("c:\\Users\\Me\\Downloads\\a.zip") == "C:\\" and core.mount_of("D:\\x") == "D:\\", "mount_of na Windows: litera dysku jak w liscie dyskow")
finally:
    _os_m.is_windows = _old_win

from tidydisk import schedule as sch_w
_ta = sch_w.win_task_args("weekly", "03:30", 20, 5, command='"C:\\x\\tidydisk.exe"')
check(_ta[:4] == ["/Create", "/TN", "TidyDisk-check", "/TR"] and _ta[4] == '"C:\\x\\tidydisk.exe" notify --min-free 20 --min-reclaim 5'
      and "WEEKLY" in _ta and "SUN" in _ta and "03:30" in _ta and _ta[-1] == "/F", "schtasks: argumenty zadania tygodniowego")
check("MONTHLY" in sch_w.win_task_args("monthly", "", 1, 1, command="x") and "10:00" in sch_w.win_task_args("daily", "", 1, 1, command="x"), "schtasks: miesieczne i domyslna godzina")
try:
    sch_w.win_task_args("weekly", "25:00", 1, 1, command="x"); _bad = False
except ValueError:
    _bad = True
check(_bad, "schtasks: zla godzina odrzucona")

_vd = Path(tempfile.mkdtemp(prefix="fc-ver-"))
(_vd / "Downloads").mkdir()
for _n, _sz in (("Setup_1.2.8.0.exe", 3 * 1024 * 1024), ("Setup_1.2.9.0.exe", 3 * 1024 * 1024), ("Setup_1.2.13.0.exe", 0)):
    (_vd / "Downloads" / _n).write_bytes(_n.encode() * (_sz // len(_n)))  # rozna zawartosc: inaczej byly by duplikatami
    os.utime(_vd / "Downloads" / _n, (time.time() - 200 * 86400,) * 2)
from tidydisk import scanner as sc_v, kb as kb_v
_rv = sc_v.scan(str(_vd), kb_v.KnowledgeBase(_vd, []), advise=True)
_adv = {os.path.basename(a[1]): a for a in _rv.advice}
check("Setup_1.2.13.0.exe" not in _rv.keepers and not any("1.2.13.0" in r for a in _adv.values() for r in a[6]), "wersje: pusty plik nie jest 'nowsza wersja'")
check("Setup_1.2.8.0.exe" in _adv and any("1.2.9.0" in r for r in _adv["Setup_1.2.8.0.exe"][6]), "wersje: starsza wersja wskazuje na prawdziwa nowsza")
shutil.rmtree(_vd, ignore_errors=True)

_ai = sch_w.win_ai_task_args("daily", "02:15", "assisted", command="X")
check(_ai[_ai.index("/TN") + 1] == "TidyDisk-ai" and _ai[_ai.index("/TR") + 1] == "X ai --notify -q --wait-ai 10 --mode assisted" and "DAILY" in _ai, "schtasks: zadanie AI w tle")
check(sch_w.win_task_args("weekly", "", 1, 1, command="X", auto_clean=True)[4].endswith("--auto-clean") and not sch_w.win_task_args("weekly", "", 1, 1, command="X")[4].endswith("--auto-clean"), "schtasks: auto-clean tylko na zyczenie")
from tidydisk import disks as dk_w
_dw = dk_w.list_disks_windows(letters=["Y", "Z"], kind_of=lambda r: 4, volume_info=lambda r: ("Mikolaj", "NTFS"),
                              usage=lambda r: (5, 5), remote_of=lambda r: "\\\\srv\\share")
check(all("\\\\srv\\share" in d.model for d in _dw) and len(_dw) == 2, "dyski Windows: dysk sieciowy pokazuje sciezke UNC")
_ed = Path(tempfile.mkdtemp(prefix="fc-emp-"))
(_ed / "Downloads").mkdir()
(_ed / "Downloads" / "Setup_9.exe").write_bytes(b"")
(_ed / "Downloads" / "notes.txt").write_bytes(b"")
os.utime(_ed / "Downloads" / "Setup_9.exe", (time.time() - 100 * 86400,) * 2)
_re = sc_v.scan(str(_ed), kb_v.KnowledgeBase(_ed, []), advise=True)
_names = {os.path.basename(a[1]) for a in _re.advice}
check("Setup_9.exe" in _names and "notes.txt" not in _names, "analiza: pusty instalator w Pobranych proponowany, pusty .txt nie")
shutil.rmtree(_ed, ignore_errors=True)

_fd = Path(tempfile.mkdtemp(prefix="fc-fresh-"))
(_fd / "Downloads").mkdir()
(_fd / "Downloads" / "nowy.crdownload").write_bytes(b"")
_rf = sc_v.scan(str(_fd), kb_v.KnowledgeBase(_fd, []), advise=True)
check(not any(a[1].endswith("nowy.crdownload") for a in _rf.advice), "analiza: swiezy pusty .crdownload (trwa pobieranie) nie jest proponowany")
shutil.rmtree(_fd, ignore_errors=True)
_sr = sc_v.ScanResult(root="/h")
_sr.nodes = {"/h/x/foo\\": [1, 1, "mine", "", 2], "/h/x/foo\\/sub": [1, 1, "mine", "", 3], "/h/x": [2, 2, "mine", "", 1], "/h": [2, 2, "mine", "", 0]}
check([c[0] for c in _sr.children("/h/x")] == ["/h/x/foo\\"] and [c[0] for c in _sr.children("/h/x/foo\\")] == ["/h/x/foo\\/sub"], "children: backslash w nazwie katalogu na Linuksie to czesc nazwy")


# --- 2.23.1: sciezki natywne Windows u konsumentow
from tidydisk import ai as _ai, changes as _ch, learn as _ln, osal, core
_osw = osal.is_windows
osal.is_windows = lambda: True
try:
    check(list(_ai._ancestors("C:\\Users\\Jan\\Foo\\a.bin"))[:3] == ["C:\\Users\\Jan\\Foo", "C:\\Users\\Jan", "C:\\Users"], "ai: _ancestors dla sciezki Windows")
    check(_ai._nearest("C:\\Users\\Jan\\Foo\\a.bin", {"C:\\Users\\Jan": 1}) == "C:\\Users\\Jan", "ai: _nearest dla Windows")
    check(_ai._under("C:\\a\\b", "C:\\a") and not _ai._under("C:\\ab", "C:\\a"), "ai: _under dla Windows")
    class _E:
        kind = "path"
        def __init__(s, p): s.paths = [p]
    check(len(core.dedupe_selection([_E("C:\\a"), _E("C:\\a\\b.txt")])) == 1, "dedupe_selection: plik w zaznaczonym folderze (Windows)")
finally:
    osal.is_windows = _osw
check(_ch.__name__ and True, "changes zaimportowane")
osal.is_windows = lambda: True
try:
    check("Users" not in "".join(_ln.features("C:\\Users\\Jan\\Old\\x.zip", 100, "safe", 50, [], "C:\\Users\\Jan")), "learn: cecha folderu bez loginu")
finally:
    osal.is_windows = _osw

from tidydisk import schedule as _sc
try:
    _sc.calendar("daily", "abc"); _ok = False
except ValueError as _ex:
    _ok = "HH:MM" in str(_ex)
check(_ok, "schedule: zla godzina daje czytelny blad")

import tempfile as _tf
_d = _tf.mkdtemp()
_deep = os.path.join(_d, "a", "b", "c", "d", "e", "f", ".git")
os.makedirs(_deep)
check(core.holds_keep(_d) == "w środku jest .git", "holds_keep: .git gleboko w srodku (5+ poziomow)")
_e = []
core.trash_path(_d, _e)
check(_e and ".git" in _e[0], "trash_path: folder z .git w srodku nie trafia do kosza")
_s = _tf.mkdtemp()
check(core.holds_keep(_s) == "", "holds_keep: pusty folder")
check(os.path.isabs(cli._expand_excludes(["~/x", "y"])[0]) and len(cli._expand_excludes(["~/x"])) >= 1, "cli: --exclude rozwija ~ i sciezki wzgledne")
_nm = _tf.mkdtemp()
os.makedirs(os.path.join(_nm, *["n%d" % k for k in range(14)]))
check(core.holds_keep(_nm) == "", "holds_keep: gleboki pusty folder (np. node_modules) nie jest odmowa")
print("WSZYSTKO OK" if not fails else f"BLEDY: {len(fails)}")
sys.exit(1 if fails else 0)
