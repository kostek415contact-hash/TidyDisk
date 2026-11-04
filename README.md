# TidyDisk

> Dawniej *Fedora Cleaner*. Po aktualizacji ustawienia i dane przenoszą się same; stare polecenie `fedora-cleaner` zastąpiło `tidydisk`.

Graficzny program do sprzątania dysku na Fedorze (KDE/GNOME). Przeszukuje wszystkie pliki,
wyjaśnia, czym są, pokazuje podział na dyski i partycje, a przed usunięciem **mówi, co usunie,
co zostawi i dlaczego**.

## Instalacja

    unzip tidydisk.zip && cd tidydisk
    ./install.sh          # do ~/.local, bez roota; zapyta o python3-pyqt6, jeśli go brakuje
    ./uninstall.sh        # usunięcie
    ./install.sh --admin  # tylko skaner administratora (sudo), np. po aktualizacji programu

Program pojawi się w menu aplikacji („TidyDisk”) i pod komendą `tidydisk`.
Ikona jest wpisana w `.desktop` pełną ścieżką, więc działa od razu (bez odświeżania cache).

## Strony programu

- **Dyski i partycje** – dyski (NVMe/SSD/HDD/USB), pasek podziału na partycje, zajęte miejsce.
- **Foldery** – drzewo największych katalogów z oceną i wyjaśnieniem. Przycisk „Skanuj cały dysk
  (administrator)” przeszukuje też to, czego zwykły użytkownik nie widzi (jedno okno z hasłem;
  skaner tylko czyta). Skaner działa z kopii należącej do roota (`/usr/local/lib/tidydisk/admin_scan.py`,
  instaluje ją `install.sh` po zapytaniu): kod z Twojego katalogu nigdy nie dostaje uprawnień roota. Program
  odmówi skanu, gdy kopii nie ma, nie należy do roota, jest zapisywalna dla innych albo ma inną wersję.
- **Pliki** – największe pliki, typy plików, filtr po ocenie, wyjaśnienie „co to jest / dlaczego”.
- **Mapa dysku** – treemapa: kafle proporcjonalne do rozmiaru folderów, kolor = ocena (zielony bezpieczne, bursztynowy
  do sprawdzenia, niebieski moje pliki, czerwony nie ruszaj), 🤖 = wybrane przez AI. Klik wchodzi w folder, „↑ Wyżej”
  wraca. Dane z ostatniej analizy albo skanu folderów.
- **Sprzątanie** – trzy zakładki, a po prawej **panel szczegółów** wybranej pozycji (rozmiar, pewność, co to jest,
  dlaczego, werdykt AI, przyciski „Zaznacz do usunięcia” / „Zostaw”):
  - **Polecane** – algorytm przeszukuje wszystkie pliki (dom i dyski danych) i sam proponuje, co usunąć, z procentem
    pewności i powodami (patrz niżej). Pewne propozycje są zaznaczone, resztę oceniasz sam.
  - **Wszystkie pliki** – każdy dysk do rozwijania; zaznaczasz dowolne foldery i pliki.
  - **System i pakiety** – cache, kosz, Flatpak, stare jądra, nieużywane pakiety.

  Lista „Dysk” filtruje po dysku. Wszystkie przełączniki (kosz, symulacja, dziennik, AI) są w **Ustawieniach**,
  a wszystko inne na stronie **Ustawienia** (patrz niżej).
  Twoje pliki, które sam zaznaczysz, domyślnie trafiają do kosza (`gio trash`) i wymagają potwierdzenia.

## Jak działa wykrywanie (zakładka Polecane)

Każdy plik dostaje punkty 0–100 za kilka sygnałów; powody widać przy pozycji:

