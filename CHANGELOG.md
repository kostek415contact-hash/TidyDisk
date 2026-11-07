# Historia zmian

## 2.23.12 - Serwer AI na innym komputerze w sieci

- Nowa opcja **„Serwer AI w sieci lokalnej”** (Ustawienia → AI, `config set ai_lan true`), domyślnie wyłączona. Po włączeniu program przyjmuje adres IP z sieci prywatnej (192.168.x.x, 10.x.x.x, 172.16–31.x.x, fc00::/7), np. `http://192.168.1.17:8888`. Adresy publiczne, nazwy hostów, adresy z `użytkownik@` i przekierowania nadal są odrzucane; zapytania nadal idą bez proxy ze środowiska.
- Uwaga: nazwy plików, ścieżki, krótkie podglądy zawartości i klucz API idą wtedy do tamtego komputera nieszyfrowanym HTTP. Bezpieczniejsza alternatywa: tunel SSH i adres `127.0.0.1` (opis w README).
- Zgodę na sieć zmienia tylko użytkownik w Ustawieniach lub `config set`; importowany plik ustawień jej nie przenosi.
- Nie uruchamiane jeszcze na prawdziwym serwerze AI w sieci.

## 2.23.11 - Poprawki po kolejnym audycie

- **Naprawa (CLI):** `clean --only games|kernel|packages` (i kategorie Windows) nie kończy się już błędem tylko dlatego, że skan na tym komputerze takiej kategorii nie zwrócił; `config set` nie zgłasza fałszywego błędu przy normalizacji (spacje, `~`, końcowy `/`, duplikaty); `--min-size` i `--older-than` odrzucają `nan`/`inf`; `-q` nie ukrywa już błędów pojedynczych pozycji przy czyszczeniu.
- **Naprawa (uczenie):** jeden uszkodzony wpis w `learn.json` nie kasuje już wszystkich próbek ani listy „Nie proponuj więcej”.
- Raport/diagnostyka: ścieżka z `/home/…` wewnątrz katalogu domowego nie zamienia się w `~~`; login w ścieżce kopii na innym dysku jest maskowany bez niszczenia struktury; `HOME=/` nie wyciera całego tekstu.
- Historia: nieistniejące katalogi nie zawyżają „zwolniono”; proporcja przy częściowym sukcesie liczona z istniejących ścieżek; zapis „zwolniono” nie zależy od dziennika; ścieżka z pojedynczym surogatem jest odrzucana zamiast przerywać czyszczenie.
- Zapisy plików: `fsync` przed podmianą, dowiązanie (np. z dotfiles) zostaje dowiązaniem, `FC_CONFIG` ze ścieżką względną działa.
- Okno: kliknięcie kategorii z ukrytymi (filtrem) dziećmi potrafi ją odznaczyć; przerwanie skanu administratora działa też, gdy trafi przed startem procesu, i kończy się komunikatem „Przerwano”; „Wszystkie pliki” znów liczą rozmiary na żywo (rozmiary z analizy zaniżały foldery z twardymi dowiązaniami).
- Instalator: skaner administratora generowany z `TIDYDISK_NO_MIGRATE=1` (jak w pakietach).
- Usunięty martwy sygnał postępu analizy.
- Nie uruchamiane jeszcze na prawdziwym Windows.

## 2.23.10 - Audyt: równoległe zapisy, anonimizacja, historia, CLI

