"""Baza wiedzy: co to za plik/katalog i czy wolno go usunac.

Modul uzywa wylacznie biblioteki standardowej i NIE importuje reszty pakietu -
jego zrodlo jest tez wysylane do procesu administratora (patrz scanner.py).

Oceny:
  safe    - bezpieczne: program odtworzy to sam, brak utraty danych
  review  - do przejrzenia: zwykle zbedne, ale decyzja nalezy do czlowieka
  keep    - nie ruszaj: system, konfiguracja, dane programow
  mine    - Twoje pliki: dokumenty, zdjecia, projekty - program ich nie usuwa
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path

SAFE, REVIEW, KEEP, MINE = "safe", "review", "keep", "mine"
RATINGS = (SAFE, REVIEW, KEEP, MINE)
RATING_LABEL = {
    SAFE: "Bezpieczne",
    REVIEW: "Do przejrzenia",
    KEEP: "Nie ruszaj",
    MINE: "Twoje pliki",
}


@dataclass(frozen=True)
class Verdict:
    rating: str
    title: str
    what: str  # co to jest
    why: str  # dlaczego taka ocena
    rule: str = ""  # wzorzec, ktory zadzialal (do raportu)


# (wzorzec, ocena, tytul, co to jest, dlaczego)
# ~ = katalog domowy. "*" nie przekracza "/", "**" przekracza.
_RULES: list = [
    # ---- cache uzytkownika
    ("~/.cache/thumbnails", SAFE, "Miniatury plików",
     "Podglądy obrazów i filmów generowane przez menedżer plików.",
     "Odtworzą się automatycznie przy następnym otwarciu folderu."),
    ("~/.cache/pip", SAFE, "Cache pip",
     "Pobrane wcześniej pakiety Pythona.",
     "Pip pobierze je ponownie, gdy będą potrzebne."),
    ("~/.cache/mesa_shader_cache", SAFE, "Cache shaderów Mesa",
     "Skompilowane shadery karty graficznej.",
     "Przebudują się przy kolejnym uruchomieniu gry lub programu 3D (chwilowe przycięcia)."),
    ("~/.cache/nvidia", SAFE, "Cache shaderów NVIDIA",
     "Skompilowane shadery sterownika NVIDIA.",
     "Sterownik zbuduje je od nowa."),
    ("~/.cache/fontconfig", SAFE, "Cache czcionek",
     "Indeks zainstalowanych czcionek.",
     "Odbuduje się automatycznie."),
    ("~/.cache/mozilla", SAFE, "Cache Firefoksa",
     "Zapisane strony i obrazy przyspieszające przeglądanie.",
     "Nie zawiera haseł ani zakładek (te są w ~/.mozilla). Zamknij Firefoksa przed czyszczeniem."),
    ("~/.cache/google-chrome", SAFE, "Cache Google Chrome",
     "Zapisane strony i obrazy przyspieszające przeglądanie.",
     "Hasła i zakładki są w ~/.config. Zamknij Chrome przed czyszczeniem."),
    ("~/.cache/chromium", SAFE, "Cache Chromium",
     "Zapisane strony i obrazy przyspieszające przeglądanie.",
     "Profil jest w ~/.config. Zamknij przeglądarkę przed czyszczeniem."),
    ("~/.cache/BraveSoftware", SAFE, "Cache Brave",
     "Zapisane strony i obrazy przyspieszające przeglądanie.",
     "Profil jest w ~/.config. Zamknij przeglądarkę przed czyszczeniem."),
    ("~/.cache/uv", SAFE, "Cache uv", "Pobrane pakiety Pythona (menedżer uv).", "uv pobierze je ponownie, gdy będą potrzebne."),
    ("~/.cache/ccache", SAFE, "Cache ccache", "Wyniki kompilacji C/C++.", "Kompilator zbuduje je od nowa (dłuższa pierwsza kompilacja)."),
    ("~/.cache/vscode-cpptools", SAFE, "Cache IntelliSense (VS Code)", "Baza podpowiedzi dla C/C++.", "VS Code odbuduje ją przy otwarciu projektu."),
    ("~/.cache/Unity", SAFE, "Cache Unity", "Pobrane pakiety i cache edytora Unity.", "Unity pobierze je ponownie."),
    ("~/.cache/unity3d", SAFE, "Cache Unity", "Cache edytora Unity.", "Unity odbuduje go."),
    ("~/.cache/gnome-software", SAFE, "Cache GNOME Software", "Dane sklepu z aplikacjami.", "Odtworzą się."),
    ("~/.cache/appstream", SAFE, "Cache AppStream", "Metadane aplikacji.", "Odtworzą się przy odświeżeniu sklepu."),
    ("~/.cache/discover", SAFE, "Cache Discover", "Dane sklepu z aplikacjami KDE.", "Odtworzą się."),
    ("~/.cache/libdnf5", SAFE, "Cache DNF użytkownika", "Metadane repozytoriów.", "dnf pobierze je ponownie."),
    ("**/steamapps/shadercache", REVIEW, "Cache shaderów Steam", "Skompilowane shadery gier Steam.",
     "Steam zbuduje je od nowa przy następnym uruchomieniu gry (chwilowe przycięcia)."),
    ("**/steamapps/downloading", REVIEW, "Niedokończone pobieranie Steam", "Pliki gier pobierane teraz lub przerwane.",
     "Steam dokończy lub pobierze je ponownie."),
    ("**/steamapps/temp", REVIEW, "Pliki tymczasowe Steam", "Tymczasowe pliki aktualizacji gier.",
     "Steam odtworzy je przy aktualizacji."),
    ("~/.cache/winetricks", SAFE, "Cache winetricks", "Pobrane instalatory bibliotek Windows.", "Winetricks pobierze je ponownie."),
    ("~/.cache/opera-gx", SAFE, "Cache Opera GX", "Zapisane strony i obrazy przyspieszające przeglądanie.", "Profil jest w ~/.config. Zamknij przeglądarkę przed czyszczeniem."),
    ("~/.cache/Espressif", REVIEW, "Cache Espressif (ESP-IDF)", "Pobrane narzędzia i komponenty ESP32.", "Można pobrać ponownie, ale zajmie to czas - nie zaznaczam sam."),
    ("~/.cache/yarn", SAFE, "Cache Yarn",
     "Pobrane pakiety JavaScript.", "Yarn pobierze je ponownie."),
    ("~/.cache/go-build", SAFE, "Cache kompilacji Go",
     "Pośrednie wyniki kompilacji.", "Kompilator zbuduje je od nowa (dłuższa pierwsza kompilacja)."),
    ("~/.cache/huggingface", REVIEW, "Modele Hugging Face",
     "Pobrane modele AI i zbiory danych.",
     "Można pobrać ponownie, ale to często wiele GB i długi download."),
    ("~/.cache/torch", REVIEW, "Modele PyTorch",
     "Pobrane wagi modeli.", "Pobiorą się ponownie, ale mogą być duże."),
    ("~/.cache/pre-commit", SAFE, "Cache pre-commit", "Pobrane środowiska narzędzi pre-commit.", "pre-commit zbuduje je od nowa."),
    ("~/.cache/pnpm", SAFE, "Cache pnpm", "Pobrane pakiety JavaScript (pnpm).", "pnpm pobierze je ponownie."),
    ("~/.cache/bottles", SAFE, "Cache Bottles", "Dane tymczasowe programu Bottles (bez butelek z programami).", "Bottles odtworzy je sam."),
    ("~/.cache/zig", SAFE, "Cache kompilatora Zig", "Pośrednie wyniki kompilacji.", "Kompilator zbuduje je od nowa."),
    ("~/.cache/bazel", REVIEW, "Cache Bazel", "Wyniki kompilacji i pobrane zależności.", "Bazel zbuduje je od nowa, ale pierwsza kompilacja potrwa długo."),
    ("~/.cargo/registry/cache", REVIEW, "Cache pakietów Rust (cargo)", "Pobrane paczki .crate.", "Cargo pobierze je ponownie przy następnej kompilacji."),
    ("~/.gradle/caches", REVIEW, "Cache Gradle", "Pobrane zależności i wyniki budowania.", "Gradle pobierze je ponownie, ale to długi download."),
    ("~/.m2/repository", REVIEW, "Repozytorium Maven (lokalne)", "Pobrane zależności projektów Java.", "Maven pobierze je ponownie; zainstalowane lokalnie własne artefakty by zniknęły."),
    ("~/.platformio/.cache", REVIEW, "Cache PlatformIO", "Pobrane pliki pomocnicze PlatformIO.", "PlatformIO pobierze je ponownie."),
    ("~/.arduino15/staging", REVIEW, "Pobrane pakiety Arduino", "Archiwa płytek i bibliotek po instalacji.", "Można pobrać ponownie z menedżera płytek."),
    ("~/.cache/baloo", SAFE, "Indeks wyszukiwania (Baloo)",
     "Indeks plików do szybkiego wyszukiwania w KDE.", "Zostanie zbudowany od nowa."),
    ("~/.cache/rclone", REVIEW, "Cache rclone", "Pamięć podręczna rclone; przy trybie vfs może trzymać jeszcze niewysłane zmiany.",
     "Sprawdź, czy rclone nie ma niewysłanych plików, zanim to usuniesz."),
    ("~/.cache/JetBrains", REVIEW, "Cache JetBrains", "Indeksy IDE; w środku bywa lokalna historia plików (LocalHistory).",
     "Lokalnej historii nie odtworzysz - przejrzyj zawartość."),
    ("~/.cache/pypoetry", REVIEW, "Cache Poetry", "Pobrane pakiety i środowiska wirtualne Poetry.", "Środowiska odtworzysz, ale to potrwa."),
    ("~/.cache/borg", REVIEW, "Cache BorgBackup", "Indeks kopii zapasowych Borg.", "Odbudowa indeksu bywa bardzo wolna."),
    ("~/.cache/keepassxc", REVIEW, "Cache KeePassXC", "Pliki pomocnicze menedżera haseł.", "Lepiej nie ruszać bez potrzeby."),
    ("~/.cache/evolution", REVIEW, "Cache Evolution", "Lokalna kopia poczty i kalendarza Evolution.", "Może zawierać niezsynchronizowane dane."),
    ("~/.cache/*", SAFE, "Cache aplikacji",
     "Dane tymczasowe zapisane przez program, żeby działał szybciej.",
     "To z definicji kopia, którą program odtworzy. Zamknij program przed czyszczeniem."),
    ("~/.cache", SAFE, "Katalog cache użytkownika",
     "Wspólne miejsce na dane tymczasowe programów.", "Programy odtwarzają jego zawartość."),
    # ---- kosz, flatpak
    ("~/.local/share/Trash", SAFE, "Kosz",
     "Pliki, które usunąłeś do kosza.",
     "Usunięcie jest nieodwracalne - sprawdź, czy niczego w koszu nie potrzebujesz."),
    ("~/.var/app/*/cache", SAFE, "Cache aplikacji Flatpak",
     "Dane tymczasowe programu zainstalowanego z Flatpaka.", "Program odtworzy je sam."),
    ("~/.var/app/*/config", KEEP, "Ustawienia aplikacji Flatpak",
     "Konfiguracja programu.", "Usunięcie resetuje ustawienia programu."),
    ("~/.var/app/*/data", KEEP, "Dane aplikacji Flatpak",
     "Dane programu (np. zapisy, bazy).", "Mogą zawierać Twoje dane - nie usuwaj."),
    ("~/.var/app", KEEP, "Dane aplikacji Flatpak",
     "Katalogi robocze programów z Flatpaka.", "Poza podkatalogiem cache zawierają dane i ustawienia."),
    ("/var/lib/flatpak", KEEP, "Programy Flatpak (system)",
     "Zainstalowane aplikacje i runtime'y Flatpak.",
     "Nieużywane runtime'y usuwa polecenie flatpak, nie ręczne kasowanie."),
    ("~/.local/share/flatpak", KEEP, "Programy Flatpak (użytkownik)",
     "Zainstalowane aplikacje i runtime'y Flatpak.",
     "Nieużywane runtime'y usuwa polecenie flatpak, nie ręczne kasowanie."),
    # ---- dane programow w ~/.local i ~/.config
    ("~/.local/share/baloo", REVIEW, "Indeks wyszukiwania (Baloo)",
     "Baza indeksu plików KDE.", "Można skasować (odbuduje się), ale indeksowanie potrwa i obciąży dysk."),
    ("~/.local/share/recently-used.xbel", REVIEW, "Lista ostatnich plików",
     "Historia otwieranych dokumentów.", "Mały plik; kasowanie czyści tylko historię."),
    ("~/.local/share/Steam", REVIEW, "Steam",
     "Biblioteka gier i dane Steam.", "Zawiera zainstalowane gry i zapisy - usuwaj gry z poziomu Steam."),
    ("~/.local/share/containers", REVIEW, "Obrazy kontenerów (Podman)",
     "Obrazy i wolumeny kontenerów.", "Usuwaj poleceniem podman system prune, nie ręcznie."),
    ("~/.local/share/*", KEEP, "Dane aplikacji",
     "Dane programów użytkownika (bazy, zapisy, profile).", "Mogą zawierać dane, których program nie odtworzy."),
    ("~/.local/share", KEEP, "Dane aplikacji",
     "Dane programów użytkownika.", "Mogą zawierać dane, których program nie odtworzy."),
    ("~/.local/state", KEEP, "Stan aplikacji", "Historia i stan programów.", "Program może ich potrzebować."),
    ("~/.config", KEEP, "Ustawienia programów",
     "Konfiguracja aplikacji i pulpitu.", "Usunięcie resetuje ustawienia, a czasem profile i hasła przeglądarek."),
    ("~/.mozilla", KEEP, "Profil Firefoksa",
     "Zakładki, hasła, historia, rozszerzenia.", "To Twoje dane - nie usuwaj."),
    ("~/.thunderbird", KEEP, "Profil Thunderbirda", "Poczta i konta.", "To Twoje dane - nie usuwaj."),
    ("~/.ssh", KEEP, "Klucze SSH", "Klucze prywatne i lista znanych serwerów.", "Utrata kluczy odcina dostęp do serwerów."),
    ("~/.gnupg", KEEP, "Klucze GPG", "Klucze szyfrujące i podpisujące.", "Utrata kluczy bywa nieodwracalna."),
    ("~/.pki", KEEP, "Certyfikaty", "Certyfikaty użytkownika.", "Mogą być potrzebne przeglądarkom."),
    ("~/.var", KEEP, "Dane aplikacji Flatpak", "Katalogi robocze programów z Flatpaka.", "Zawierają dane i ustawienia programów."),
    ("~/.local", KEEP, "Dane użytkownika (.local)", "Programy, dane i stan aplikacji użytkownika.", "Mogą zawierać dane, których program nie odtworzy."),
    ("~/.*", KEEP, "Ukryte dane programu", "Ukryty katalog lub plik z ustawieniami/danymi programu.", "Usunięcie zwykle resetuje program, a czasem kasuje dane."),
    ("~/.bashrc", KEEP, "Ustawienia powłoki", "Konfiguracja terminala.", "Zmienia działanie terminala."),
    # ---- narzedzia deweloperskie
    ("~/.cargo/registry", REVIEW, "Cache Cargo (Rust)",
     "Pobrane źródła i paczki bibliotek Rusta.", "Cargo pobierze je ponownie."),
    ("~/.rustup", REVIEW, "Toolchainy Rust", "Kompilatory Rusta.", "Można doinstalować ponownie, ale zajmie to czas."),
    ("~/.npm", REVIEW, "Cache npm", "Pobrane pakiety JavaScript.", "npm pobierze je ponownie."),
    ("~/.gradle/caches", REVIEW, "Cache Gradle", "Pobrane zależności projektów Java.", "Gradle pobierze je ponownie."),
    ("~/.m2/repository", REVIEW, "Repozytorium Maven", "Pobrane biblioteki Java.", "Maven pobierze je ponownie."),
    ("~/.conda", REVIEW, "Środowiska Conda", "Pakiety i środowiska Pythona.", "Środowiska można odtworzyć z pliku, jeśli go masz."),
    ("~/.local/pipx", REVIEW, "Programy pipx", "Programy Pythona w osobnych środowiskach.", "Można zainstalować ponownie."),
    ("**/saves", KEEP, "Zapisy gier i światy", "Zapisane gry, światy Minecrafta i podobne dane.", "Tego nie da się odtworzyć - nie proponuję usunięcia."),
    ("**/node_modules", REVIEW, "node_modules", "Biblioteki projektu JavaScript.", "Odtworzysz poleceniem npm install, o ile projekt ma package.json."),
    ("**/__pycache__", SAFE, "Skompilowany Python", "Pliki .pyc przyspieszające start programów.", "Python utworzy je ponownie."),
    ("**/Code Cache", SAFE, "Cache kodu przeglądarki/Electrona", "Skompilowany kod JavaScript stron i aplikacji (Chrome, VS Code, Discord, Slack...).",
     "Program zbuduje go od nowa (chwilowo wolniejszy start). Zamknij program przed czyszczeniem."),
    ("**/GPUCache", SAFE, "Cache GPU przeglądarki/Electrona", "Skompilowane shadery i dane GPU.", "Program zbuduje je od nowa."),
    ("**/GrShaderCache", SAFE, "Cache shaderów Skia", "Skompilowane shadery grafiki Chrome/Electrona.", "Program zbuduje je od nowa."),
    ("**/DawnCache", SAFE, "Cache shaderów Dawn (WebGPU)", "Skompilowane shadery WebGPU Chrome/Electrona.", "Program zbuduje je od nowa."),
    ("**/.venv", REVIEW, "Środowisko wirtualne Pythona", "Biblioteki projektu.", "Odtworzysz z requirements, jeśli projekt je ma."),
    ("**/.Trash-*", SAFE, "Kosz na dysku", "Kosz użytkownika na dodatkowym dysku.", "Pliki w koszu - usunięcie jest nieodwracalne, sprawdź je najpierw."),
    ("**/$RECYCLE.BIN", REVIEW, "Kosz Windows", "Kosz systemu Windows na tej partycji.", "Należy do Windows - usuwaj z poziomu Windows."),
    ("**/System Volume Information", KEEP, "Dane systemu Windows", "Punkty przywracania i indeksy Windows.", "Należą do Windows."),
    ("**/lost+found", KEEP, "lost+found", "Katalog odzyskiwania systemu plików.", "Nie ruszaj."),
    ("**/.git", KEEP, "Historia Git", "Pełna historia wersji projektu.", "Usunięcie kasuje historię projektu."),
    # ---- foldery uzytkownika
    ("~/Downloads", REVIEW, "Pobrane pliki", "Wszystko, co pobrałeś z internetu.",
     "Często leżą tam instalatory i archiwa, które już nie są potrzebne - ale to Twoje pliki, przejrzyj je."),
    ("~/Pobrane", REVIEW, "Pobrane pliki", "Wszystko, co pobrałeś z internetu.",
     "Często leżą tam instalatory i archiwa, które już nie są potrzebne - ale to Twoje pliki, przejrzyj je."),
    ("~/Documents", MINE, "Dokumenty", "Twoje dokumenty.", "Program nigdy ich nie usuwa."),
    ("~/Dokumenty", MINE, "Dokumenty", "Twoje dokumenty.", "Program nigdy ich nie usuwa."),
    ("~/Pictures", MINE, "Obrazy", "Twoje zdjęcia i grafiki.", "Program nigdy ich nie usuwa."),
    ("~/Obrazy", MINE, "Obrazy", "Twoje zdjęcia i grafiki.", "Program nigdy ich nie usuwa."),
    ("~/Videos", MINE, "Wideo", "Twoje filmy.", "Program nigdy ich nie usuwa."),
    ("~/Wideo", MINE, "Wideo", "Twoje filmy.", "Program nigdy ich nie usuwa."),
    ("~/Music", MINE, "Muzyka", "Twoja muzyka.", "Program nigdy jej nie usuwa."),
    ("~/Muzyka", MINE, "Muzyka", "Twoja muzyka.", "Program nigdy jej nie usuwa."),
    ("~/Desktop", MINE, "Pulpit", "Pliki leżące na pulpicie.", "Program nigdy ich nie usuwa."),
    ("~/Pulpit", MINE, "Pulpit", "Pliki leżące na pulpicie.", "Program nigdy ich nie usuwa."),
    # ---- system
    ("/var/cache/libdnf5", SAFE, "Cache DNF", "Metadane repozytoriów i pobrane pakiety.", "dnf pobierze je ponownie przy następnej aktualizacji."),
    ("/var/cache/dnf", SAFE, "Cache DNF", "Metadane repozytoriów i pobrane pakiety.", "dnf pobierze je ponownie."),
    ("/var/cache/PackageKit", SAFE, "Cache PackageKit", "Dane menedżera oprogramowania.", "Odtworzą się."),
    ("/var/cache/apt", SAFE, "Cache APT", "Pobrane pakiety .deb i metadane.", "apt pobierze je ponownie przy następnej aktualizacji."),
    ("/var/cache", REVIEW, "Cache systemowy", "Dane tymczasowe usług systemowych.", "Zwykle odtwarzalne, ale każda usługa jest inna."),
    ("/var/lib/systemd/coredump", SAFE, "Zrzuty pamięci po awariach",
     "Obrazy pamięci programów, które się zawiesiły.", "Służą tylko do diagnozy awarii; stare zrzuty są zbędne."),
    ("/var/log/journal", REVIEW, "Dziennik systemd", "Zapis zdarzeń systemu.",
     "Przycinanie starych wpisów jest bezpieczne (journalctl --vacuum), ale tracisz historię diagnostyczną."),
    ("/var/log", KEEP, "Logi systemu", "Zapisy działania usług.", "Zarchiwizowane (*.gz, *.old) są zbędne - czyści je program; reszta jest w użyciu."),
    ("/var/tmp", REVIEW, "Tymczasowe pliki (trwałe)", "Pliki tymczasowe zachowywane między restartami.", "Programy mogą jeszcze z nich korzystać."),
    ("/tmp", REVIEW, "Tymczasowe pliki", "Pliki tymczasowe bieżącej sesji.", "Używane przez działające programy."),
    ("/var/lib/libvirt/images", MINE, "Dyski maszyn wirtualnych", "Obrazy dysków VM.", "To dane Twoich maszyn."),
    ("/var/lib/docker", REVIEW, "Dane Dockera", "Obrazy i kontenery.", "Czyść poleceniem docker system prune."),
    ("/var/lib/containers", REVIEW, "Dane Podmana", "Obrazy i kontenery.", "Czyść poleceniem podman system prune."),
    ("/var/lib/rpm", KEEP, "Baza RPM", "Lista zainstalowanych pakietów.", "Uszkodzenie psuje menedżer pakietów."),
    ("/var/lib/dnf", KEEP, "Historia DNF", "Historia instalacji.", "Potrzebna do cofania zmian."),
    ("/var/lib", KEEP, "Dane usług", "Stan usług systemowych.", "Zmiana może zepsuć usługę."),
    ("/var", KEEP, "Dane zmienne systemu", "Logi, cache, bazy usług.", "Zarządza tym system."),
    ("/boot", KEEP, "Rozruch", "Jądra i bootloader.", "Błąd = system się nie uruchomi. Stare jądra usuwaj przez dnf."),
    ("/usr", KEEP, "Programy systemu", "Zainstalowane programy i biblioteki.", "Zarządza tym dnf."),
    ("/etc", KEEP, "Konfiguracja systemu", "Ustawienia systemu.", "Błąd może uniemożliwić start."),
    ("/opt", KEEP, "Programy dodatkowe", "Programy spoza repozytoriów.", "Zarządzane przez ich instalator."),
    ("/root", KEEP, "Katalog administratora", "Dane konta root.", "Nie ruszaj."),
    ("/srv", KEEP, "Dane usług", "Dane serwowane przez usługi.", "Mogą być czyjeś."),
    ("/bin", KEEP, "System", "Podstawowe programy.", "Zarządza tym system."),
    ("/sbin", KEEP, "System", "Podstawowe programy.", "Zarządza tym system."),
    ("/lib", KEEP, "System", "Biblioteki systemu.", "Zarządza tym system."),
    ("/lib64", KEEP, "System", "Biblioteki systemu.", "Zarządza tym system."),
    ("/proc", KEEP, "Pseudo-system plików", "Wirtualny - nie zajmuje miejsca.", "Nie jest prawdziwymi plikami."),
    ("/sys", KEEP, "Pseudo-system plików", "Wirtualny - nie zajmuje miejsca.", "Nie jest prawdziwymi plikami."),
    ("/dev", KEEP, "Urządzenia", "Wirtualny katalog urządzeń.", "Nie jest prawdziwymi plikami."),
    ("/run", KEEP, "Stan uruchomieniowy", "Wirtualny, znika po restarcie.", "Nie ruszaj."),
]

# Rozszerzenia: (tytul, opis, ocena-podpowiedz). Podpowiedz "review" wplywa na ocene
# tylko w lokalizacjach "do przejrzenia"/"Twoje pliki".
_EXT: dict = {}


def _ext(names, title, what, rating, category):
    for n in names.split():
        _EXT[n] = (title, what, rating, category)


_ext("iso img", "Obraz dysku", "Obraz płyty lub dysku (np. instalator systemu).", REVIEW, "Archiwa i obrazy")
_ext("rpm", "Pakiet RPM", "Instalator programu dla Fedory.", REVIEW, "Archiwa i obrazy")
_ext("deb", "Pakiet DEB", "Instalator programu dla Debiana/Ubuntu - na Fedorze bezużyteczny.", REVIEW, "Archiwa i obrazy")
_ext("appimage", "AppImage", "Program w jednym pliku.", REVIEW, "Programy")
_ext("run sh", "Skrypt/instalator", "Skrypt lub samorozpakowujący się instalator.", REVIEW, "Programy")
_ext("zip 7z rar tar gz tgz xz bz2 zst", "Archiwum", "Spakowane pliki.", REVIEW, "Archiwa i obrazy")
_ext("tmp temp bak old orig swp part crdownload", "Plik tymczasowy/kopia", "Pozostałość po pracy programu lub niedokończone pobieranie.", REVIEW, "Tymczasowe")
_ext("log", "Log", "Zapis działania programu.", REVIEW, "Tymczasowe")
_ext("core", "Zrzut pamięci", "Obraz pamięci zawieszonego programu.", REVIEW, "Tymczasowe")
_ext("mp4 mkv avi mov webm wmv flv m4v", "Film", "Plik wideo.", MINE, "Wideo")
_ext("mp3 flac ogg opus wav m4a aac wma", "Muzyka", "Plik audio.", MINE, "Muzyka")
_ext("jpg jpeg png gif webp bmp tif tiff heic svg raw cr2 nef arw dng", "Obraz", "Zdjęcie lub grafika.", MINE, "Obrazy")
_ext("pdf doc docx odt rtf txt md epub mobi djvu", "Dokument", "Dokument tekstowy.", MINE, "Dokumenty")
_ext("xls xlsx ods csv ppt pptx odp", "Arkusz/prezentacja", "Arkusz kalkulacyjny lub prezentacja.", MINE, "Dokumenty")
_ext("py js ts c cpp h rs go java php rb", "Kod źródłowy", "Plik z kodem programu.", MINE, "Kod i dane")
_ext("json xml yaml yml sql db sqlite", "Dane", "Plik z danymi lub baza.", MINE, "Kod i dane")
_ext("qcow2 vdi vmdk vhd", "Dysk maszyny wirtualnej", "Obraz dysku VM.", MINE, "Archiwa i obrazy")
_ext("ttf otf woff woff2", "Czcionka", "Plik czcionki.", MINE, "Inne")

OTHER_CATEGORY = "Inne"
CATEGORIES = ("Wideo", "Muzyka", "Obrazy", "Dokumenty", "Archiwa i obrazy",
              "Programy", "Kod i dane", "Tymczasowe", "Inne")


@lru_cache(maxsize=8192)
def ext_of(name: str) -> str:
    base = name.lower()
    if base.endswith((".tar.gz", ".tar.xz", ".tar.bz2", ".tar.zst")):
        return base.rsplit(".", 2)[-1]
    if "." not in base.strip("."):
        return ""
    return base.rsplit(".", 1)[-1]


def file_category(name: str) -> str:
    e = _EXT.get(ext_of(name))
    return e[3] if e else OTHER_CATEGORY


def _glob_to_regex(pattern: str) -> re.Pattern:
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if pattern[i:i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("".join(out) + r"\Z", re.S)


# katalogi projektow: ogolne reguly po nazwie, ktore nie moga zdjac ochrony ze strefy "Nie ruszaj" (np. ~/.vscode/.../node_modules)
_PROJECT_DIRS = ("**/node_modules", "**/__pycache__", "**/.venv")


class KnowledgeBase:
    """Wyszukiwanie oceny: najblizszy przodek ze zdefiniowana regula wygrywa."""

    def __init__(self, home, data_mounts=(), system: str = "linux") -> None:
        self.fold = system == "windows"  # Windows: sciezki porownujemy po normalizacji (male litery, '/')
        if self.fold:
            from . import kb_windows as _w
            self._norm = _w.norm
            rules = _w.RULES
        else:
            self._norm = str
            rules = _RULES
        home = self._norm(home) if self.fold else home
        self.home = str(home).rstrip("/") or "/"
        self.data_mounts = [self._norm(m) if self.fold else str(m).rstrip("/") for m in data_mounts if str(m).rstrip("/")]
        self.literal: dict = {}  # sciezka -> regula
        self.by_name: dict = {}  # "**/nazwa" -> regula
        self.patterns: list = []  # (regex, regula, staly_fragment)
        for rule in rules:
            pat = rule[0]
            if pat.startswith("~"):
                pat = self.home + pat[1:]
            if pat.startswith("**/") and not any(ch in pat[3:] for ch in "*?/"):
                self.by_name.setdefault(pat[3:], rule)
            elif not any(ch in pat for ch in "*?"):
                self.literal.setdefault(pat, rule)
            else:
                # najdluzszy staly fragment wzorca: tani test 'in' odsiewa wiekszosc sciezek przed regexem
                lit = max(re.split(r"[*?]+", pat), key=len)
                self.patterns.append((_glob_to_regex(pat), rule, lit))

    def match_here(self, path: str):
        """Regula dopasowana dokladnie do tej sciezki (bez przodkow) albo None."""
        if self.fold:
            path = self._norm(path)
        r = self.literal.get(path)
        if r is not None:
            return r
        r = self.by_name.get(path.rsplit("/", 1)[-1])
        if r is not None:
            return r
        for rx, rule, lit in self.patterns:
            if lit in path and rx.match(path):
                return rule
        return None

    @staticmethod
    def _verdict(rule) -> Verdict:
        return Verdict(rule[1], rule[2], rule[3], rule[4], rule[0])

    def classify_dir(self, path: str, inherited: Verdict | None) -> Verdict:
        """Ocena katalogu przy przejsciu w dol drzewa (dziedziczenie po rodzicu)."""
        rule = self.match_here(path)
        if rule is not None:
            if inherited is not None and inherited.rating == KEEP and rule[1] != KEEP and rule[0] in _PROJECT_DIRS:
                return inherited  # ogolna regula po nazwie (node_modules, .venv...) nie zdejmuje ochrony ze strefy 'Nie ruszaj'
            return self._verdict(rule)
        if inherited is not None:
            return inherited
        return self.default(path)

    def default(self, path: str) -> Verdict:
        if self.fold:
            path = self._norm(path)
        for m in self.data_mounts:
            if path == m or path.startswith(m + "/"):
                return Verdict(MINE, "Pliki na dysku danych", "Pliki na dodatkowym dysku lub partycji.",
                               "Dysk danych - zakładam, że to Twoje pliki; program ich nie usuwa.",
                               "(domyślna: dysk danych)")
        if path == self.home or path.startswith(self.home + "/"):
            return Verdict(MINE, "Twoje pliki", "Pliki w katalogu domowym.",
                           "Nie rozpoznaję tego miejsca - zakładam, że to Twoje dane.", "(domyślna: dom)")
        return Verdict(KEEP, "Plik poza katalogiem domowym", "Nierozpoznane miejsce w systemie.",
                       "Nie rozpoznaję tego miejsca - nie usuwam.", "(domyślna: poza domem)")

    def classify(self, path: str) -> Verdict:
        """Ocena dowolnej sciezki: najblizszy przodek (lacznie z nia sama) z regula."""
        p = self._norm(path) if self.fold else (path.rstrip("/") or "/")
        cur = p
        generic = None  # najblizsza ogolna regula po nazwie - ustepuje ochronie ze strefy 'Nie ruszaj' wyzej
        while True:
            rule = self.match_here(cur)
            if rule is not None:
                if rule[0] in _PROJECT_DIRS and rule[1] != KEEP:
                    generic = generic or rule
                else:
                    return self._verdict(rule) if (generic is None or rule[1] == KEEP) else self._verdict(generic)
            if cur == self.home or cur == "/" or "/" not in cur:
                break
            cur = cur.rsplit("/", 1)[0] or "/"
        if generic is not None:
            return self._verdict(generic)
        return self.default(p)

    def classify_file(self, path: str, dir_verdict: Verdict | None = None) -> Verdict:
        """Ocena pliku = ocena lokalizacji, z podpowiedzia po rozszerzeniu."""
        base = dir_verdict if dir_verdict is not None else self.classify(path)
        e = _EXT.get(ext_of(os.path.basename(path)))
        if e is None:
            return base
        title, what, hint, _cat = e
        if base.rating in (REVIEW, MINE):
            rating = REVIEW if hint == REVIEW else base.rating
            why = base.why
            if hint == REVIEW and base.rating == MINE:
                why = ("Typ pliku zwykle jest zbędny po użyciu, ale leży w Twoich plikach - "
                       "zdecyduj sam.")
            return Verdict(rating, title, what, why, base.rule + " + rozszerzenie")
        return Verdict(base.rating, title, what, base.why, base.rule)


_default_kb: KnowledgeBase | None = None
_default_home = ""


def default_kb() -> KnowledgeBase:
    global _default_kb, _default_home
    home = str(Path.home())
    if _default_kb is None or _default_home != home:
        _default_kb = KnowledgeBase(Path.home(), system="windows" if os.name == "nt" else "linux")
        _default_home = home
    return _default_kb


def classify(path: str) -> Verdict:
    return default_kb().classify(path)


def rating_and_category(name: str, base: str) -> tuple:
    """(file_rating(name, base), file_category(name)) with a single extension lookup."""
    e = _EXT.get(ext_of(name))
    if e is None:
        return base, OTHER_CATEGORY
    return (REVIEW if base in (REVIEW, MINE) and e[2] == REVIEW else base), e[3]


def file_rating(name: str, base: str) -> str:
    """Szybka ocena pliku wg oceny katalogu i rozszerzenia."""
    if base in (REVIEW, MINE):
        e = _EXT.get(ext_of(name))
        if e is not None and e[2] == REVIEW:
            return REVIEW
    return base


# ------------------------------------------------------------------ powody propozycji --
# Powod to stabilny KOD + tekst z tego jedynego katalogu ({} = parametry). Reszta programu (reguly, uczenie)
# rozpoznaje powody po kodzie, wiec zmiana lub tlumaczenie tekstow zmienia tylko ten katalog.
REASONS = {
    "loc_safe": "miejsce z danymi, które program odtworzy sam",
    "loc_review": "miejsce, w którym zwykle leżą zbędne rzeczy",
    "fresh": "zmieniony niedawno ({} dni temu)",
    "stale_days": "nieużywany od {} dni",
    "stale_months": "nieużywany od ok. {} miesięcy",
    "stale_year": "nieużywany od ponad roku ({} miesięcy)",
    "huge": "bardzo duży ({})",
    "big": "duży ({})",
    "partial": "niedokończone pobieranie",
    "empty": "pusty plik (0 B) - najpewniej nieudane pobranie",
    "coredump": "zrzut pamięci po awarii",
    "installer": "instalator - po instalacji zwykle zbędny",
    "tempbak": "plik tymczasowy lub kopia zapasowa",
    "log": "log",
    "archive": "archiwum",
    "extracted": "rozpakowane obok jako folder «{}»",
    "recreatable": "można go odtworzyć (narzędzie zbuduje go ponownie)",
    "oldver": "starsza wersja - nowsza «{}» leży obok",
    "copyname": "numerowana kopia pliku «{}» leżącego obok",
    "project": "folder wygenerowany w projekcie {} - odtworzy się ze źródeł",
    "dup": "identyczna kopia pliku «{}» z {}",
    "rpm_installed": "pakiet «{}» jest już zainstalowany",
}


_REASON_PREFIX = {c: t.split("{")[0] for c, t in REASONS.items()}


def reason(code: str, *args) -> str:
    return REASONS[code].format(*args)


def has_reason(reasons, code: str) -> bool:
    """Czy na liscie powodow jest powod o danym kodzie (dopasowanie po stalym poczatku tekstu z katalogu)."""
    prefix = _REASON_PREFIX[code]
    return any(r.startswith(prefix) for r in reasons)