| Sygnał | Punkty |
|---|---|
| miejsce: dane odtwarzalne (cache) / zwykle zbędne (Pobrane) / Twoje | 55 / 25 / 0 |
| identyczna kopia innego pliku (porównanie pełnego skrótu blake2b) | +50 |
| stary instalator (iso, rpm, AppImage …) / niedokończone pobranie | +30 / +35 |
| archiwum rozpakowane obok jako folder | +30 (+15 za archiwum) |
| pakiet .rpm już zainstalowany w systemie | +40 |
| folder do odtworzenia (node_modules, .venv, __pycache__ …) | +25 |
| wiek bez użycia: 60–180 dni / pół roku–rok / ponad rok | +10 / +18 / +25 |
| świeży plik (poniżej 14 dni) | −35 |
| rozmiar ≥ 100 MB / 1 GB / 10 GB | +8 / +12 / +15 |

Propozycja pojawia się od 45 pkt, **zaznaczona sama dopiero od 75 pkt** i nigdy dla „Twoich plików”. „Twoje pliki”
(Dokumenty, Zdjęcia …) są proponowane wyłącznie przy konkretnym sygnale (duplikat, instalator …) – sam wiek nie
wystarcza. Pliki „Nie ruszaj” nie dostają punktów nigdy. Wszystko, co algorytm zaznaczy, i tak przechodzi
okno potwierdzenia.

### Zabezpieczenia algorytmu

- Nigdy nie proponuje plików z drzew zarządzanych przez inne programy: warstwy kontenerów (`containers/storage`),
  prefiksy Wine/Proton (`compatdata`, `compatibilitytools.d`), `Library/PackageCache` Unity, `.cargo`, `node_modules`,
  `.git`, środowiska Pythona, Flatpak. Identyczne pliki są tam celowe.
- Pliki kodu i bibliotek (`.dll`, `.so`, `.py`, `.json` …) nie są uznawane za duplikaty do usunięcia.
- Punkty za „instalator” i „archiwum” dostają tylko pliki w Pobranych/Pulpicie (do 3 poziomów w głąb).

## Uczenie się z Twoich decyzji

Przy każdym prawdziwym czyszczeniu program zapamiętuje, co zaznaczyłeś, a czego nie ruszyłeś mimo wysokiej pewności.
Mały model (regresja logistyczna, czysty Python) przesuwa pewność o maks. ±30 pkt, a „Twoje pliki” nigdy w górę.
Dane: `~/.local/share/tidydisk/learn.json`, tylko lokalnie. Prawy przycisk → „Nie proponuj tego więcej”.
Ustawienia → Ochrona → „Zapomnij moje wcześniejsze decyzje” (albo tylko jedną cechę z listy „Czego się nauczyłem”).

## AI przegląda wszystko w etapach (lejek)

Model nie dostaje milionów plików naraz. Zamiast tego wszystko przechodzi przez etapy od najtańszych do najostrzejszych,
a z każdym etapem pozycji jest mniej:

1. **Reguły** (bez AI) – wiedza o systemie, drzewa zarządzane i „Nie ruszaj” odpadają od razu.
2. **Statystyki** (bez AI) – rozmiar, wiek, typ, duplikaty: lista kandydatów i dużych folderów.
3. **AI: foldery** (tanie) – jedna linijka na folder; model wybiera: *zostaw* (Twoja praca), *zajrzyj* albo *cały
   zbędny* (np. `Library` projektu Unity). Pliki w folderach „zostaw” są odznaczane, nawet gdy algorytm był pewny.
4. **AI: pliki** – model ocenia pliki z folderów „zajrzyj” i największe pozycje.
5. **AI: weryfikacja** (najostrzejsza) – drugi przebieg w roli recenzenta, który szuka powodu, by NIE usuwać
   (znaczniki projektu, sąsiednie pliki źródłowe, kopie zapasowe). Zaznaczone zostaje tylko to, co zatwierdzi.
   Cały folder „zbędny” trafia na listę dopiero po tej weryfikacji.

**Zaglądanie do zawartości.** W etapach 4 i 5 model dostaje nie tylko nazwę, ale też krótki podgląd tego, co jest w środku:
typ po nagłówku pliku (a nie po rozszerzeniu), początek tekstu, spis plików w archiwum zip/tar, nazwę pakietu `.rpm`,
etykietę obrazu ISO. Dzięki temu ocenia „co to naprawdę jest”. Podgląd trafia wyłącznie do lokalnego modelu
(`127.0.0.1`). Pliki o nazwach wskazujących na dane poufne (klucze, hasła, portfele: `id_rsa`, `.pem`, `.kdbx`,
`password`, `token` …) nie są w ogóle otwierane. Wyłączysz to w Ustawienia → AI → „AI zagląda do zawartości plików”.

