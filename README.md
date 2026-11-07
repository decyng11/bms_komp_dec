# EMS komp-dec

Integracja Home Assistanta, która pilnuje, kiedy falownik Deye ma ładować baterię z sieci, a kiedy ją oddawać. Plan na najbliższą dobę powstaje z cen prądu, prognozy produkcji z paneli i tego, ile dom zwykle zużywa. Do tego jest karta na pulpit z przepływem energii, planem i rozliczeniem w złotówkach.

## Co robi

Plan na dobę ładuje baterię z sieci w najtańszych godzinach, oddaje ją, gdy prąd jest drogi, i blokuje ładowanie z paneli przy wysokich cenach. Zna taryfy strefowe (np. G12w) oraz ceny dynamiczne z RCE i Pstryka.

Zużycie domu jest liczone z historii, osobno dla dni powszednich i weekendów, z poprawką na temperaturę. Produkcję paneli bierze z Solcast albo z Forecast.Solar i poprawia ją o to, jak prognoza sprawdzała się w ostatnich dwóch tygodniach. Jeśli podasz cenę baterii i liczbę cykli, planer dolicza też koszt jej zużycia i nie ładuje ani nie sprzedaje, gdy to się nie opłaca.

Na karcie widać przepływ energii na żywo, plan, bilans w złotych, raport miesięczny i stan baterii. W zakładce „Zysk i log” jest porównanie kosztów: tak jak jest, bez baterii i z baterią bez planera, oraz to, jak trafne były prognozy. Jest też zakładka z dodatkowymi urządzeniami, których liczniki kWh integracja potrafi sama znaleźć w Home Assistancie. Wybrane urządzenia (np. bojler) EMS może sam włączać przy nadwyżce z paneli albo w najtańszych godzinach, jeśli na to pozwolisz.

Powiadomień jest ponad trzydzieści rodzajów. Każdy włączasz osobno, można ustawić ciszę nocną i podsumowania dzienne, tygodniowe i miesięczne.

Parametry falownika, strefy czasowe, alarmy, kopie ustawień i autotest są w Diagnostyce, za hasłem. Autotest sprawdza na żywo dane z falownika, prognozę, ceny i urządzenia i daje raport do skopiowania. Problemy, które trwają dłużej (brak danych z falownika, brak ceny, brak prognozy), pojawiają się też w Ustawienia, Naprawy.

## Czego potrzebujesz

Home Assistanta w wersji 2024.11 lub nowszej (tyle wpisałem w `hacs.json`, na starszych nie sprawdzałem) i hybrydowego falownika Deye z loggerem Solarman. Falowniki Sofar z magazynem (G3 i hybrydowe) są obsługiwane eksperymentalnie: na start EMS tylko zapisuje w dzienniku, co by ustawił, a zapis włączasz sam, gdy to sprawdzisz. Falownik możesz podłączyć przez integrację ha-solarman albo bezpośrednio do loggera, ale to drugie jest na razie eksperymentalne. Reszta jest opcjonalna: ceny z RCE lub Pstryka, prognoza PV i encja pogody.

## Instalacja

Przez HACS, jeśli repozytorium jest publiczne (HACS nie pobiera z prywatnych):

1. W HACS otwórz menu ⋮ i wybierz „Niestandardowe repozytoria”.
2. Wklej adres tego repozytorium i jako typ wybierz „Integracja”.
3. Znajdź „EMS komp-dec” i kliknij „Pobierz”.
4. Zrestartuj Home Assistanta.

Ręcznie, co działa także z prywatnego repozytorium:

1. W zakładce Releases pobierz `bms_komp_dec.zip` z najnowszego wydania.
2. Rozpakuj go do `/config/custom_components/bms_komp_dec/`. W archiwum od razu są pliki integracji, bez dodatkowego folderu.
3. Zrestartuj Home Assistanta.

## Pierwsze uruchomienie

1. Wejdź w Ustawienia, Urządzenia i usługi, Dodaj integrację i wybierz „EMS komp-dec”.
2. Wybierz „Kreator: falownik + planer w jednym”. Doda falownik (albo użyje tego z ha-solarman), poczeka na pierwsze odczyty i dopasuje encje. Przez pierwsze kilkadziesiąt sekund falownik może jeszcze nie odpowiadać, to normalne.
3. Po instalacji zapis do falownika i automatyczne stosowanie planu są wyłączone. Włączasz je sam, kiedy będziesz gotowy. Przełącznik „Auto-stosowanie: tylko podgląd” pokazuje, co plan by zrobił, bez zapisu do falownika.
4. Dodaj kartę na pulpit: tryb edycji, „Dodaj kartę”, „Centrum Energii” (typ `custom:bms-panel-card`). Zasób z kodem karty integracja dodaje sama.

## Aktualizacja

W HACS pojawi się powiadomienie o nowej wersji. Ręcznie zrób kopię zapasową, usuń stary folder `bms_komp_dec`, rozpakuj nową wersję i zrestartuj Home Assistanta. Potem odśwież przeglądarkę (Ctrl+F5, w aplikacji na telefonie wyczyść pamięć podręczną), żeby nie została stara karta.

Co się zmieniło w kolejnych wersjach, jest w [CHANGELOG.md](CHANGELOG.md).

## Gdy coś nie działa

Uruchom autotest w Diagnostyce i skopiuj raport. Możesz też pobrać plik diagnostyczny: Ustawienia, Urządzenia i usługi, EMS komp-dec, menu ⋮, „Pobierz diagnostykę”. Adres i numer seryjny falownika oraz usługa powiadomień są w nim ukryte.

## Uwaga

Integracja steruje falownikiem i magazynem energii. Używasz jej na własną odpowiedzialność, więcej w pliku [LICENSE](LICENSE). Na początek zostaw zapis do falownika wyłączony i zobacz, co proponuje plan.

## Licencja

Wszelkie prawa zastrzeżone. Możesz zainstalować integrację u siebie do użytku osobistego, ale bez zgody autora nie wolno jej kopiować, przerabiać na dalsze udostępnianie ani używać komercyjnie.

Kod w `custom_components/bms_komp_dec/direct/` pochodzi z projektów ha-solarman i pysolarman (MIT) oraz umodbus (MPL-2.0) i ma własne licencje, które leżą obok w plikach `LICENSE-*.txt`. Biblioteki Chart.js 4.4.1 i chartjs-adapter-date-fns 3.0.0 (MIT) są dołączone w `frontend/vendor/`, dzięki czemu wykresy działają bez dostępu przeglądarki do internetu.

## Testy

W folderze `tests/` są testy logiki (Python, z atrapami Home Assistanta) i testy karty w przeglądarce (Playwright). Na GitHubie uruchamiają się same przy każdej zmianie. Lokalnie: `python tests/run_python.py` oraz `node tests/run_ui.js` (wymaga pakietu `playwright` i przeglądarki Chromium).

## Wydanie nowej wersji

Numer wersji musi być taki sam w `manifest.json`, `const.py`, w `CARD_VERSION` w `frontend/bms-panel.js` i w `install.version` w plikach `frontend/bms-*.js`. Potem wystarczy utworzyć na GitHubie wydanie z tagiem `vX.Y.Z` (albo `X.Y.Z`), a akcja sprawdzi zgodność numerów i doda do niego `bms_komp_dec.zip`.