- **Naprawa (ważne):** równoległe zapisy ustawień, historii i pamięci uczenia mogły uszkodzić plik (wspólny plik tymczasowy) albo po cichu się nie udać. Teraz każdy zapis ma własny plik tymczasowy.
- Anonimizacja raportu i diagnostyki: katalog domowy znika też przy apostrofie, nawiasie, dwukropku i przecinku oraz na Windows (wielkość liter, `/` i `\`); cudze konta w `/home/...` nie zjadają znaków za nazwą. (Wpis 2.23.9 o `/home/janusz` opisywał to nieprecyzyjnie: cudze konta były i są maskowane do `~`.)
- Historia: wpis z kilkoma ścieżkami, w którym część się usunęła, a część nie, zapisuje to, co zniknęło; nieistniejący plik nie zawyża „zwolniono” i nie trafia do Historii; błąd odczytu informacji o pliku (inny niż „brak”) jest raportowany.
- Zapisy eksportu AI i `lastrun.json` nie wywalają się na nazwach w złym kodowaniu; ścieżka z znakiem NUL jest odrzucana; ustawienia zagnieżdżone w nieskończoność nie rzucają wyjątku.
- CLI: `-q` nie ukrywa już błędów użycia; `clean --json` bez `--yes` wypisuje podsumowanie symulacji; nieznana kategoria w `--only` to błąd; `config set` ostrzega i zwraca błąd, gdy wartość została odrzucona lub zmieniona; zapis do niedostępnej ścieżki (`--plan`, `diag --out`, `report -o`) daje komunikat zamiast tracebacku; `tidydisk -q ai` kończy się od razu po zapisie wyników.
- Praca AI w tle: błąd „serwer nie odpowiedział” nie pojawia się już, gdy foldery zostały ocenione, a zawiodła tylko weryfikacja.
- Duplikaty: filtr folderów z zostawianym oryginałem działa w czasie liniowym (wcześniej minuty przy 100 tys. plików) i nie gubi kopii wewnątrz folderu.
- Okno: „Zaznacz polecane / Odznacz” nie ruszają wierszy ukrytych filtrem także w „Wszystkich plikach” (ukryty dysk); kategoria przy filtrze pokazuje stan częściowy; „Wszystkie pliki” korzystają z rozmiarów z analizy; przerwanie skanu administratora zatrzymuje proces; teksty o Harmonogramie i pliku uczenia dostosowane do Windows.
- Migracja starych timerów podmienia też stary `PYTHONPATH`; instalator: `&`/`|` w ścieżce nie psują wpisu `.desktop`, a nieudane generowanie skanera administratora nie zostawia pustego pliku.
- Uczenie: uszkodzony `learn.json` o poprawnym JSON-ie nie wywala programu.
- Nie uruchamiane jeszcze na prawdziwym Windows.

## 2.23.9 - Kolejny audyt: ochrona, czyszczenie, raporty, AI

- **Bezpieczeństwo:** `.ssh`, `.gnupg` i `.git` (także `.GIT` na dyskach bez rozróżniania wielkości liter) są chronione na każdej głębokości, również gdy wskażesz sam taki folder poza `~`. Dotyczy Linuksa i Windows.
- Czyszczenie: wyjście poleceń w złym kodowaniu (pkexec, podman, flatpak) nie przerywa już czyszczenia ani nie gubi wpisu w Historii; plik 0 B, który od skanu zaczął się pobierać, nie jest kasowany.
- `clean --exclude '$HOME/…'` rozwija zmienne; ścieżka chroniona w ustawieniach bez ścieżki bezwzględnej nie jest już po cichu pomijana (nienadzorowane czyszczenie odmawia).
- Nazwy plików w złym kodowaniu nie wywalają zapisu uczenia, ustawień, planu `--plan` ani raportu.
- Raport/diagnostyka: nazwy w «…» (np. oryginał duplikatu) są maskowane przy anonimizacji, a skracanie katalogu domowego nie ucina cudzych loginów (`/home/janusz`).
- `schedule enable` zwraca błąd, gdy systemctl/schtasks nie włączył timera; `schedule --mode` przyjmuje tylko assisted/ai_only.
- AI: numer pozycji tylko całkowity (nie 1.9 ani true), odporność na dziwne odpowiedzi serwera, lepsze rozpoznanie błędów 401/403 i CUDA; praca w tle zgłasza błąd, gdy serwer nie odpowiedział na żadną paczkę plików.
- Okno: „Zaznacz polecane” i „Odznacz” nie ruszają wierszy ukrytych filtrem; błąd skanu pokazuje komunikat zamiast pustej listy; anulowanie sprawdzania zdjęć kończy się komunikatem.
- Duplikaty: folder (np. `build/`) zawierający zostawiany oryginał nie jest proponowany do usunięcia.
- Migracja starych timerów nie psuje ścieżki w `PYTHONPATH`; instalator cytuje `Exec=` przy spacji w ścieżce.
- Nie uruchamiane jeszcze na prawdziwym Windows.

## 2.23.8 - Naprawa błędu okna po czyszczeniu

- **Naprawa (ważne):** w 2.23.7 po każdym czyszczeniu w oknie pojawiał się błąd „nieoczekiwany”, a lista Polecanych nie odświeżała się (metoda czyszcząca „duchy” trafiła do złej klasy). Dodany test pilnuje, żeby okno główne nie sięgało po dane strony Sprzątania.
- Okno: „Nie proponuj tego więcej” i „Zawsze zostaw” naprawdę usuwają wiersz (wcześniej wracał po zmianie filtra); po nowej analizie panel szczegółów nie działa na starej pozycji; w trybie „Bardzo dokładny” wyniki AI od razu pojawiają się na liście.
- Historia i pamięć AI: nazwa pliku w złym kodowaniu (np. stary cp1250) nie wywala już zapisu po wykonanym usunięciu.
- AI w tle: gdy serwer nie odpowiada na żadne zapytanie, zadanie kończy się błędem zamiast „zakończone”; błąd 403 ma czytelny komunikat.
- Rozpoznawanie działającego programu po obciętej nazwie procesu jest ostrożniejsze (bez fałszywych ostrzeżeń).
- Nie uruchamiane jeszcze na prawdziwym Windows.

## 2.23.7 - Naprawa regresji z 2.23.6 i poprawki okna

- Naprawa: kontrola „plik zmienił się od skanu” porównywała rozmiar logiczny z zajętym na dysku i odrzucała prawie każdy plik z Polecanych; teraz akceptuje oba.
- Naprawa: „Przywróć z kosza” zawsze kończyło się błędem (odczyt punktów montowania).
- Cache Poetry (`virtualenvs`) jest „Do przejrzenia”, a nie „Bezpieczne” (zdublowana reguła).
- `clean --older-than`: bardzo duży katalog traktowany jest jako świeży (nie czyścimy), zamiast zawyżać wiek.
- Okno: usunięte lub pominięte (wyłączona reguła, „Nie proponuj więcej”) propozycje nie zostają „duchem” zaznaczonym na liście i w sumach, także po czyszczeniu; po błędzie analizy znika pasek postępu; „Zostaw”/„Zaznacz” z panelu mają pierwszeństwo przed oceną AI nawet bez zmiany stanu pola.
- AI: błędny klucz API (401/403) nie jest ponawiany (wcześniej ocena wisiała ok. 8 minut); urwana odpowiedź modelu zachowuje kompletne wpisy; filtr zagnieżdżonych pozycji i „Nie proponuj więcej” działają też ze ścieżkami Windows; pamięć AI ustawiona na 0 dni nie nadpisuje pliku pustym; raport nie odsyła pustych opisów do niezwiązanych pozycji.
- Nie uruchamiane jeszcze na prawdziwym Windows.

## 2.23.6 - Ochrona stref „Nie ruszaj” i kontrola przed usunięciem

- Ogólne reguły po nazwie (`node_modules`, `.venv`, `__pycache__`) nie zdejmują już ochrony ze stref „Nie ruszaj” (`~/.vscode`, `~/.mozilla`, `~/.ssh`...).
- Przed usunięciem propozycji z analizy program sprawdza, czy plik nadal istnieje i ma ten sam rozmiar co przy skanie; zmieniony jest pomijany.
- Ochrona „Nie ruszaj” działa też, gdy katalog domowy jest dowiązaniem na inny dysk.
- `~/.cache`: rclone, JetBrains, Poetry, Borg, KeePassXC i Evolution są „Do przejrzenia” (nie zaznaczane automatycznie); rozpoznawanie działającego programu radzi sobie z obciętą nazwą procesu (`chromium-browse`).
- Przyciski „Zaznacz”/„Zostaw” w panelu szczegółów odświeżają pola wyboru we wszystkich zakładkach.
- `config set`/`config import` zgłaszają błąd, gdy zapis się nie udał.
- „Przywróć z kosza” szuka też w koszu zewnętrznych dysków i uwzględnia `XDG_DATA_HOME`.
- Windows: zadanie harmonogramu uruchamiane ze źródeł Pythona podaje ścieżkę pakietu.
- README zgodne z kodem (usuwanie, harmonogram, artefakty CI, motywy).
- Nie zrobione: podgląd filmów/PDF i skan dysków sieciowych nadal w wątku okna (możliwe krótkie zamrożenie); `_guard` bez `try/finally`.
- Nie uruchamiane jeszcze na prawdziwym Windows.

## 2.23.5 - Poprawki po pełnym audycie

- Czyszczenie starych logów administratora działało zawsze błędem (`find -delete` z `-prune`) i psuło cały skrypt roota; naprawione.
- `clean` (CLI) odmawia pracy, gdy nie da się wiarygodnie odczytać ustawień (chronione ścieżki); `--older-than` liczy wiek po najnowszym pliku w środku; `--exclude` i ustawienia rozumieją `$HOME`; lista ścieżek w `config set` używa separatora systemu (Windows: `;`).
- Plik, który zniknął w trakcie czyszczenia, nie jest już błędem.
- Raport: kolumna „Gdzie” pokazuje polecenie administratora; nazwy „Twoich plików” są maskowane także poza katalogiem domowym i bezpośrednio w nim; „Co się zmieniło” nie raportuje całego łańcucha folderów.
- AI: klucz API z niedozwolonym znakiem nie wycieka do komunikatów błędu; odpowiedź modelu z dopiskiem lub urwanym końcem nie gubi całej paczki; trafniejsze komunikaty błędów; pliki `.ts` nie są traktowane jak wideo.
- GUI: usunięta propozycja nie zostaje „duchem” na liście; ostrzeżenie o używanych plikach i usuwanie zdjęć mają domyślnie „Nie”.
- install.sh/uninstall.sh: odpowiedź „nie” była traktowana jak „tak”; uninstall wyłącza timery.
- Diagnostyka na Windows nie zostawia nazwy użytkownika w ścieżkach.
- Nie uruchamiane jeszcze na prawdziwym Windows.

## 2.23.4 - Drobne poprawki po audycie końcowym

- Ochrona folderów: ocena „Nie ruszaj” sprawdzana w każdym podfolderze bez limitu (wcześniej po 20 000 folderach kontrola cicho się kończyła), błąd odczytu podfolderu to odmowa.
- Ostrzeżenie „pozycje są używane przez programy” działa też, gdy obok jest inny otwarty plik o podobnej nazwie (`app` i `app-old`) oraz na dyskach zewnętrznych w `/run/media`.
- Odporność: uszkodzony plik pamięci AI nie blokuje startu; dziwna nazwa folderu Steam nie przerywa skanu.
- Nie uruchamiane jeszcze na prawdziwym Windows.

## 2.23.3 - Mniej fałszywych odmów przy ochronie folderów

- Kontrola „czy w środku jest coś chronionego” nie odmawia już dla głębokich ani wielkich folderów (np. `node_modules`): `.git`/`.ssh`/`.gnupg` szukane są na każdej głębokości (limit 2 mln elementów), ocena bazy wiedzy tylko do 5 poziomów. Nieczytelny podfolder nadal oznacza odmowę. Junctiony i dowiązania nie są przekraczane.
- Czytelniejszy komunikat odmowy.
- Nie uruchamiane jeszcze na prawdziwym Windows.

## 2.23.2 - Poprawki po drugim audycie

- Bezpieczeństwo: folder z `.git`/`.ssh`/`.gnupg` albo innym elementem „Nie ruszaj” w środku nie trafia już do Kosza (wcześniej kontrola była tylko przy trwałym usuwaniu). Kontrola sięga 8 poziomów i do 100 000 elementów, a gdy folder jest za duży lub za głęboki, program odmawia zamiast zgadywać.
- `notify --auto-clean` nie czyści, gdy nie da się wiarygodnie odczytać ustawień (uszkodzony JSON, brak pliku z `--config`).
- `--exclude` rozumie `~` i ścieżki względne.
- Linux: dwukropek lub backslash w nazwie folderu nie psuje już ocen AI ani „Co się zmieniło”.
- CLI/exe: `pythonw` bez strumieni nie przerywa `notify` (cooldown i auto-clean działają); `--opcja=wartość` trafia do CLI; prawdziwy błąd importu nie jest ukrywany; zła godzina w harmonogramie daje czytelny komunikat.
- GUI: sortowanie rozmiarów w „Wszystkich plikach” jest liczbowe; okno błędu pojawia się jedno naraz i tylko w wątku głównym.
- Nie uruchamiane jeszcze na prawdziwym Windows.

## 2.23.1 - Windows: poprawki po audycie

- Bezpieczeństwo usuwania: odrzucane nazwy-aliasy (końcowa kropka/spacja, strumienie `:`, nazwy urządzeń, 8.3), pliki tylko w chmurze (OneDrive) są pomijane, ponowna kontrola junctionów przed wejściem do katalogu, Kosz z oknami systemowymi (Windows pyta, gdy element się nie mieści). Foldery OneDrive/Dropbox/Google Drive, pliki z kropką, `.git`, `.ssh`, `.gnupg` są chronione.
- Skaner pomija junctiony (ten sam plik nie wygląda już na duplikat).
- Ścieżki natywne (`\`) w AI (ochrona kluczy `.ssh`/`.aws`, foldery „zostaw”, skracanie `~`), raporcie (maskowanie „Twoich plików”), „Co się zmieniło”, zaznaczaniu (folder + plik w środku), uczeniu.
- Eksplorator: czyszczone tylko `thumbcache_*`/`iconcache_*`.
- Harmonogram Windows: zadanie uruchamia `tidydisk-gui.exe` (bez okna konsoli), czytelny komunikat błędu `schtasks`, sprawdzane wyłączanie; `tidydisk-gui.exe` przyjmuje polecenia (`notify`, `ai`), zapisuje `crash.log` przy awarii; do exe dołączone tłumaczenia.
- „Przywróć z kosza” na Windows kieruje do Eksploratora.
- Nie uruchamiane jeszcze na prawdziwym Windows.

## 2.23.0 - Windows: komplet funkcji z Linuksa

- Windows: harmonogram pracy AI w tle (zadanie `TidyDisk-ai`, `tidydisk ai --notify`) i opcjonalne automatyczne czyszczenie w harmonogramie (`--auto-clean`: tylko pozycje Bezpieczne, domyślnie wyłączone). Przyciski w Ustawieniach działają tak jak na Linuksie.
- Analiza: pusty instalator lub niedokończone pobieranie (0 B) w Pobranych/Pulpicie jest proponowany jako „pusty plik - najpewniej nieudane pobranie”.
- Dyski Windows: dysk sieciowy pokazuje ścieżkę UNC, więc widać, gdy dwie litery (np. Y: i Z:) to ten sam udział.
- Nie uruchamiane jeszcze na prawdziwym Windows.

## 2.22.1 - Pusty plik nie jest „nowszą wersją”

- Analiza: pusty plik (0 B, np. nieudane pobranie `Setup_1.2.13.0.exe`) nie jest już traktowany jako nowsza wersja, więc program nie proponuje usunięcia działającego starszego instalatora na jego podstawie.

## 2.22.0 - Windows: analiza plików, AI i harmonogram

- Windows: analiza plików (zakładka Polecane: duplikaty, instalatory, niedokończone pobierania, starsze wersje, najwięksi) - skaner liczy wewnątrz na ścieżkach z `/` i zwraca wynik w postaci natywnej (`C:\\...`); rozpoznawanie „Pobranych” i katalogu domowego nie zależy od wielkości liter.
- Windows: przyciski AI (lokalny serwer modelu po HTTP) i „Analizuj ponownie” widoczne; polecenia `analyze` i `ai` w terminalu.
- Windows: harmonogram sprawdzania dysku przez Harmonogram zadań (`schtasks`, zadanie `TidyDisk-check`) i dymek w zasobniku (PowerShell). Automatyczne czyszczenie w harmonogramie i praca AI w tle nadal tylko na Linuksie.
- Raport na Windows bez wiersza „jądro”.
- Nie uruchamiane jeszcze na prawdziwym Windows (tylko symulacja trybu Windows na Linuksie).

## 2.21.2 - Windows: filtr dysków i podział wg dysków

- Windows: pozycje ze skanu dostają teraz dysk (litera `C:\\`), więc filtr „Wszystkie dyski” nie pokazuje „0 pozycji” przy każdym dysku, a raport nie wpisuje wszystkiego do „(nieznany)”.

## 2.21.1 - Windows: ochrona plików profilu

- Windows: `NTUSER.DAT` (i jego dzienniki), `ntuser.ini`, `.ssh`, `.gnupg` oraz stare dowiązania zgodności (`Application Data`, `Local Settings`, `My Documents`, `Start Menu` itd.) są „Nie ruszaj”. Wcześniej leżały w katalogu domowym jako „Twoje pliki” z polem wyboru, a przy włączonym usuwaniu dałoby się je zaznaczyć.

## 2.21.0 - Windows: czyszczenie włączone

- Windows: usuwanie działa (wcześniej zablokowane). Osobny mechanizm `winfs.py`: odmawia przy ścieżkach przez junction/dowiązanie (`realpath` musi się zgadzać), nigdy nie rusza korzenia dysku ani katalogu domowego, tylko pozycje ocenione jako Bezpieczne/Do przejrzenia (lub wybrane ręcznie poza „Nie ruszaj”); wewnątrz czyszczonych katalogów dowiązania usuwa jako same dowiązania; pliki używane przez programy pomija z komunikatem; wybrane ręcznie idą do Kosza (PowerShell, ścieżka przez zmienną środowiskową).
- Nie było jeszcze uruchamiane na prawdziwym Windows: zacznij od symulacji („Pokaż, co zostanie usunięte”).
- Nadal tylko Linux: analiza plików (duplikaty, duże pliki), AI i harmonogram.

## 2.20.3 - Windows: poprawne oceny plików

- Windows: baza wiedzy działała w trybie linuksowym, więc pliki w `~\\Downloads` i innych miejscach profilu były oceniane jako „Nie ruszaj / Plik poza katalogiem domowym”. Teraz są „Twoje pliki” (archiwa i tymczasowe - „Do przejrzenia”).
- Windows: ukryte przyciski AI i „Analizuj ponownie” (nie działają w tej wersji).

## 2.20.2 - Okno na Windows (tylko odczyt)

- CI buduje `tidydisk-gui.exe` (PyQt6, bez konsoli): dwuklik otwiera okno. Na Windows okno robi tylko skan i raport, usuwanie nadal zablokowane. Okno nie było jeszcze uruchamiane na prawdziwym Windows.

## 2.20.1 - Pasek zajętości dysku z btrfs na kilku partycjach

- „Dyski i partycje”: system plików rozłożony na kilku partycjach (btrfs ×3) był pomijany w sumie dysku, więc dysk 931 GB pokazywał „zajęte 133 GB z 281 GB”. Teraz liczy się raz, proporcjonalnie do udziału partycji na tym dysku.

## 2.20.0 - Audyt: bezpieczeństwo usuwania, Windows, pakiety, dokumentacja

Pięć niezależnych przeglądów kodu (Windows, bezpieczeństwo, pakiety/CI, logika/GUI, UX/dokumentacja). Naprawione:

**Bezpieczeństwo usuwania**
- Wyścig (TOCTOU): usuwanie działa na jednokrotnie rozwiązanej ścieżce rodzica otwartej krok po kroku z `O_NOFOLLOW` i kasuje względem deskryptora; podmiana katalogu na symlink po sprawdzeniu kończy się błędem, nie skasowaniem celu poza dozwolonymi katalogami.
- Końcowy `/` (`~/.ssh/`) nie omija już ochrony „Nie ruszaj”; wybrany ręcznie punkt montowania nie jest czyszczony; zbyt głębokie drzewo nie przerywa czyszczenia (`RecursionError`).
- Korzeń „dozwolonego katalogu”, który symlinkiem wskazuje na katalog domowy, jego przodka lub `/`, jest pomijany.
- Raport (Markdown i CSV) maskuje nazwy plików w „Twoich plikach”; CSV neutralizuje komórki zaczynające się od `= + - @` (wszędzie, puste zostają puste).
- Skaner administratora nie robi `rpm -qp` na plikach użytkowników; `settings.save` nie zmienia praw cudzego katalogu z `--config`.
- Skrypt roota zwraca błąd, gdy którykolwiek krok się nie powiódł (wcześniej liczył się tylko ostatni).
- Migracja timerów nie nadpisuje istniejących nowych jednostek.

**Windows (nadal tylko skan i raport)**
- Zablokowane usuwanie w każdym prymitywie (`remove_path`, `rm_tree`, `remove_contents`, `trash_path`), nie tylko w `run_clean`; okno pokazuje komunikat zamiast potwierdzenia.
- `osal.O_NOFOLLOW/O_NONBLOCK/O_BINARY`, `open_regular`, `pread`; skróty plików, podgląd i zapis ustawień nie wywalają się na Windows.
- `analyze`, `ai`, `background`, `schedule` wyłączone z czytelnym komunikatem; chronione ścieżki działają z `C:\...` i bez względu na wielkość liter; konsola z `errors=replace`.
- Skan: pozycje „zawartość katalogu”, nazwa profilu przeglądarki w etykiecie, ostrzeżenie gdy przeglądarka działa; brak opcji „administrator” i komunikatu o root.

**Logika i GUI (sprawdzone tylko na atrapie Qt)**
- Wątek miniatury wideo nie jest niszczony w trakcie pracy; klik w kategorię nie zaznacza wierszy ukrytych filtrem; wiersze „Wszystkie pliki” przepinane na nowe wpisy po analizie.
- `detect()` nie przerywa na obcej usłudze z kodem 401/403; `notify --disk` z nieznanym dyskiem zwraca błąd; absurdalna data pliku nie wywala okna.

**Pakiety i dokumentacja**
- CI: macierz Fedora 44/45/rawhide, artefakty RPM i `.exe`; `install.sh`/`uninstall.sh` rozpoznają `.deb` i nie przerywają bez terminala; `.deb` zależy od `pkexec`, zawiera CHANGELOG; spec: poprawny `%changelog`, `hicolor-icon-theme`.
- Prompty AI są neutralne systemowo (Linux/Windows/macOS) - **pamięć ocen AI zostanie odświeżona przy następnym przebiegu**.
- README: poprawione zdanie o zmianie nazwy, opis podglądu zawartości dla AI, polecenia terminala, ścieżki Windows; kilka napisów dostało tłumaczenia.

Świadomie bez zmian: klucz API nadal idzie do pierwszego odpowiadającego portu przy pustym adresie (ustaw adres serwera na komputerze wieloosobowym).

## 2.19.5 - Windows: bez informacji o btrfs

- Test `tidydisk.exe` pod Wine (status, skan, raport) przeszedł. Poprawka: na Windows nie pokazujemy już komunikatu o migawkach btrfs (pod Wine był widoczny `/proc/mounts` hosta).

## 2.19.4 - CI: budowa RPM

- CI instaluje `python3-devel` (wymagane przez `BuildRequires` w specu); wcześniej `rpmbuild` przerywał na brakujących zależnościach.

## 2.19.3 - pyflakes: czysto

- `osal.py`: brakujący import `Path` (nazwa w adnotacji); `widgets.py`: reeksport z `progress` jawnie użyty (pyflakes nie czyta `noqa`), usunięty nieużywany `os` i zmienna `pure`; usunięte nieużywane zmienne w `core.py`, `ai.py`, `gui.py`.

## 2.19.2 - .exe uruchamia się; porządki w importach

- `.exe`: osobny punkt wejścia `packaging/windows/entry.py` (skrypt uruchamiany przez PyInstaller nie ma pakietu nadrzędnego, stąd błąd „relative import”); bez argumentów pokazuje status dysku zamiast próbować otworzyć okno Qt. Windows-smoke w CI: skan i budowa przeszły, uruchomienie `.exe` było tym brakującym krokiem.
- Usunięte nieużywane importy (`pyflakes`): `Path` w changes/progress, `time` w widgets, `QCheckBox`/`QInputDialog` w gui, `__version__` w `__main__`.

## 2.19.1 - Poprawki CI

- Job `windows-smoke`: import modułów bez `-I` (z `-I` Python nie widzi katalogu repozytorium).
- Testy: blok wymagający zapisu w `/mnt` (kosz na drugim dysku) jest pomijany bez roota (job `deb` na Ubuntu). Testy sprawdzone także jako zwykły użytkownik.

## 2.19.0 - Windows: katalogi i dyski, test przez Wine

- `osal.config_dir()` / `osal.data_dir()`: Windows `%APPDATA%\\TidyDisk` i `%LOCALAPPDATA%\\TidyDisk`, Linux bez zmian (`~/.config/tidydisk`, `~/.local/share/tidydisk`); wszystkie moduły używają ich zamiast wpisanych na sztywno ścieżek.
- Lista dysków na Windows (litery dysków, typ, system plików, zajętość) zamiast `lsblk`.
- `tools/test-windows-wine.sh`: uruchomienie wersji Windows na Linuksie przez Wine (nie sprawdzone w tym środowisku); README: trzy sposoby testu bez Windowsa.

## 2.18.0 - Nowa nazwa: TidyDisk (dawniej Fedora Cleaner)

- Program nazywa się **TidyDisk**: polecenie `tidydisk`, pakiet `tidydisk` (.rpm/.deb), moduł `tidydisk`, reguła polkit `org.tidydisk.admin-scan`, katalogi `~/.config/tidydisk` i `~/.local/share/tidydisk`.
- Migracja przy pierwszym uruchomieniu: stare katalogi `fedora-cleaner` są przenoszone (ustawienia, historia, pamięć AI), a timery systemd `fedora-cleaner-*` zamieniane na `tidydisk-*`. Nie nadpisuje istniejących nowych plików.
- Pakiety: `Obsoletes/Provides: fedora-cleaner` (rpm), `Replaces/Conflicts/Provides` (deb); `install.sh` usuwa starą instalację. Zmienne `FC_AI_URL/KEY/MODEL` i `FC_CONFIG` zostają bez zmian (zgodność).
- Motyw `fedora` zostaje pod tym kluczem (to nazwa wyglądu, nie programu).

## 2.17.0 - Windows: skan i raport (tylko odczyt; nie sprawdzone na prawdziwym Windows)

- Nowy `scan_windows.py`: znane miejsca z bazy Windows (Temp, cache Edge/Chrome/Firefox/Brave dla każdego profilu, shadery, npm/pip/NuGet/Gradle…), kategorie, oceny; hasła, profile i Dokumenty nigdy na liście.
- `core.scan` na Windows używa tego skanu; lista procesów przez `tasklist`, dysk = dysk profilu użytkownika.
- Usuwanie na Windows zablokowane w `run_clean` (symulacja działa).
- `packaging/windows/build-exe.ps1` (PyInstaller) i kroki w CI: skan na windows-latest + artefakt `.exe`.

## 2.16.2

- Okno "Co zostanie usunięte" i "Odrzucone przez recenzenta": klik w nagłówek kolumny sortuje (nazwa, rozmiar, ocena, miejsce); rozmiar sortuje się liczbowo.

## 2.16.1

- Cofnięty układ z 2.16.0 (szczegóły w pasku pod listą zabierały za dużo wysokości): szczegóły znów w panelu po prawej, ale w nowej, czytelnej postaci z 2.15.0 (decyzja, kafelki, ukryte puste sekcje, przewijanie). Lista jest wyższa.

## 2.16.0 - Sprzątanie: lista na całą szerokość, szczegóły pod nią (interfejs nie oglądany w prawdziwym Qt)

- Wąski panel po prawej zniknął. Lista zajmuje całą szerokość okna, a **szczegóły są w pasku pod listą**: z lewej tytuł, decyzja (✖ do usunięcia / ✔ zostaje) i kafelki; w środku „Gdzie to jest”, „Co to jest”, „Dlaczego”, „Uwaga” i werdykt AI (przewijane); z prawej podgląd i przyciski „Zapytaj AI”, „Zaznacz do usunięcia”, „Zostaw”.
- Lista „Widok” ma czytelne nazwy („Widok: tylko do usunięcia ✖”).

## 2.15.0 - przebudowany panel szczegółów (interfejs nie oglądany w prawdziwym Qt)

- Panel po prawej ma na górze **decyzję**: „✖ Zaznaczone do usunięcia”, „✔ Zostaje (niezaznaczone)” albo „🔒 Program tego nie usuwa”; odświeża się od razu po zaznaczeniu.
- Trzy kafelki: rozmiar, pewność, ocena (ze znakiem). Pod spodem „Gdzie to jest” (pełna ścieżka), „Co to jest”, „Dlaczego można usunąć”, „Uwaga” i werdykt AI - puste sekcje są ukryte.
- Pusty stan to jedno zdanie z podpowiedzią zamiast samych nagłówków; panel jest szerszy (360-480 px) i przewija się, gdy tekstu jest dużo; przyciski zostają na dole.
- Dziennik czyszczenia nie zajmuje już pustej ramki - pojawia się dopiero, gdy ma treść.

## 2.14.0 - Sprzątanie: sortowanie i widoczne zaznaczenie (interfejs nie oglądany w prawdziwym Qt)

- **Sortowanie klikiem w nagłówek** na listach „Polecane” i „System i pakiety”: po nazwie (bez wielkości liter), rozmiarze (liczbowo, nie tekstowo) i pewności; ponowny klik odwraca kolejność. Na starcie zostaje kolejność programu (wg pewności).
- **Zaznaczone do usunięcia** wiersze mają czerwonawe tło i pogrubioną nazwę - od razu widać, co zniknie, bez przewijania do stopki.

## 2.13.1 - czytelność Sprzątania (interfejs nie oglądany w prawdziwym Qt)

- Nowa lista „Widok”: wszystkie pozycje / **tylko do usunięcia ✖** / tylko zostawione. Odświeża się przy każdej zmianie zaznaczenia.
- Przycisk **„Pokaż, co zostanie usunięte”**: okno z pełną listą zaznaczonych (nazwa, rozmiar, ocena ze znakiem, pełna ścieżka, powód), osobno „Bezpowrotnie” i „Do kosza”, od największych.
- Foldery `saves` (zapisy gier, światy Minecrafta) mają ocenę „Nie ruszaj”: nie są już proponowane jako duplikaty.

## 2.13.0

- Baza wiedzy dla Windows (`kb_windows.py`): Temp, cache Edge/Chrome/Firefox/Brave (tylko dokładne podkatalogi cache, nigdy cały profil), shadery, npm/pip/NuGet/Yarn/pnpm, cache VS Code i Discord. Chronione: Windows, Program Files, ProgramData, hiberfil/pagefile, AppData (poza znanymi cache), OneDrive i Dokumenty. Ścieżki są porównywane po normalizacji (`\`, wielkość liter, `\\?\`, UNC). Sprawdzone tylko testami na ciągach znaków - bez prawdziwego Windowsa.
- Debian/Ubuntu/Mint: pozycja „Cache APT” (`apt-get clean`) obok „Cache DNF”.

## 2.12.0 - początek wersji wieloplatformowej

- Nowa warstwa systemowa `osal.py`: rozmiar pliku na dysku, priorytet procesu, blokada pracy w tle, uprawnienia administratora, wersja jądra i użycie dysku w jednym miejscu, z zastępnikami dla systemów bez funkcji uniksowych. Na Fedorze działanie bez zmian; testy sprawdzają też zachowanie bez `uname`, `geteuid`, `nice` i `statvfs`.
- `packaging/build-deb.sh` buduje pakiet .deb (sprawdzone narzędziem `dpkg-deb`); w CI zadanie `deb` i próbne zadanie `windows-smoke` (importy modułów).

## 2.11.0

- `clean --plan PLIK` zapisuje plan (JSON, bez poleceń i pakietów) i nic nie usuwa; `clean --apply PLIK` skanuje od nowa i wykonuje tylko te pozycje z planu, które nadal są bezpieczne, mają te same ścieżki i nie urosły (`--yes` jak zwykle).
- Flatpak: dane odinstalowanych aplikacji z `~/.var/app` jako „Do przejrzenia” (nigdy nie zaznaczane same; bez katalogu instalacji Flatpaka nic nie zgadujemy).
- Nowe znane cache: `Code Cache`, `GPUCache`, `GrShaderCache`, `DawnCache` (Chrome, VS Code, Discord, Slack i inne programy na Electronie).
- Szybciej: skrót częściowy duplikatów obejmuje próbki ze środka pliku (pliki z wypełnionym początkiem i końcem, np. obrazy dysków, nie są już czytane w całości; wynik bez zmian), pełny skrót bez kopiowania bufora, dopasowanie wzorców bazy wiedzy ok. 2,5x szybsze.

## 2.10.1 - porządki w interfejsie (nie oglądane w prawdziwym Qt)

- Jedna paleta ocen dla listy, mapy dysku i legendy; ocena to zawsze znak + tekst + kolor (✔ ▲ ◆ ✖), czytelna też bez rozróżniania kolorów. Kontrast zgodny z WCAG AA w obu motywach.
- Mapa dysku: tekst kafli dopasowany do motywu (na jasnym był nieczytelny).
- Stopka Sprzątania: linia „Co zniknie” (bezpowrotnie / do kosza / liczba pozycji wg oceny).
- Skróty: F5, Ctrl+Enter (czyść, z potwierdzeniami), Ctrl+Shift+R (zaznacz polecane), Ctrl+Shift+D (odznacz); lista w pomocy F1.
- Nazwy dostępności dla przycisków, pól i list rozwijanych; widoczny fokus klawiatury w nowych stylach.
- Zmiana motywu w trakcie sesji przemalowuje wiersze dopiero po następnym skanie.

## 2.10.0

- Po czyszczeniu baner pokazuje prawdziwy pomiar: o ile zmieniło się wolne miejsce na dysku domowym (btrfs z migawkami i kosz mogą zwolnić mniej niż suma rozmiarów).
- Przed czyszczeniem ostrzeżenie o pozycjach używanych teraz przez działające programy (z `/proc/*/fd`), np. cache przeglądarki.
- Nowa opcja „Bezpieczne pozycje w jednym oknie” (domyślnie włączona): przy pytaniu po kolei pozycje „Bezpieczne” potwierdzasz razem, resztę osobno.
- Nowe znane cele czyszczenia: pre-commit, Poetry, pnpm, Bottles, Zig, Bazel, cache cargo, Gradle, repozytorium Maven, PlatformIO, pobrane pakiety Arduino (ostatnie osiem jako „Do przejrzenia”).
- `status --exit-code [--min-free GB]` do skryptów; JSON z `status` i `analyze` ma pole `schema`.

## 2.9.3

- **Błąd w statystyce:** „bez odpowiedzi modelu” liczyło też foldery pominięte celowo, bo leżą wewnątrz folderu ocenionego jako „cały zbędny”. Teraz liczy tylko pozycje, o które zapytano, a model nie dał oceny.

## 2.9.2

- Raport mówi, w jakim trybie wyszukiwania powstał (niedokładny / dokładny / bardzo dokładny) i ile ocen AI ma lista - żeby nie trzeba było zgadywać z samego raportu.

## 2.9.1 - przyspieszenia (wyniki bez zmian, sprawdzone na danych syntetycznych)

- Zaznaczanie pozycji: usuwanie zdublowanych ścieżek było O(n²) i działo się przy każdym kliknięciu (20 tys. zaznaczonych: 64 s → 0,1 s).
- Weryfikacja całych folderów przez AI: 18,5 s → 0,12 s (100 tys. pozycji); klasyfikacja folderów 9,2 s → 1,5 s; dopasowanie najbliższego werdyktu ok. 100× szybciej.
- Skan: ok. 20% szybciej (mniej powtórnych sprawdzeń na plik); filtr końcowy porad 10× szybszy.
- Pamięć ocen AI: zapis co 20 s nie czyta ponownie własnego pliku (2 s → 1 s przy 300 tys. wpisów).

## 2.9.0

- **Nowy styl (opcjonalny):** w Ustawieniach → Wygląd „Nowoczesny (ciemny)” i „Nowoczesny (jasny)”. Domyślny wygląd bez zmian. Styl nie był oglądany w prawdziwym Qt - jeśli coś wygląda źle, wróć do „Fedora Cleaner (ciemny)” i dołącz zrzut.
- Po czyszczeniu i w podsumowaniu: szacunek wolnego miejsca po usunięciu zaznaczonego.
- Historia: panel „Zmiany od ostatniego skanu”.
- Okno z pozycjami odrzuconymi przez recenzenta AI (można je zaznaczyć ręcznie).
- `ai --export plik.csv|.json` - zapisuje zapamiętane oceny AI (CSV bez formuł arkusza).
- `ai --wait-ai MIN` - praca w tle czeka do MIN minut na serwer AI; jednostka systemd używa `--wait-ai 10` (przydatne tuż po starcie systemu).

## 2.8.1

- Gdy recenzent nie zatwierdził pozycji, bo nie odpowiedział, opis mówi dlaczego: „serwer nie zwrócił odpowiedzi” albo „odpowiedź bez tej pozycji lub w złym formacie”; liczba takich przypadków trafia do statystyk (`bez_odpowiedzi`).

## 2.8.0 - praca w tle sprawdzona od początku do końca, diagnostyka, zmiany od ostatniego skanu

Praca w tle (sprawdzona prawdziwym uruchomieniem z atrapą serwera AI: skan, oceny, pamięć, brak serwera, blokada, SIGTERM)
- **Błąd naprawiony:** jednostka systemd wywoływała `ai --notify -q`, a `-q` po poleceniu `ai` było odrzucane - nocne uruchomienia kończyłyby się błędem. Teraz `-q` działa w obu miejscach.
- Po starcie okna jedna linia o pracy w tle, która skończyła się od ostatniej wizyty (oceny wczytają się z pamięci).
- Zakończenie przez SIGTERM: przebieg kończy się w sekundę, zapisuje `lastrun.json` (przerwane) i pamięć ocen.

Odporność AI
- Za duże zapytanie (okno kontekstu modelu): paczka jest dzielona na pół i ponawiana; pojedyncza zbyt duża pozycja zostaje bez oceny, reszta idzie dalej.
- Łączny limit czasu pojedynczego zapytania (2 × limit czasu z ustawień); wolny serwer nie blokuje paczki bez końca.
- Znacznik folderu w pamięci ocen zawiera czas zmiany folderu: zmieniony folder dostaje nową ocenę.

Nowe
- `fedora-cleaner diag` / Ustawienia → Dane: zrzut diagnostyczny (bez klucza API i nazwy użytkownika).
- `fedora-cleaner changes`: nowe i rosnące duże foldery od poprzedniego skanu (migawka zapisuje się po każdym skanie).
- Menu pozycji: „Zawsze zostaw (dodaj do chronionych)”.
- CI zapisuje zrzuty ekranu stron okna jako artefakt.
- Tłumaczenia: moduł `i18n` (klucz = polski tekst, katalog `locale/en.json`), ustawienie `language`. Na razie przetłumaczone: menu boczne i kilka akcji; resztę dopisuje się do katalogu bez zmian w kodzie.

## 2.7.2 - czytelniejszy opis ocen AI w raporcie

- „Bardzo dokładny”: opis pozycji zaczyna się od werdyktu („AI: lepiej zostawić (ryzyko niskie): …”), a nie od samego ryzyka - przy pozycji odrzuconej przez recenzenta nie wygląda już, jakby AI ją polecało.
- Raport: tytuł i uzasadnienie rozdzielone myślnikiem.

## 2.7.1 - poprawki po audycie pracy w tle, bezpieczeństwa i odporności AI

Praca w tle
- Pamięć ocen AI scala się z plikiem na dysku przy zapisie: GUI i praca w tle nie kasują już sobie nawzajem wyników; zapis idzie przez unikalny plik tymczasowy, uszkodzony plik trafia do `aicache.json.bad`.
- Błąd skanu albo odrzucony klucz API nie kończą się tracebackiem: przebieg zapisuje ślad (`lastrun.json`), a powiadomienie mówi, co poszło nie tak. Powiadomienia przychodzą tylko gdy coś znaleziono albo był błąd.
- Jednostka systemd: ponowienie po 15 min przy błędzie lub braku serwera AI (najwyżej 4 razy na dobę), 5 min na zapis po SIGTERM, cudzysłów wokół `PYTHONPATH` (ścieżki ze spacją), `%` zdwojone.
- Zamknięcie okna przy zasobniku bez pracy w tle kończy program (nie zostaje niewidzialny proces).
- `lastrun.json`, `scanstats.json`, `notify.json` zapisywane atomowo z prawami 0600.
- Zakończenie `ai` nie czeka na porzucone zapytania do modelu.
- Uwaga: timery użytkownika nie działają po wylogowaniu; `loginctl enable-linger $USER` pozwala im działać w nocy bez sesji.

Odporność AI
- Restart serwera AI w trakcie przebiegu: ponawianie z przerwami (5 s, 20 s, 60 s); paczka bez odpowiedzi jest pomijana, przebieg kończy się dopiero po 6 takich paczkach z rzędu (oceny z pamięci zostają).
- Powtórzone numery w odpowiedzi modelu: wygrywa pierwsza odpowiedź; przykład w prompcie używa numeru 0 (zgodnie z numeracją).
- Ścieżki w zapytaniach przycięte do 240 znaków; uzasadnienia AI bez znaczników i znaków sterujących.
- Cały folder uznany za „do usunięcia” jest pomijany także wtedy, gdy w środku jest mały `.git`/`.ssh`/`.gnupg`.

Bezpieczeństwo
- Reguła polkit pyta o hasło przy każdym skanie administratora; `install.sh` przekazuje skrypt do `sudo install` rurą (bez pliku tymczasowego); skrypt i polityka nie nadpisują instalacji z pakietu RPM; sprawdzenie skryptu odrzuca dowiązania w ścieżce.

## 2.7.0 - polkit, harmonogram AI w oknie, pakiet RPM

- Skan administratora to teraz wykonywalny skrypt z własną regułą polkit (tylko ten jeden plik, tylko odczyt, hasło pamiętane krótko). Skrypt sprawdza argumenty, bo działa jako root.
- Okno „Historia”: włączanie i wyłączanie cyklicznej oceny AI w tle (częstotliwość, godzina, wynik ostatniego uruchomienia).
- Licencja GPL-3.0-or-later (`LICENSE`), plik AppStream `.metainfo.xml`.
- Pakiet RPM (`packaging/fedora-cleaner.spec`): skaner administratora w `/usr/libexec/fedora-cleaner/`.
- Nowe ustawienie `scan_parallel` (domyślnie 1): skanowanie kilku miejsc naraz. Pomiar: na rozgrzanym cache równolegle bywa wolniej, więc jest wyłączone.
- CI: Fedora 43, 44 i rawhide (rawhide nie blokuje), walidacja `.desktop` i metainfo, budowa RPM.

## 2.6.2 - tryb „Bardzo dokładny” bez śladów algorytmu

- Zamiast „Pewność 80%/55%” (to był tylko zapis ryzyka podanego przez model) pokazuję „Ocena AI (ryzyko niskie/średnie)”; w kolumnie listy samo „niskie/średnie”.
- Pozycje wskazane przez AI mają tytuł „Wskazane przez AI” zamiast nazwy z bazy wiedzy (np. „Pakiet RPM”).
- Raport: powód zostawienia to „AI nie zatwierdziło usunięcia”, nie „program nie zaznacza tego sam”.

## 2.6.1 - poprawki z raportu 2.6.0

- Uzasadnienia AI nie odwołują się już do numerów z zapytania („jak w pozycji 0”) - takie zdania są odrzucane, zostaje powód programu.
- Komunikat „recenzent nie odpowiedział” zastąpiony czytelnym „nie zatwierdzone: recenzent nie odpowiedział”.
- Raport: „Zajęte” dla btrfs na kilku partycjach podane raz.

## 2.6.0 - pasek postępu na każdej stronie, skróty, dokumentacja

- Pasek postępu z procentami, ETA i przyciskiem „Przerwij” w pasku stanu - widoczny na każdej stronie.
- Skróty: Ctrl+1..8 (strony), Ctrl+, (ustawienia), Ctrl+F (szukaj), F1 (lista skrótów); nazwy dla czytników ekranu.
- Pozycje, które AI ogląda poza kandydatami algorytmu, respektują wyłączone reguły.
- Dane folderów w zapytaniu do AI owinięte w losowe znaczniki (odporność na „wstrzyknięcia” w nazwach).
- Kopie tego samego pliku o różnym rozmiarze: zostaje nowszy plik.
- Dokumentacja: `CHANGELOG.md`, sekcja Prywatność, tabela ustawień (test pilnuje, by każde ustawienie było opisane).
- `.desktop`: StartupWMClass oraz akcje menu („Skanuj…”, „Oceń przez AI w tle”).

##  2.5.0 - pamięć ocen AI, praca w tle, więcej opcji terminala

- **Pamięć ocen AI** (`~/.local/share/fedora-cleaner/aicache.json`, prywatny plik): oceny folderów, plików i weryfikacji są
  zapisywane na bieżąco. Przerwanie albo zamknięcie programu nic nie gubi; kolejna ocena pomija to, co już ocenione, i pokazuje
  te wyniki od razu („z pamięci: N”). Po przerwaniu przycisk zmienia się na „Wznów ocenę AI”. Zmiana modelu, promptów, trybu
  albo pliku (rozmiar/data) = nowa ocena. Ustawienia → AI → „Pamiętaj oceny AI (dni)”, 0 = wyłączone.
- **Praca w tle w oknie:** zamknięcie okna w trakcie skanu lub oceny AI chowa program do zasobnika zamiast go przerywać;
  ikona ma menu (Pokaż / Przerwij / Zakończ), a po zakończeniu przychodzi powiadomienie. Wyłączenie: Ustawienia → „Praca w tle
  po zamknięciu okna”. Ctrl+Q zamyka naprawdę.
- **Praca w tle bez okna:** `fedora-cleaner ai [--mode assisted|ai_only] [--notify]` robi skan i ocenę AI o niskim priorytecie
  (nice + ionice), z postępem w procentach i szacowanym czasem; tylko jedna taka praca naraz; nic nie usuwa. Wyniki lądują w pamięci
  ocen, więc po otwarciu okna ocena AI kończy się od razu. `fedora-cleaner ai --last` pokazuje ostatni przebieg.
  Cyklicznie: `fedora-cleaner schedule enable --ai --every weekly --time 03:30` (timer systemd użytkownika).
- **Terminal - nowe opcje:** `--version/-V`, `-q`, `--config PLIK`; kody wyjścia (0 ok, 1 błąd, 2 złe użycie, 3 praca w tle już
  działa, 4 brak serwera AI); `analyze --mode/--min-score/--depth/--limit/--format text|json|csv`; `scan/clean --disk --only
  --rules +iso,-video`; `clean --dry-run --force --exclude --older-than DNI --min-size MB` (opcje tylko zawężają zakres; symulacja
  z ustawień nie jest przebijana przez `--yes` bez `--force`); `notify --disk --stdout-only --cooldown`; `schedule --time`;
  nowe polecenia `config path|list|get|set|export|import` (klucza API nie ustawiamy z wiersza poleceń), `rules`, `history`.
- Tryb „Bardzo dokładny”: prompt nie wspomina już o ocenie programu; weryfikacja AI idzie równolegle jak pozostałe etapy.

##  2.4.1 - poprawki z audytu

- **Bardzo dokładny:** AI ocenia teraz także pojedyncze pliki w środku folderów (wcześniej pula zawierała tylko foldery najwyższego
  poziomu); foldery ocenia etap 3, pliki etap 4. Pasek skanu liczy 0-100% bez etapów, których w tym trybie nie ma, lista plików nie
  jest obcinana do 1000, a cache skrótów z trybu „Dokładny” nie jest nadpisywany pustym.
- **Starsze wersje:** „Disc 1/2”, „Season/part/vol”, lata i daty w nazwach, 32/64 bit oraz „(2023)” nie są już uznawane za wersje
  ani kopie; `1.1` = `1.1.0`.
- **Zawsze zostaje jeden egzemplarz:** to, co jeden detektor (duplikaty, wersje, kopie) zostawia, nie może zostać zaproponowane
  do usunięcia przez inny.
- **Foldery z `.git`, `.ssh`, `.gnupg` w środku** nie są kasowane w całości (ani proponowane przez AI jako „cały zbędny”).
- **Zmiana trybu w trakcie skanu** uruchamia nowy skan po jego końcu i czyści stare oceny AI; pozycje już nieistniejące znikają z listy.
- **Zapytania AI:** anulowanie nie czeka na wolne zapytania, jedna zła paczka nie zabija etapu, ponowienie tylko po błędach
  przejściowych (nie po odmowie dostępu).
- Pomijane są też zdalne systemy plików FUSE (rclone, s3fs …) i `davfs`/`9p`/`ceph`.

##  2.4.0 - pasek postępu z procentami i szacowanym czasem

- W zakładce Sprzątanie pod paskiem stanu jest pasek „Skan: 42% · pozostało ok. 3 min” (analiza plików) oraz
  „AI: 17% · pozostało ok. 1 h 05 min” (ocena AI: foldery + pliki + weryfikacja razem).
- Analiza plików zapamiętuje, ile plików miał poprzedni skan każdego dysku (`scanstats.json`), dzięki czemu zna 100%.
  Przy pierwszym skanie pasek jest „w ruchu” (bez procentów), a czas pojawia się od drugiego.
- Czas to szacunek z dotychczasowego tempa (po 3% i 8 s), wygładzany, żeby nie skakał; postęp nigdy się nie cofa.
  W ocenie AI tempo bywa nierówne (pominięte wnętrza folderów skracają resztę), więc czas może się zmieniać.

##  2.3.0 - szybszy etap AI bez utraty jakości

- **Od góry do dołu:** foldery oceniane są poziom po poziomie, a wnętrza folderów uznanych za „cały zbędny” nie są już pytane
  (ten werdykt obejmuje wszystko w środku). Wnętrza „zostaw” nadal są oceniane (np. `Library` w Twoim projekcie).
  Wyłączenie: Ustawienia → AI → „Pomijaj wnętrza…”.
- **Równolegle:** nowe ustawienie „Zapytań AI naraz” (domyślnie 2, 1–8) dla etapu folderów i plików. Wymaga serwera, który
  obsługuje kilka zapytań (llama-server: `--parallel N`); przy 1 działa jak dawniej.
- Ocena pojedynczego folderu/pliku jest taka sama jak wcześniej - zmienia się tylko kolejność i liczba zbędnych zapytań.

##  2.2.6

- „Bardzo dokładny”: progi rozmiaru obniżone do 1 MB (foldery i pliki); razem z brakiem limitów liczby AI dostaje praktycznie
  wszystko, co ma sens oceniać. Skan zapisuje foldery od 1 MB na każdej głębokości.

##  2.2.5

- „Bardzo dokładny” nie ma limitów liczby: AI ocenia wszystkie foldery i pliki powyżej progów rozmiaru (od 2.2.6: od 1 MB), bez limitu głębokości i bez limitu listy największych plików. Limity „ile ocenia AI”
  z Ustawień dotyczą tylko trybu Dokładny. Uwaga: przy dużym dysku to dużo zapytań i długi czas pracy modelu.

##  2.2.4

- Etap 3/5 (AI, foldery) pokazuje „X z N”, gdzie N to limit największych folderów (Ustawienia → AI, domyślnie 300), z dopiskiem o limicie.
- Foldery, na które model nie odpowiedział (np. urwany JSON), są pytane jeszcze raz; reszta jest wymieniona w podsumowaniu
  („bez odpowiedzi modelu: N”), zamiast po cichu znikać.

##  2.2.3

- Czytelniejszy postęp analizy: „Etap 2/3: Pakiety rpm - miejsce 1 z 2: ~ - …”. Etapy: przeglądanie plików (liczba sprawdzonych
  plików i bieżący folder), pakiety rpm, duplikaty (grupa X z Y) oraz scalanie wyników. W trybie „Bardzo dokładny” jest tylko
  przeglądanie plików. Etapy AI nadal mają numery 1-2/5 … 5/5.

##  2.2.2

- Tryb „Bardzo dokładny” nie uruchamia już algorytmu w ogóle: skan tylko mierzy rozmiary (bez oceniania, duplikatów, wersji,
  hashowania), lista „Polecane” nie bierze propozycji algorytmu ani korekt z uczenia, a `fedora-cleaner analyze` w tym trybie
  niczego nie proponuje (CLI nie ma AI).

##  2.2.1

- **Bardzo dokładny = naprawdę tylko AI.** Algorytm nie podaje już kandydatów, nie ocenia i nie podpowiada modelowi powodów:
  AI dostaje największe foldery i pliki (od 100 MB / 20 MB) bez wskazówek programu, a lista „Polecane” zawiera wyłącznie to,
  co AI wskaże i co przejdzie weryfikację. Zasady bezpieczeństwa (chronione ścieżki, „nie ruszaj”) działają nadal.

##  2.2.0

- **Trzy dokładności szukania** (lista w pasku „Sprzątanie” i w Ustawieniach → Ogólne):
  *Niedokładny* – tylko algorytm (bez AI), *Dokładny* – algorytm + AI (domyślnie), *Bardzo dokładny* – wyłącznie AI (od 2.2.1 bez udziału algorytmu; wymaga działającego serwera AI).
- **Nowy sposób szukania: plik + wersja.** W jednym folderze porównywane są numery wersji w nazwach
  (`SetupSonelPE6_1.2.8.0.exe` vs `…1.2.9.0.exe`, `jdk-17…rpm` vs `jdk-25…rpm`); starsze dostają powód „starsza wersja”,
  najnowsza zostaje.
- **Numerowane kopie** (`nazwa (1).zip` obok `nazwa.zip`) – kopia jest proponowana, oryginał zostaje.
- Nowa reguła „Starsze wersje i numerowane kopie” (Ustawienia → Reguły) i filtr o tej nazwie na liście.
- Ten sam plik wykryty kilkoma sposobami jest teraz jedną pozycją ze wszystkimi powodami.

##  2.1.0

- **Tryb tekstowy** (bez okna): `fedora-cleaner status | scan | analyze | clean | report | notify | schedule`, każde z `--json`.
  `clean` bez `--yes` tylko pokazuje plan; z `--yes` czyści wyłącznie pozycje **Bezpieczne** z kategorii wbudowanych
  (bez AI, bez „Twoich plików”, bez propozycji z analizy, bez administratora, chyba że dodasz `--root`).
- **Harmonogram i powiadomienia**: `fedora-cleaner schedule enable --every weekly [--min-free 20] [--min-reclaim 5]
  [--auto-clean]` tworzy timer systemd użytkownika, który sprawdza dysk i wysyła powiadomienie pulpitu (`notify-send`),
  gdy jest mało miejsca albo dużo do bezpiecznego odzyskania. Włączysz go też przyciskiem na stronie Historia.
  Nic nie usuwa, chyba że sam dodasz `--auto-clean`. Wyłączenie: `schedule disable`.
- **Historia miejsca**: każdy skan/start zapisuje mały punkt (raz na godzinę, `space.json`); strona Historia
  pokazuje wykres zajętego miejsca i przyrost z ostatnich dni.
- **Raport HTML** („Raport ▾” w oknie albo `fedora-cleaner report -o raport.html`): dyski z paskami, ile bezpiecznie
  do odzyskania, wykres, największe pozycje; jeden plik bez zewnętrznych zasobów. `report --json` dla skryptów
  (np. czujnik wolnego miejsca w Home Assistant).
- **Migawki btrfs** (snapper / Timeshift): tylko informacja na stronie Dyski i w `status` - czy są, ile, i że trzymają
  usunięte dane. Program niczego tam nie usuwa.
- **Podobne zdjęcia** (nowa strona): skrót różnicowy dHash, grupy zdjęć prawie takich samych; nic nie jest
  zaznaczane samo, „Zaznacz słabsze kopie” zostawia największą rozdzielczość, usuwanie idzie do kosza i do Historii.

##  2.0.2

- Foldery projektów leżące w koszu (`.Trash-1000`, `~/.local/share/Trash`) nie są już proponowane osobno.

##  2.0.1

- Model AI nie odznacza już folderów projektu rozpoznanych po plikach obok (np. `Library` Unity) - wcześniej
  uznawał je za „niezbędne” i lista pokazywała je jako nieznaczone.

##  2.0.0

- **Podgląd zawartości** przed usunięciem (panel szczegółów i okno „Czy usunąć?”): zdjęcie (miniatura), klatka z
  filmu (ffmpeg), początek tekstu lub PDF-a, spis plików w archiwum i w folderze, tagi audio. Pliki wyglądające na
  poufne (klucze, hasła) nie są pokazywane; dowiązania i pliki specjalne nie są otwierane.
- **Plan przed czyszczeniem**: okno potwierdzenia pokazuje ile pójdzie bezpowrotnie, ile do kosza, rozbicie na dyski,
  polecenia wykonywane jako administrator oraz uwagę o migawkach btrfs.
- **Historia** (nowa strona): dziennik czyszczeń (kiedy, co, jak) w `~/.local/share/fedora-cleaner/history.json`;
  pozycje przeniesione do kosza można stamtąd **przywrócić** na pierwotne miejsce.
- **Gry i kontenery** (nowa kategoria w Sprzątaniu): shadery Steam (zaznaczone tylko dla odinstalowanych gier),
  osierocone prefiksy Proton i stare wersje Proton-GE (zawsze do przejrzenia, nigdy zaznaczane same), nieużywane
  obrazy Podmana (`podman image prune`, wolumeny zostają).
- **Foldery projektów** (Unity: `Library`/`Temp`/`Obj`/`Logs`, Rust `target`, PlatformIO `.pio`, ESP-IDF `build`)
  są rozpoznawane po plikach obok i proponowane jako odtwarzalne, także na dyskach z „Twoimi plikami”. Otwarty projekt
  Unity (blokada w `Temp`) jest pomijany. Wyłączysz to regułą „foldery do odtworzenia”.

##  1.9.0

- Przełączniki z okna „Sprzątanie” przeniesione do Ustawień; wyłączona w Ustawieniach reguła działa też jako
  ostatnia blokada przy samym usuwaniu (nawet gdy pozycja trafiła na listę wcześniej).
- „AI może zaznaczać Twoje pliki” – osobny przełącznik (Ustawienia → AI).
- Powody propozycji mają stałe kody (`kb.REASONS`), więc reguły, uczenie i testy nie zależą od polskich sformułowań.
- Recenzent AI pyta o każdą pozycję osobno (`Pozycje w jednym zapytaniu recenzenta`), a dane trafiają do modelu w
  losowych znacznikach.
- Skrót plików (duplikaty) jest pamiętany między skanami (`~/.local/share/fedora-cleaner/hashcache.json`);
  ustawienia AI są trzymane w pamięci, nie czytane z pliku dla każdej pozycji.
- Wygląd: filtr rodzaju (duplikaty / instalatory / foldery / stare), pierścień „odzyskasz” w stopce, pasek
  zajętości całego dysku na karcie dysku.
- Czytelniejsze komunikaty błędów AI (adres nielokalny, brak serwera, limit czasu, brak pamięci).