Przy każdej pozycji widać uzasadnienie (🤖), a pasek statusu pokazuje bieżący etap. Przycisk **🤖 Oceń przez AI**
uruchamia przegląd ręcznie, **Przerwij ocenę AI** go zatrzymuje; automatyczny start wyłączysz w Ustawienia → AI.

## Czyszczenie pozycja po pozycji

Po kliknięciu **Wyczyść** program pyta o **każdą pozycję osobno** (największe najpierw): nazwa, ścieżka, rozmiar, ocena,
uzasadnienie AI i podgląd zawartości. Przyciski: **Usuń**, **Zostaw** (domyślny), **Zostaw resztę**, **Usuń resztę**,
**Przerwij** (nic nie zostaje usunięte). Zamknięcie okna też przerywa. Wyłączysz to w Ustawienia → „Pytaj o każdą pozycję
po kolei” (wróci jedno okno potwierdzenia dla całości).

Ustawienia: strona **Ustawienia → AI** . Dla Unsloth Studio:
1. uruchom model, np. `unsloth run --model unsloth/gemma-4-26B-A4B-it-GGUF:UD-Q4_K_XL`,
2. w Studio: Settings → API → utwórz klucz (zaczyna się od `sk-unsloth-`),
3. wpisz klucz w Ustawienia → AI i kliknij „Zapisz i sprawdź połączenie z AI” (adres wykrywany sam: porty 8888, 8080, 11434, 1234, 8000; inny w polu „adres”).
Klucz zapisuje się w `~/.config/tidydisk/settings.json` (prawa 0600, tylko Ty; stary `ai.json` jest wczytywany automatycznie); możesz go też podać zmienną
`FC_AI_KEY`. Działa też z `llama-server`, Ollamą i LM Studio.

Bezpieczeństwo: model dostaje tylko metadane (ścieżka, rozmiar, wiek, nazwy plików obok), nigdy zawartość, i łączy się
tylko z `127.0.0.1`. Może wyłącznie **zaznaczyć pole wyboru** - pliki „Nie ruszaj”, katalogi systemowe i `.ssh` są
odrzucane niezależnie od jego odpowiedzi, a przed usunięciem zawsze jest okno potwierdzenia. Twoja ręczna zmiana
zaznaczenia ma pierwszeństwo przed modelem. Pliki z „Twoich plików” zaznaczone przez AI trafiają do kosza.
Pojedynczą pozycję możesz też zapytać przyciskiem **🤖 Zapytaj AI**.

Adres AI jest sprawdzany ściśle (http/https, host 127.0.0.1 / localhost / ::1, bez `użytkownik@`); zapytania idą bez proxy
ze środowiska i bez przekierowań, a obcy adres z pliku ustawień lub `FC_AI_URL` jest ignorowany. Import ustawień nie
podmienia adresu ani klucza AI. Usuwanie folderów działa na deskryptorach (nie idzie za symlinkami, nie wchodzi w
punkty montowania), a ścieżki względne i kończące się na `..` są odrzucane.

## Ustawienia

Strona **Ustawienia** (menu boczne) ma siedem zakładek; **Zapisz** działa od razu, bez restartu (zmiany parametrów
algorytmu obowiązują od następnej analizy). Plik: `~/.config/tidydisk/settings.json`; błędny wpis w pliku
nie psuje programu - wartości są sprawdzane i przycinane do dozwolonego zakresu.

