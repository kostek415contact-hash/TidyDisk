"""Baza wiedzy dla Windows: znane, bezpieczne do czyszczenia miejsca (tylko DOKLADNE sciezki, bez zgadywania).

Format jak w kb._RULES; "~" = profil uzytkownika (C:/Users/nazwa), sciezki zapisane z "/" i malymi literami
(NTFS nie rozroznia wielkosci liter; dopasowanie odbywa sie po normalizacji). Nigdy nie ruszamy: Windows, Program Files,
ProgramData, WinSxS, hiberfil/pagefile, Prefetch, profili przegladarek (haslo, ciasteczka, historia) ani Dokumentow."""
from __future__ import annotations

SAFE, REVIEW, KEEP = "safe", "review", "keep"

_L = "~/appdata/local"
_R = "~/appdata/roaming"

RULES: list = [
    # ---- tymczasowe i miniatury
    (f"{_L}/temp", SAFE, "Pliki tymczasowe użytkownika", "Dane tymczasowe programów.",
     "Programy je odtworzą; pliki w użyciu zostaną pominięte. Zamknij instalatory przed czyszczeniem."),
    (f"{_L}/microsoft/windows/explorer", REVIEW, "Miniatury i ikony Eksploratora", "Pliki thumbcache_*.db i iconcache_*.db.",
     "Eksplorator odbuduje je sam, ale folder zawiera też inne pliki - czyść tylko pliki thumbcache i iconcache."),
    (f"{_L}/crashdumps", SAFE, "Zrzuty awarii programów", "Obrazy pamięci programów, które się zawiesiły.",
     "Potrzebne tylko do diagnozy błędu."),
    # ---- przegladarki: tylko dokladne podkatalogi cache, nigdy caly profil
    (f"{_L}/microsoft/edge/user data/*/cache", SAFE, "Cache Edge", "Zapisane strony i obrazy.",
     "Hasła i ciasteczka są poza tym folderem. Zamknij przeglądarkę przed czyszczeniem."),
    (f"{_L}/microsoft/edge/user data/*/code cache", SAFE, "Cache kodu Edge", "Skompilowany kod stron.", "Edge odbuduje go sam."),
    (f"{_L}/microsoft/edge/user data/*/gpucache", SAFE, "Cache GPU Edge", "Shadery strony.", "Edge odbuduje go sam."),
    (f"{_L}/google/chrome/user data/*/cache", SAFE, "Cache Chrome", "Zapisane strony i obrazy.",
     "Hasła i ciasteczka są poza tym folderem. Zamknij przeglądarkę przed czyszczeniem."),
    (f"{_L}/google/chrome/user data/*/code cache", SAFE, "Cache kodu Chrome", "Skompilowany kod stron.", "Chrome odbuduje go sam."),
    (f"{_L}/google/chrome/user data/*/gpucache", SAFE, "Cache GPU Chrome", "Shadery strony.", "Chrome odbuduje go sam."),
    (f"{_L}/mozilla/firefox/profiles/*/cache2", SAFE, "Cache Firefox", "Zapisane strony i obrazy.",
     "Profil (hasła, zakładki) jest w AppData/Roaming i zostaje nietknięty."),
    (f"{_L}/bravesoftware/brave-browser/user data/*/cache", SAFE, "Cache Brave", "Zapisane strony i obrazy.",
     "Hasła i ciasteczka są poza tym folderem."),
    # ---- shadery
    (f"{_L}/d3dscache", SAFE, "Cache shaderów DirectX", "Skompilowane shadery.", "System odbuduje je przy uruchomieniu gier."),
    (f"{_L}/nvidia/dxcache", SAFE, "Cache shaderów NVIDIA (DX)", "Skompilowane shadery.", "Sterownik odbuduje je sam."),
    (f"{_L}/nvidia/glcache", SAFE, "Cache shaderów NVIDIA (GL)", "Skompilowane shadery.", "Sterownik odbuduje je sam."),
    (f"{_L}/amd/dxcache", SAFE, "Cache shaderów AMD", "Skompilowane shadery.", "Sterownik odbuduje je sam."),
    # ---- narzedzia programistyczne
    (f"{_L}/npm-cache", SAFE, "Cache npm", "Pobrane pakiety JavaScript.", "npm pobierze je ponownie."),
    (f"{_L}/pip/cache", SAFE, "Cache pip", "Pobrane pakiety Pythona.", "Pip pobierze je ponownie."),
    (f"{_L}/nuget/v3-cache", SAFE, "Cache NuGet", "Pobrane metadane i paczki.", "NuGet pobierze je ponownie."),
    ("~/.nuget/packages", REVIEW, "Pakiety NuGet", "Pobrane zależności projektów .NET.", "Zostaną pobrane przy kolejnej kompilacji."),
    ("~/.cargo/registry/cache", REVIEW, "Cache pakietów Rust (cargo)", "Pobrane paczki .crate.", "Cargo pobierze je ponownie."),
    ("~/.gradle/caches", REVIEW, "Cache Gradle", "Pobrane zależności i wyniki budowania.", "Gradle pobierze je ponownie."),
    ("~/.m2/repository", REVIEW, "Repozytorium Maven (lokalne)", "Pobrane zależności projektów Java.", "Maven pobierze je ponownie."),
    (f"{_L}/yarn/cache", SAFE, "Cache Yarn", "Pobrane pakiety JavaScript.", "Yarn pobierze je ponownie."),
    (f"{_L}/pnpm/store", SAFE, "Magazyn pnpm", "Pobrane pakiety JavaScript.", "pnpm pobierze je ponownie."),
    (f"{_R}/code/cache", SAFE, "Cache VS Code", "Dane tymczasowe edytora.", "Edytor odbuduje je sam (nie dotyka ustawień ani kopii zapasowych)."),
    (f"{_R}/code/cacheddata", SAFE, "Skompilowany kod VS Code", "Pamięć podręczna.", "Edytor odbuduje ją sam."),
    (f"{_R}/code/gpucache", SAFE, "Cache GPU VS Code", "Shadery.", "Edytor odbuduje je sam."),
    (f"{_R}/discord/cache", SAFE, "Cache Discord", "Zapisane obrazy i pliki.", "Program pobierze je ponownie."),
    # ---- nigdy
    (_L, KEEP, "Dane lokalne programów", "Katalog AppData/Local.", "Ustawienia i dane programów - nie usuwam."),
    (_R, KEEP, "Dane programów (Roaming)", "Katalog AppData/Roaming.", "Ustawienia, profile i hasła programów - nie usuwam."),
    ("~/appdata", KEEP, "Dane programów", "Katalog AppData.", "Ustawienia i dane programów - nie usuwam."),
    ("~/onedrive", KEEP, "OneDrive", "Pliki synchronizowane z chmurą.", "Usunięcie pliku usuwa też kopię w chmurze - nie ruszam."),
    ("~/documents", KEEP, "Dokumenty", "Twoje dokumenty.", "Nie usuwam."),
    # ---- pliki systemowe profilu leza w katalogu domowym obok Twoich plikow: nigdy nie sa do usuniecia
    ("~/ntuser.dat*", KEEP, "Rejestr użytkownika", "Plik rejestru profilu Windows (NTUSER.DAT i jego dzienniki).",
     "Usunięcie uszkodzi profil użytkownika - nie ruszam."),
    ("~/ntuser.ini", KEEP, "Rejestr użytkownika", "Ustawienia profilu Windows.", "Nie usuwam."),
    ("~/.ssh", KEEP, "Klucze SSH", "Klucze i konfiguracja SSH.", "Nie usuwam."),
    ("~/.gnupg", KEEP, "Klucze GPG", "Klucze GPG.", "Nie usuwam."),
    ("~/application data", KEEP, "Dowiązanie do AppData", "Stare dowiązanie zgodności do AppData.", "Nie usuwam."),
    ("~/local settings", KEEP, "Dowiązanie do AppData", "Stare dowiązanie zgodności do AppData.", "Nie usuwam."),
    ("~/my documents", KEEP, "Dowiązanie do Dokumentów", "Stare dowiązanie zgodności.", "Nie usuwam."),
    ("~/start menu", KEEP, "Menu Start", "Skróty menu Start.", "Nie usuwam."),
    ("~/cookies", KEEP, "Dowiązanie zgodności", "Stare dowiązanie zgodności.", "Nie usuwam."),
    ("~/nethood", KEEP, "Dowiązanie zgodności", "Stare dowiązanie zgodności.", "Nie usuwam."),
    ("~/printhood", KEEP, "Dowiązanie zgodności", "Stare dowiązanie zgodności.", "Nie usuwam."),
    ("~/sendto", KEEP, "Menu Wyślij do", "Skróty menu Wyślij do.", "Nie usuwam."),
    ("~/templates", KEEP, "Szablony Windows", "Dowiązanie zgodności do szablonów.", "Nie usuwam."),
]

# katalogi systemowe, ktorych program nigdy nie rusza (porownanie po normalizacji, bez wielkosci liter)
PROTECTED = ("c:/windows", "c:/program files", "c:/program files (x86)", "c:/programdata", "c:/system volume information",
             "c:/$recycle.bin", "c:/recovery", "c:/boot")
NEVER_FILES = ("hiberfil.sys", "pagefile.sys", "swapfile.sys")


def norm(path: str) -> str:
    """Postac porownawcza sciezki Windows: '/', male litery, bez prefiksu \\\\?\\ i koncowego '/'."""
    p = str(path).replace("\\", "/")
    if p.startswith("//?/UNC/") or p.startswith("//?/unc/"):
        p = "//" + p[8:]
    elif p.startswith("//?/"):
        p = p[4:]
    p = p.lower()
    while "//" in p[2:]:
        p = p[:2] + p[2:].replace("//", "/")
    return p.rstrip("/") or "/"


def is_protected(path: str) -> bool:
    p = norm(path)
    if p.rsplit("/", 1)[-1] in NEVER_FILES:
        return True
    return any(p == d or p.startswith(d + "/") for d in PROTECTED) or ".." in p.split("/")