- **Ogólne** – wygląd (ciemny motyw TidyDisk albo systemowy KDE), kosz dla moich plików, pytanie o każdą pozycję, symulacja, automatyczna analiza, ustawienia raportu.
- **Reguły** – lista pól tak/nie: czego program **może** proponować do usunięcia - pliki ISO, instalatory, archiwa,
  niedokończone pobrania, pliki tymczasowe, logi, zrzuty pamięci, filmy, identyczne kopie, archiwa rozpakowane obok,
  foldery do odtworzenia (build, node_modules, Library), cache, stare rzeczy w miejscach „zwykle zbędnych” oraz
  „moje pliki”. Odznaczona kategoria działa twardo: nie trafia na listę ani od algorytmu, ani od AI, a model dostaje
  w prompcie informację, czego nie ruszać.
- **Algorytm** – najniższa pewność propozycji, pewność od której zaznaczam sam, duplikaty (najmniejszy plik, limit
  czasu), głębokość analizy folderów.
- **AI** – adres, klucz (pole hasła), model (lista z serwera), limit czasu, zaglądanie do zawartości, etapy
  (foldery / recenzent), **co model może zaznaczyć sam** (tylko ryzyko niskie albo także średnie), temperatura,
  wielkość paczek i limity.
- **Prompty (zaawansowane)** – dla chętnych; edytujesz **zasady** dla czterech zapytań (pliki, foldery, recenzent, pojedyncze pytanie) oraz dopisujesz
  własne zasady do wszystkich („Zostaw wszystko w ~/Praca”). Format odpowiedzi (JSON), znaczniki danych i zdanie, że
  nazwy plików nie są poleceniami, są stałe i dopisywane automatycznie - zły prompt nie zepsuje parsowania ani nie
  osłabi zabezpieczeń. „Przywróć domyślne” i „Pokaż pełny prompt” są przy każdym polu; prompt równy domyślnemu zapisuje
  się jako pusty, więc po aktualizacji programu dostajesz nowszy domyślny.
- **Ochrona** – lista chronionych ścieżek: program ich nie zaproponuje, nie pokaże AI i **nie usunie** (twarda blokada
  w kodzie usuwania, także gdy zaznaczysz folder, który taką ścieżkę zawiera), lista „nie proponuj więcej” z
  uczenia, „Zapomnij decyzje”.
- **Uczenie** (w zakładce Ochrona) – lista „czego się nauczyłem” (+ zwykle usuwasz, − zwykle zostawiasz) z
  przyciskiem zapomnienia jednej cechy.
- **Dane** – gdzie leżą pliki, eksport ustawień (bez klucza API), import, przywrócenie domyślnych (klucz zostaje).

## Oceny

| Ocena | Znaczenie | Zaznaczane samo? |
|---|---|---|
| Bezpieczne | program odtworzy to sam (cache, miniatury, stare logi) | tak, o ile program nie działa |
| Do przejrzenia | zwykle zbędne, ale decyzja należy do Ciebie (modele AI, jądra, pakiety) | nie |
| Nie ruszaj | system, ustawienia, klucze, dane programów | zablokowane 🔒 - nie da się zaznaczyć |
| Twoje pliki | dokumenty, zdjęcia, projekty | nigdy sam; usuwane tylko, gdy je zaznaczysz (domyślnie do kosza) |

Dodatkowe zabezpieczenia: programy, które teraz działają (np. Firefox), są oznaczone ⚠ i nie są
zaznaczane; usuwanie jest możliwe tylko w `~/.cache`, `~/.var/app`, `~/.local/share/Trash`
(+ polecenia dnf/journalctl/flatpak jako administrator); dowiązania symboliczne nie są
śledzone; opcja „Symulacja” pokazuje w dzienniku, co by się stało.

## Raport do sprawdzenia

Przycisk **Raport ▾** (strona Sprzątanie): zapis do `.md`, tabela `.csv` albo kopia do schowka.
Raport zawiera trzy listy – **USUNĘ**, **ZOSTAWIĘ** (z powodem), **CHRONIONE** – oraz, jeśli był skan,
podział wg oceny i typu plików oraz największe pliki. Domyślnie ścieżki są zanonimizowane
(`~` zamiast `/home/nazwa`), a nazwy plików w „Twoich plikach” zamaskowane. Zawartość plików
nigdy nie trafia do raportu.

## Prywatność

- AI działa **wyłącznie lokalnie** (Unsloth Studio pod 127.0.0.1 / localhost); program odmawia innych adresów.
- Do modelu trafiają: ścieżki (domyślnie z `~` zamiast nazwy użytkownika), rozmiary, daty i - jeśli włączone
  „Zaglądaj do zawartości plików” - krótki początek plików tekstowych. Nic nie opuszcza komputera.
- Dane wstawiane do zapytań są owinięte w losowe znaczniki, a prompt mówi, że nazwy plików nie są poleceniami.
- Klucz API leży w `settings.json` (prawa 0600), nie trafia do raportu, eksportu ani argumentów terminala.
- Pamięć ocen AI: `~/.local/share/tidydisk/aicache.json` (0600) - ścieżki, rozmiary i werdykty; wyłączysz
  ustawieniem `ai_cache_days = 0`, usuniesz plikiem.
- Program niczego nie wysyła do sieci poza zapytaniami do lokalnego serwera AI.

## Tabela ustawień

Plik `~/.config/tidydisk/settings.json`; poza tym `rule_*` (przełączniki z zakładki Reguły), `prompt_*`
(zaawansowane), `ai_key` i `protected_paths` (lista).

| Klucz | Opis | Domyślnie | Zakres |
|---|---|---|---|
| `trash_mine` | Moje pliki do kosza | tak |  |
| `review_each` | Pytaj o każdą pozycję po kolei | tak |  |
| `review_safe_together` | Bezpieczne pozycje w jednym oknie (przy pytaniu po kolei) | tak |  |
| `dry_run` | Tryb symulacji | nie |  |
| `anonymize` | Raport: anonimizuj nazwę użytkownika | tak |  |
| `show_private_names` | Raport: pokaż nazwy w moich plikach | nie |  |
| `show_log` | Pokaż dziennik | nie |  |
| `search_mode` | Dokładność wyszukiwania | assisted |  |
| `language` | Język (część napisów) | auto |  |
| `theme` | Wygląd (`fedora`, `modern`, `modern-light`, `system`) | fedora |  |
| `auto_analysis` | Analizuj automatycznie po skanie | tak |  |
| `min_score` | Najniższa pewność propozycji (%) | 45 | 20–90 |
| `auto_score` | Pewność, od której zaznaczam sam (%) | 75 | 50–99 |
| `dup_min_mb` | Duplikaty: najmniejszy plik (MB) | 2 | 1–1024 |
| `dup_budget_s` | Duplikaty: limit czasu (s) | 45 | 5–600 |
| `analysis_depth` | Głębokość analizy folderów | 3 | 1–6 |
| `scan_parallel` | Miejsca skanowane naraz | 1 | 1–4 |
| `ai_url` | Adres serwera | (puste) |  |
| `ai_model` | Model | (puste) |  |
| `ai_timeout_s` | Limit czasu zapytania (s) | 600 | 30–3600 |
| `ai_auto` | Oceniaj automatycznie po analizie | tak |  |
| `ai_inspect` | Zaglądaj do zawartości plików | tak |  |
| `tray` | Praca w tle po zamknięciu okna | tak |  |
| `ai_cache_days` | Pamiętaj oceny AI (dni) | 30 | 0–365 |
| `ai_parallel` | Zapytań AI naraz (foldery) | 2 | 1–8 |
| `ai_skip_inside` | Pomijaj wnętrza folderów uznanych za „cały zbędny” | tak |  |
| `ai_mine` | AI może zaznaczać „Twoje pliki” | tak |  |
| `ai_stage_folders` | Etap: ocena folderów | tak |  |
| `ai_stage_verify` | Etap: recenzent (weryfikacja) | tak |  |
| `ai_risk` | Co model może zaznaczyć sam | niskie |  |
| `ai_temperature` | Temperatura | 0.1 | 0.0–1.0 |
| `ai_batch_files` | Pliki w jednym zapytaniu | 8 | 2–30 |
| `ai_verify_batch` | Pozycje w jednym zapytaniu recenzenta | 1 | 1–8 |
| `ai_batch_folders` | Foldery w jednym zapytaniu | 25 | 5–60 |
| `ai_pool_limit` | Ile pozycji ocenia AI | 200 | 20–1000 |
| `ai_folder_min_mb` | Foldery: najmniejszy rozmiar (MB) | 50 | 1–10240 |
| `ai_folder_limit` | Foldery: ile ocenia AI | 300 | 20–1500 |
| `protected_paths` |  | [] |  |

Historia zmian: `CHANGELOG.md`.

## Inne systemy i formaty pakietów (w budowie)

- **.rpm** (Fedora): `packaging/tidydisk.spec`. **.deb** (Debian, Ubuntu, Mint): `bash packaging/build-deb.sh` - instaluje program i skaner; czyszczenie cache APT działa, a funkcje oparte na `dnf`/`rpm` (jądra, niepotrzebne pakiety) tylko na Fedorze (na Debianie nie są proponowane). **.sh**: `install.sh`.
- **Windows (.exe)**: skan i raport z rozpoznawaniem znanych miejsc (Temp, cache przeglądarek, shadery, narzędzia programistyczne) - **tylko odczyt, niczego nie usuwa** (usuwanie zablokowane w kodzie do czasu testów na prawdziwym Windows 11). Budowa: `packaging/windows/build-exe.ps1` (PyInstaller; CI zapisuje `tidydisk.exe` jako artefakt). Użycie: `tidydisk.exe scan` / `status` / `report`. Okno (PyQt6) na Windows jeszcze nie jest sprawdzone.

### Sprawdzenie wersji Windows bez Windowsa

1. **Wine** (najszybciej, na Fedorze): `sudo dnf install wine`, potem `bash tools/test-windows-wine.sh` - pobiera Pythona dla Windows i uruchamia skan oraz listę dysków. To nie jest prawdziwy Windows, ale wychwytuje błędy w kodzie.
2. **GitHub Actions**: po wypchnięciu repozytorium job `windows-smoke` buduje `tidydisk.exe` na prawdziwym Windows i zapisuje go jako artefakt do pobrania.
3. **Maszyna wirtualna**: `sudo dnf install virt-manager`, darmowy obraz Windows 11 Enterprise (90 dni) z Microsoft Evaluation Center - tam uruchom `.exe` z kroku 2. Najpewniejszy test, przed włączeniem usuwania.

## Terminal: polecenia pomocnicze
- `tidydisk clean --plan plan.json` zapisuje plan (bez poleceń i pakietów, nic nie usuwa); `clean --apply plan.json [--yes]` skanuje od nowa i wykonuje tylko te pozycje z planu, które nadal są bezpieczne, mają te same ścieżki i nie urosły.
- `tidydisk status [--json] [--exit-code --min-free GB]` - wolne miejsce; z `--exit-code` kończy się kodem 1, gdy któryś dysk ma mniej wolnego niż próg (do skryptów i monitoringu). JSON ma pole `schema`.

- `tidydisk ai [--mode ai_only] [--notify] [-q] [--wait-ai MIN]` - skan i ocena AI bez okna (to uruchamia timer); `ai --last` pokazuje wynik, `ai --export plik.csv` (albo `.json`) zapisuje zapamiętane oceny AI.
- `tidydisk changes` - co urosło lub przybyło od poprzedniego skanu.
- `tidydisk diag [--out plik]` - zrzut diagnostyczny do wysłania razem z raportem.

## Pakiety

`packaging/tidydisk.spec` buduje RPM (`rpmbuild -ba`). Instalacja z `install.sh` zostaje dla użytkownika bez roota.

## Licencja

GPL-3.0-or-later (pełny tekst w pliku `LICENSE`) - zgodna z licencją PyQt6, na którym program stoi.

## Testy

    python3 -I tests/test_all.py     # logika, skaner, raport i logika okna na atrapie Qt
    python3 tests/smoke_qt.py        # smoke-test okna na prawdziwym PyQt6 (QT_QPA_PLATFORM=offscreen; bez PyQt6: SKIP)

Te same testy + `pyflakes` uruchamia CI (`.github/workflows/ci.yml`, kontener Fedora).
