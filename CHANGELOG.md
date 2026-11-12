# EMS komp-dec — zmiany po 0.9.3 (jeszcze niewydane)

## Poprawki
- **Zatwierdzone godziny nie uruchamiały okna, gdy przełącznik zestawu był wyłączony**: auto-stosowanie i ręczne zatwierdzenie propozycji zmieniały tylko godziny Start/Stop, a przełączniki „Ładowanie z sieci (zestaw 1/2)” i „Sprzedaż z baterii (zestaw 1/2)” są domyślnie wyłączone — okno nigdy nie startowało. Teraz EMS włącza przełącznik zestawu, którego godziny zapisał (tylko gdy okno jest kompletne). Sprzedaż włączana jest wyłącznie przy braku zakazu sprzedaży (import z sieci, bilans arbitrażu — bateria naładowana więcej niż wyprodukowało PV, tryb burzowy); w razie zakazu EMS pisze to w dzienniku i nie włącza. Cofnięcie auto-stosowania przywraca też wyłączenie tych przełączników.
- **Ładowanie z sieci nie działało przy zablokowanym prądzie ładowania baterii (0 A)**: „Battery Max Charging Current” = 0 (blokada ładowania z PV, np. po oknie eksportu PV) blokuje ładowanie z każdego źródła, także z sieci. EMS przy starcie okna i przy „Wymuś ładowanie z sieci” przywraca prąd ładowania, a zabezpieczenie robi to też w trakcie trwającego okna (z powiadomieniem).
- **Pasek zakładek na dole, same ikony**: zamiast paska z emoji na górze — pasek przyklejony do dołu okna z ikonami liniowymi (SVG), bez tła; treść przy dolnej krawędzi łagodnie znika, więc ikony są czytelne. Aktywna zakładka świeci i ma kropkę, alarm w Diagnostyce — czerwoną kropkę. Na telefonie same ikony (nazwa w podpowiedzi), na komputerze ikony z nazwami, wyśrodkowane. Powrót do starego układu: Diagnostyka → Tryby → „Pasek zakładek na górze” (dla wszystkich użytkowników).
- **Zysk w złotówkach przy propozycjach**: sprzedaż z baterii, doładowanie w oknie dziennym i blokada PV pokazują szacowany zysk (np. „+1,51 zł”), a okno propozycji — sumę. Nocne ładowanie z sieci ma plakietkę „wymagane do rana” (to zabezpieczenie, nie zysk). Propozycje, których plan nie przewiduje, są zwinięte w „Nie planuję (N)”. Także w dzwonku „Do decyzji”.
- **Ostrzeżenie o wyłączonym zestawie** (zakładka EMS): gdy zestaw ładowania z sieci lub sprzedaży ma ustawione godziny, a przełącznik jest wyłączony, panel mówi, że okno nie wystartuje, i daje przycisk „Włącz”.
- **Plan wyłącza zestaw sprzedaży, gdy sprzedaży nie przewiduje** (przy włączonym auto-stosowaniu): nieopłacalna sprzedaż (np. mało PV) albo zakaz arbitrażu nie wykona się już o starych godzinach. Zestaw włącza się z powrotem, gdy plan znów zaproponuje sprzedaż; nie dotyczy braku danych (niska pewność), podglądu ani trwającej sprzedaży. Zestawy wyłączone ręcznie nie są włączane przez plan. „Cofnij auto-stosowanie” przywraca stan.
- **Mniej, a lepszych propozycji planera**:
  - *Sprzedaż z baterii przy małej produkcji PV*: koszt odtworzenia sprzedanej energii liczony realnie — z PV tylko w tej części, którą PV faktycznie odrobi w ciągu doby (nadwyżka ponad zużycie domu), resztę wyceniamy po cenie zakupu z sieci. Im mniej PV odrobi, tym wyższa wymagana marża (do 2×). Zimą, gdy PV nie uzupełni baterii, sprzedaż „na styk” już się nie pojawia.
  - Minimalna sprzedaż: ≥ 1,5 kWh i zysk ≥ 0,50 zł (drobne okna odpadają). Doładowanie południowe: zysk ≥ 0,30 zł (wcześniej 0,10 zł). Nocne ładowanie „na styk” (< 0,5 kWh do doładowania) jest pomijane.
  - Propozycja różniąca się od bieżących godzin o ≤ 15 min (start i stop) nie wymaga zatwierdzania; propozycje o niskiej pewności nie są proponowane do zastosowania.

# EMS komp-dec — zmiany w 0.9.3 (z 0.9.2)

## Prognozy: codzienne uczenie i samostrojenie
- **Prognoza zużycia**: współczynniki temperatury i sezonu są przeliczane codziennie (wcześniej tylko przy starcie HA). Raz na dobę EMS sprawdza kilkadziesiąt wariantów modelu (waga ostatnich dni, wpływ tego samego dnia tygodnia, siła poprawki temperatury, szybkość korekty błędu) na ostatnich 30 dniach — prognoza dnia X liczona tylko z danych sprzed X — i wybiera wariant, który byłby dokładniejszy o co najmniej 3%. Wynik widać pod tabelą „Ostatnie 14 dni”.
- **Prognoza PV**: okno uczenia współczynnika (7 / 14 / 30 dni, mediana albo średnia ważona wiekiem) jest wybierane osobno dla każdego dnia do przodu tym samym testem wstecz. Notatka pod tabelą trafności w „Zysk i log”.

## Sprzedaż i zakup energii
- Tabela ma kolumny: Dziś, Tydz. (od poniedziałku), Miesiąc, Poprz. m., Rok (zamiast „Razem”). Usunięty wiersz średnich cen. Kwoty w zł podane raz w nagłówku.


## Oszczędności: prostsze opisy
- Kafelki „Oszczędności” mają zrozumiałe nazwy: „Zapłaciłeś”, „Bez baterii zapłaciłbyś”, „Z samą baterią (bez EMS)”, „Zaoszczędziłeś”, „Z tego zasługa EMS”; krótszy opis pod spodem (3 porównywane sytuacje).

## Poprawki
- Ostrzeżenie „okno ładowania trwa, a bateria się nie ładuje” działa tylko w zaplanowanym oknie (nie ostrzega, gdy TOU jest wyłączony na stałe).

# EMS komp-dec — zmiany w 0.9.2 (z 0.9.1)

## Moc ładowania z sieci i ochrona przyłącza
- Dwa nowe ustawienia w zakładce EMS (każdy ustawia własne wartości, domyślnie 0 = wyłączone, EMS niczego wtedy nie zapisuje):
  - **Moc ładowania baterii z sieci (kW)** — sufit. EMS wpisuje do falownika Deye odpowiedni prąd w encji „Battery Grid Charging Current” (kW ÷ napięcie baterii), a plan liczy okna ładowania z tą mocą (niższa moc = dłuższe okno).
  - **Limit poboru z sieci (kW)** — ochrona przyłącza. Gdy dom i ładowanie razem przekraczają limit, EMS co ok. 10 s zmniejsza prąd ładowania z sieci (nie niżej niż 5 A), a gdy jest zapas — przywraca go do sufitu albo do wartości sprzed redukcji. Gdy limit jest przekroczony mimo to (np. samo zużycie domu), dostajesz powiadomienie „Przekroczony limit poboru z sieci”. Reakcja nie jest natychmiastowa, więc krótki szczyt nadal możliwy.
- Działa tylko na Deye. Sufit i limit są zwykłymi encjami `number` (m.in. do użycia w automatyzacjach).

## Urządzenia
- **Oszczędzanie energii przy niskim SOC**: ustawienie „wyłączaj urządzenia poniżej SOC” (EMS → Moc ładowania z sieci i ochrona przyłącza; 0 = wyłączone). Gdy SOC jest poniżej progu przez 5 minut, EMS wyłącza urządzenia z przełącznikiem (przy włączonym „Sterowaniu urządzeniami”), a po odbiciu SOC o 5 punktów włącza z powrotem te, które wyłączył. Przy każdym urządzeniu jest pole „Nie dotyczy oszczędzania energii”. Ręczne włączenie w trakcie oszczędzania jest szanowane do końca dnia. Nowe powiadomienie „Oszczędzanie energii”.
- **Ukrywanie zakładki Urządzenia**: Diagnostyka → Tryby → „Ukryj zakładkę Urządzenia” (dla wszystkich użytkowników; dane i sterowanie działają dalej).

## Poprawki
- **Ładowanie z sieci zatwierdzone w trakcie okna nie włączało się** (np. propozycja 05:00–06:00 zatwierdzona o 05:13): reguły łapały tylko dokładną minutę startu. Teraz start jest nadrabiany raz na okno (także po restarcie HA); gdy okno trwa, a bateria się nie ładuje, przychodzi ostrzeżenie z progiem startu i prądem z falownika.
- Propozycja okna ładowania z sieci przy niemal zerowym doładowaniu („Doładuj ~0.0 kWh”) ma teraz uczciwy opis: okno ma tylko utrzymać SOC przy celu, a nie doładować.
- Odrzucona propozycja jest zapominana, gdy plan przestaje ją proponować, więc ta sama godzina zaproponowana ponownie za kilka dni znów trafi do decyzji (wcześniej mogła zostać ukryta na stałe).

## Dzwonek
- Okno dzwonka wyskakuje samo na środku ekranu, gdy przyjdzie nowe powiadomienie albo plan zaproponuje nową zmianę godzin (raz na dane zdarzenie — przeglądarka pamięta, co już pokazano). Kliknięcie dzwonka nadal otwiera i zamyka okno ręcznie.
- Propozycje oznaczone „POMIJAM” nie są już pokazywane w oknie — widać tylko to, co wymaga decyzji.

# EMS komp-dec — zmiany w 0.9.1 (z 0.9.0)

## Dzwonek: propozycje i powiadomienia w panelu
- W nagłówku karty jest dzwonek 🔔 z licznikiem (propozycje do decyzji + nieprzeczytane powiadomienia). Otwiera arkusz „Do decyzji (N)”.
- Każda propozycja planu (pary START/STOP razem) ma znacznik ZMIENIAM / POMIJAM, zmianę „było → będzie” i rozwijane „Dlaczego”. Przyciski **Potwierdź** (zapisuje godziny) i **Odrzuć** działają osobno dla każdej propozycji — nie ma przycisków zbiorczych.
- Odrzucona propozycja jest zapamiętana po stronie integracji (do czasu, aż plan zaproponuje inną godzinę) — nie wróci w panelu, nie zastosuje jej auto-stosowanie i nie będzie liczona w powiadomieniu o nowej propozycji.
- Pod propozycjami skrzynka powiadomień: podsumowania, alarmy/błędy i informacje (zapamiętywane 14 dni, max 60), z oznaczaniem jako przeczytane, usuwaniem i czyszczeniem. Nowa usługa `bms_komp_dec.inbox_action`.

## Poprawki
- **„Trwa tanie okno do 06:00” w niedzielę o 7:53.** Weekendowa tania taryfa trwa od soboty do poniedziałku do 6:00, a komunikat podawał samą godzinę, więc czytała się jak godzina z przeszłości. Teraz koniec okna ma nazwę dnia („do jutra 06:00”, „do poniedziałku 06:00”) — na karcie i w powiadomieniu o niskim SOC; okno, które zaczyna się i kończy w różne dni, jest opisane jako „od … do …”.

## Prognoza PV: korekta na wszystkie dni
- **Osobny współczynnik dla każdego dnia do przodu (dziś, jutro, za 2…6 dni).** Rano EMS zapisuje prognozę PV na 7 dni i po fakcie porównuje ją z wykonaniem, więc „jutro” i „za 5 dni” mają własne poprawki. Dla horyzontu bez własnych danych używa najbliższego krótszego. Korekta to mediana (odporna na pojedynczy zepsuty dzień) z 30 dni, w granicach 0,5–1,4; pełną wagę ma od 10 dni z danymi, minimum 5 dni.
- **Kształt godzinowy.** Stały wzorzec błędu (zacienienie, kąt paneli, horyzont — np. rano za dużo, po południu za mało) jest uczony osobno dla każdej godziny; suma dnia zostaje zgodna ze współczynnikiem dnia.
- **Poprawka „na żywo” dla dzisiejszego dnia.** Po kilku godzinach produkcji EMS porównuje wykonanie z prognozą z ostatnich 3 godzin i koryguje resztę dnia; wpływ słabnie z odległością godziny.
- **Dni z ucięciem produkcji nie uczą modelu.** Gdy bateria jest pełna i nie ma eksportu, falownik ogranicza PV do zużycia, więc „wykonanie” nie mówi nic o prognozie. Takie godziny i dni są pomijane.
- **Karta pokazuje prognozę po korekcie** (kafelki pogody, paski planu, wykresy godzinowe), z zakresem (Solcast p10–p90 albo typowy błąd z historii) i podpowiedzią z wartością surową.
- **Nowe ustawienie „Ostrożność prognozy PV w planie”** (0–100%, domyślnie 0): planer może liczyć z wartością bliższą wersji pesymistycznej.
- **Zakładka „Zysk i log” → Trafność prognoz:** błąd osobno dla każdego dnia do przodu, także po korekcie (z prognoz faktycznie wydanych po korekcie, więc pokazuje, czy korekta pomaga).
- Model uczy się od zera dla dni +1…+6, bo wcześniej nie zapisywano prognoz na dni przyszłe. Pełna korekta pojawi się po kilkunastu dniach. Prognozy nie da się zrobić „idealną”: błąd pogody rośnie z horyzontem, a zakres na karcie to pokazuje.

## Zabezpieczenia sprzedaży
- **Blokada sprzedaży według energii z całego dnia.** Dotychczasowa blokada patrzyła tylko na chwilową moc importu (domyślnie 2000 W w momencie startu sprzedaży). Nowe ustawienie „Blokada sprzedaży — import z sieci dziś” (domyślnie 3 kWh, 0 = wyłączone): gdy dziś z sieci pobrano więcej, sprzedaż z baterii jest wstrzymana do końca dnia — zarówno start z harmonogramu, jak i przycisk „Sprzedaż 6000W”. Liczy się licznik falownika, a gdy go brak — księga rozliczeń. Plan 24 h oznacza wtedy propozycje sprzedaży jako pominięte z powodem, zamiast obiecywać sprzedaż, której blokada i tak nie wykona. Czujnik „sprzedaż zablokowana importem” zapala się także od tej blokady. Blokada chwilowa (W) zostaje bez zmian i można ją wyłączyć ustawieniem 0.

# EMS komp-dec — zmiany w 0.9.0 (z 0.8.8)

## Powiadomienia
- **Podsumowanie dnia nie przychodziło, bo było domyślnie wyłączone.** Teraz podsumowanie dnia (21:00) i tygodnia (niedziela 20:00) są domyślnie włączone. Kto je wcześniej świadomie ustawił w konfiguratorze, zachowuje swoje ustawienie. Gdy podsumowanie jest wyłączone, w dzienniku EMS pojawia się wpis z przyczyną zamiast ciszy. Telefon dostaje je tylko przy ustawionej usłudze `notify` w konfiguracji EMS, w przeciwnym razie powiadomienie jest tylko w HA.
- **Nowe powiadomienie „Okno arbitrażu jutro”** (domyślnie włączone, raz na dobę): gdy jutro da się kupić tanio i sprzedać drożej po stracie cyklu z zyskiem powyżej progu (domyślnie 0,30 zł/kWh), podaje godziny, ceny i zysk z 1 kWh. Sprzedaż musi wypadać po zakupie.
- **Podsumowanie dnia i tygodnia są bogatsze:** ile kosztowałby prąd bez PV i baterii i ile zaoszczędzono, skąd energia dla domu (PV / bateria / sieć) oraz ile energii pobrano w drogich godzinach.

## Prognoza zużycia: sumy dzienne z licznika falownika
- **Naprawa przepisywania wyniku poprzedniego dnia.** Licznik dzienny falownika resetuje się o godzinie jego zegara, nie zawsze równo o północy. Do resetu pokazuje jeszcze wynik wczorajszy i dalej rośnie, a integracja zapisywała ten odczyt jako dzisiejszy. Realne zużycie rzadko przebijało wczorajszy wynik, więc dzień zostawał z cudzą wartością (w tabeli dwa dni z rzędu z tą samą sumą, np. 32,9). Teraz odczyty sprzed resetu (do 6:00) dopisują się do poprzedniego dnia, a nowy dzień zaczyna się od resetu licznika. Zachowanie przy resecie równo o północy się nie zmienia.
- **Historia z rekordera liczona po cyklach licznika.** Dociąganie historii brało „największą wartość w dobie lokalnej”, co przy resecie po północy przypisywało początkowi doby wynik poprzedniego dnia. Teraz historia dzieli się na cykle licznika (spadek wartości = reset), a do historii trafiają tylko pełne cykle. Niepełne (początek i koniec danych, przerwy w pomiarze) są pomijane.
- **Podejrzane sumy dnia są oznaczane i pomijane.** Dzień z tą samą sumą co dzień wcześniej (do 0,01 kWh, o ile nie jest to stała historia) albo poniżej 25% mediany sąsiednich dni (np. 2,5 kWh przy ok. 28) nie trafia do modelu prognozy, korekty obciążenia, sezonowości ani do średniego błędu. W tabeli „Ostatnie 14 dni” taki wiersz jest przekreślony, z ⚠ i napisem „pominięte”, zamiast absurdalnego „+830%”. Dane nie są kasowane, tylko wyłączone z obliczeń.

## Historia zużycia od zera
- **Świeża instalacja zbiera dane od zera.** Integracja nie importuje już historii zużycia z rekordera HA (wcześniej dociągała do 365 dni, co przy dziwnych licznikach dawało nierealne dni). Pierwsza prognoza zużycia pojawia się po 5 pełnych dniach, profil godzinowy po 3. Do tego czasu planer działa bez prognozy zużycia. Import można przywrócić stałą `BACKFILL_FROM_RECORDER` w `load_forecast.py`. Już zapisane dane zostają bez zmian — można je skasować w karcie: **Diagnostyka → Zaawansowane → „Wyczyść historię zużycia”** (z oknem potwierdzenia; encja `button.bms_wyczysc_historie_zuzycia`: dni, profile godzinowe, historia prognoz i sezonowość; zbieranie startuje od zera).

## Karta
- **Pod tabelką sprzedaży i zakupu:** wiersze „Bez PV i baterii” i „Oszczędzam” (szacunek: zużycie × średnia cena zakupu), pasek „Skąd energia dla domu dziś” (PV bezpośrednio / bateria / sieć) i udział poboru z sieci w drogich godzinach w tym miesiącu. Wszystko to szacunki z dziennych liczników; import ładujący baterię zawyża udział sieci.
- **Tabelka** „Sprzedaż i zakup energii”** pod paskiem „Sieć”: ile sprzedałem i kupiłem w zł (dziś / miesiąc / razem), saldo i średnie ceny sprzedaży i zakupu. Dane z księgi rozliczeń (nowy atrybut `sums` sensora „EMS Bilans dziś”); ze starszą integracją tabelka się nie pokazuje.
- **Logo Komp-Dec** w nagłówku karty zamiast napisu „Centrum Energii” (pliki w `assets/`).
- **Tabela cen zakupu:** kolory odwrócone względem sprzedaży (najtańsza godzina zielona, najdroższa czerwona).
- **Wykresy godzinowe dziś i jutro:** wartości w Wh nad słupkami (poziomo na szerokim ekranie, pionowo na wąskim).

# EMS komp-dec — zmiany w 0.8.8 (z 0.8.7)

## Sprzedaż z baterii
- **Czytelne przyczyny, gdy sprzedaż nie jest planowana.** Planer próbuje okien 3 h, 2 h i 1 h. Dotąd w komunikacie zostawała przyczyna pierwszej (najdłuższej) próby, co bywało mylące. Teraz widać przyczynę najkrótszego okna, a dłuższe są wymienione obok, np. „okno 1 h: po sprzedaży 18–19 (~5,0 kWh przy 5,0 kW) bateria spadłaby do ~12% przed świtem — brakuje ~0,8 kWh (dłuższe okna też odpadły — …)”. W planie na karcie zamiast ogólnego „brak opłacalnych godzin (lub brak pełnych cen RCE)” pojawia się ta konkretna przyczyna.
- **Obniżona moc sprzedaży.** Gdy zapas energii nie wystarcza na pełną moc w najkrótszym oknie, planer nie odrzuca już okna, tylko planuje sprzedaż mniejszą mocą (krok 0,1 kW, minimum 0,5 kW i co najmniej 1 kWh), tak by bateria nie zeszła poniżej progu nocnego przed świtem. Moc jest zapamiętywana z planu i przy starcie sprzedaży komenda używa niższej wartości (nigdy wyższej niż „Moc sprzedaży” z ustawień). Okno z pełną mocą znosi wcześniejsze ograniczenie. Przełącznik „Obniżaj moc sprzedaży do zapasu energii” (domyślnie włączony); po wyłączeniu zostaje dawne zachowanie. Plan na karcie pokazuje dopisek „moc obniżona do X kW”. Nie sprawdzono na prawdziwym falowniku.

## Plan i powiadomienia
- **Jedna kafelka „Bateria”** zamiast „Do pełnego naładowania” i „Do rozładowania”: ładuje się — kiedy będzie pełna; zaplanowane ładowanie z sieci — kiedy startuje i w jakim oknie; rozładowanie — za ile dojdzie do progu falownika, wraz z ostrzeżeniem, gdy dojdzie do niego przed startem ładowania; naładowana — na jak długo wystarczy. Dawna prognoza „do pełna z PV” przy rozładowującej się baterii już się nie wyświetla.
- **Nowe powiadomienie „Plan: bateria dojdzie do progu”.** Gdy plan 24 h przewiduje zejście SOC do progu odcięcia falownika w ciągu 16 godzin (mimo zaplanowanego ładowania i sprzedaży), dostajesz wiadomość z godziną i powodem braku ładowania z sieci. Domyślnie włączone, odstęp 12 h; ustawiasz w Diagnostyka → Powiadomienia.
- **Trafność prognoz.** Integracja zapamiętuje rano prognozę dnia (zużycie, PV), a po 23:00 porównuje ją z faktem. Pod wykresem planu widać średni błąd z ostatnich 7 dni oraz stałe odchylenie („zużycie ±8% (zwykle zawyżona o 5%), PV ±23%”). Dane gromadzą się od pierwszej doby po aktualizacji.
- **Dziennik decyzji planu.** W dzienniku pojawiają się wpisy „Plan: …” za każdym razem, gdy decyzja planu się zmieni (zaplanowano ładowanie / sprzedaż, zmienione godziny, pominięto) wraz z powodem. Bez wpisów przy każdym przeliczeniu.
- **Korekta planu o bieżące zużycie domu** (z wersji roboczej): średnia z ok. 15 minut koryguje bieżącą godzinę i dwie następne (wagi 100/60/30%), z ograniczeniami; przełącznik „Korekta planu o bieżące zużycie domu”.

## Zmiana czasu
- Sprawdzone doby 23 h (28.03.2027) i 25 h (25.10.2026): ceny, prognoza PV i taryfa trafiają na właściwe godziny zegarowe, plan nie zgłasza błędów. W dobie wiosennej nieistniejąca godzina 02:00 nie ma ceny (planer traktuje ją ostrożnie).
- **Poprawka:** reguły harmonogramu o 02:xx nie wykonywały się w wiosenną zmianę czasu (godzina nie istnieje, więc np. STOP ładowania o 02:00 nigdy nie zadziałałby). Teraz wykonują się tuż po skoku (03:00). Jesienią, gdy godzina 02:xx się powtarza, reguła wykonuje się tylko w pierwszym przejściu (wcześniej chroniła przed tym tylko przypadkowa blokada 90 s).

## Testy
- Nowe: test_salefit (26 sprawdzeń), test_planfloor (17), test_accuracy (28), test_plandecisions (16), test_dst_rules (26), battery_tile_test, sale_reason_test, accuracy_ui_test. Każdy sprawdza także, że po celowym uszkodzeniu kodu przestaje przechodzić. Zmieniony test „sprzedaż pominięta, gdy nie starczy do świtu” — dziś dotyczy trybu z wyłączoną obniżoną mocą.

# EMS komp-dec — zmiany po 0.8.7 (opis roboczy, wchodzi do 0.8.8)

- **Jedna kafelka „Bateria” zamiast „Do pełnego naładowania” i „Do rozładowania”.** Pokazuje to, co ważne w danej chwili: gdy bateria się ładuje — kiedy będzie pełna; gdy jest zaplanowane ładowanie z sieci — kiedy startuje (godzina z planu 24 h, czas do startu, okno); gdy się rozładowuje — za ile dojdzie do progu falownika; gdy jest naładowana — na jak długo wystarczy. Jeśli bateria zejdzie do progu przed startem zaplanowanego ładowania, kafelka ostrzega. Dawna prognoza „do pełnego naładowania z PV” (wprowadzająca w błąd przy rozładowującej się baterii) już się nie wyświetla.
- **Plan reaguje na bieżące zużycie domu.** Dotąd planer liczył tylko z profilu godzinowego i tempa dnia. Teraz porównuje zużycie z ostatnich kilkunastu minut (średnia krocząca, więc włączony na chwilę czajnik nic nie zmienia) z tym, czego oczekiwano, i koryguje bieżącą godzinę oraz dwie następne (waga 100%, 60%, 30%). Korekta jest ograniczona (w górę do +4 kW, w dół najwyżej o połowę), działa dopiero po 10 minutach ciągłych pomiarów i pomija odchylenia poniżej 0,3 kW (i 25%). Pod wykresem planu widać, że zużycie zostało skorygowane. Przełącznik „Korekta planu o bieżące zużycie domu” (domyślnie włączony).

# EMS komp-dec — zmiany w 0.8.7 (z 0.8.5; wersja 0.8.6 nie została wydana, jej zmiany są tutaj)

## Falowniki Sofar (eksperymentalne, na start w trybie próbnym)
- **Rozpoznawanie marki** po opcjach trybu pracy: Deye (bez zmian), **Sofar G3** (HYD 5–20KTL-3PH, HYD 3–6K-EP — profile `sofar_g3`, `sofar_g3hyd`) i **Sofar hybrydowy** (HYD 3–6K ES, ME3000SP — profil `sofar_hybrid`). Kreator dobiera encje Sofara z profili ha-solarman jak dotąd.
- **Sofar G3 — tryb pasywny** (Storage Control Mode + moce: sieci, minimalna i maksymalna baterii): praca normalna → Self Use; ładowanie z sieci → Passive, bateria min = max = +moc ładowania; sprzedaż → Passive, bateria min = max = −moc sprzedaży; blokada ładowania z PV → Passive, bateria min = −moc rozładowania, max = 0. Moce najpierw, tryb na końcu.
- **Sofar hybrydowy** — Work Mode Auto / Timed z oknem ładowania lub rozładowania (00:00–23:59) i mocą; blokada ładowania z PV przez maksymalny prąd ładowania 0 (jak w Deye), „odblokuj” przywraca zapamiętany prąd.
- Stan falownika (czy sprzedaje, ładuje z sieci, ma zablokowane ładowanie z PV) jest odczytywany według marki — zabezpieczenia, reakcja na niskie ceny i auto-stosowanie działają tak samo jak przy Deye.
- **Tryb próbny** (`switch.bms_brand_test_mode`, domyślnie włączony): dla Sofara komendy trafiają tylko do dziennika jako „TRYB PRÓBNY … ustawiłbym …”, bez zapisu. Wyłącz go, gdy kroki w dzienniku są właściwe. Sterowanie Sofarem nie było sprawdzone na prawdziwym falowniku; znak mocy w trybie pasywnym (plus = ładowanie) pochodzi z przykładów ha-solarman i evcc, nie z dokumentacji producenta.
- Sprawdzenie (kreator, autotest) pokazuje markę, encje sterujące Sofara, ich opcje i stan trybu próbnego. Sofar stringowy (bez baterii) — tylko odczyty.
- Nie przeniesione na Sofara: odczyt progu odcięcia baterii z falownika (ustaw ręcznie `number.bms_inverter_floor_soc`), opisy kodów alarmów i strony parametrów w Diagnostyce (są pod Deye).

## Poprawki
- **Ceny RCE przesunięte o 15 minut i „cena na jutro”, której nie było.** Integracja RCE PSE podaje w `dtime` koniec kwadransu. BMS brał go za początek, więc ostatni kwadrans doby (23:45–24:00) trafiał do jutra jako godzina 00–01, a każda godzina była liczona z kwadransem poprzedniej. Teraz początek jest brany z `start_dtime` (albo z `business_date` i `period`) — dotyczy tabeli cen i planera.
- **Kafelek „Do rozładowania”:** zamiast niejasnego „wg prognozy z PV: nie w 2 dni” w nocy druga linia mówi, ile zostanie do słońca: „Do słońca (ok. 08:00) zostanie ok. 24%”, a gdy bateria dojdzie do progu wcześniej — „Przed słońcem (ok. 08:00) dojdzie do 20% ok. 05:30”. Słońce = pierwsza godzina, w której prognoza PV pokrywa prognozę zużycia. W dzień linii nie ma.
- **Podsumowanie dnia mogło zniknąć bez śladu.** Znacznik „wysłano dziś” był ustawiany przed policzeniem treści, więc błąd w liczeniu (np. brak jednej wartości w danych) kasował całą wiadomość i nic nie wracało do końca doby. Teraz wiadomość zawsze wychodzi — w razie błędu z krótkim opisem i wpisem w dzienniku.
- **Autotest sprawdza podsumowanie dnia:** czy jest włączone, na którą godzinę, kiedy ostatnio poszło oraz czy coś blokuje wysyłkę (wyłączony przełącznik „Powiadomienia BMS”, brak usługi notify, cisza nocna, wyłączony telefon dla tego rodzaju).
- **Niższe kafelki pogody na telefonie** (ok. 86 px zamiast ok. 135): ikona (nadal animowana), temperatura i kWh w zwartym układzie, bez zawijania „kWh”.
- **„Aktywne funkcje” tylko włączone i zaplanowane:** wyłączone chipy znikają; włączona funkcja z oknem godzin pokazuje je (np. „Ładowanie (1) 05:00–06:00”), trwająca teraz ma pulsującą kropkę i jest pierwsza, zaplanowana na później — obrys przerywany. Ostrzeżenie „Sprzedaż zablokowana (import)” jest osobnym paskiem i widać je tylko, gdy blokada działa.
- **„Trwa tanie okno do 03:00” w weekend.** Wyszukiwanie końca taniego okna miało limit 48 godzin, więc w sobotę o 03:41 (cały weekend jest tani) kończyło się w poniedziałek o 03:00. Teraz szuka do 8 dni naprzód, więc poprawnie pokaże poniedziałek 06:00, a przed długim weekendem ze świętem także kilka dób.
- **Nazwa: BMS → EMS.** W kartach, powiadomieniach, tytułach, nazwach encji, autotestach, README i licencji. Identyfikatory zostają (domena `bms_komp_dec`, identyfikatory encji `…bms_…`, typ karty `custom:bms-panel-card`), więc aktualizacja nie zrywa niczego i nie trzeba nic konfigurować od nowa. „BMS baterii” w parametrach falownika oznacza układ zarządzania baterią i zostaje bez zmian.
- **Plan przy niskim SOC.** Próg odcięcia falownika jest czytany z jego encji (nie zakładamy żadnej stałej), a plan trzyma nad nim margines jak „margines świtu” (domyślnie 10 pkt, u Ciebie 30%): wieczorna sprzedaż skraca się lub odpada, jeśli rano miałaby zejść niżej. Gdy SOC jest nie więcej niż 5 pkt nad progiem falownika w taniej porze, ładowanie z sieci startuje od bieżącej godziny, a nie dopiero w „najlepszej” (z uzasadnieniem w planie). Ładowanie wykona się samo tylko przy włączonym auto-stosowaniu planu.
- **Plan o 05:18 planował „następną noc”.** W ostatniej godzinie taniego okna planer uznawał, że bateria „wystarczy do rana” (np. „SOC 66% o 06:00”), bo liczył do 06:00 **jutra** (po całym dniu z PV), choć bateria miała 25% i do świtu zostały godziny. Teraz przy SOC tuż nad progiem falownika plan ładuje w tej ostatniej godzinie okna (05:00–06:00), a opis „wystarczy do rana” mówi, na którą dobę patrzy („jutro o 06:00”).

# BMS komp-dec — zmiany w 0.8.5 (z 0.8.4)

## Oszczędności (zakładka „Zysk i log”)
- Nowa sekcja **„💡 Oszczędności”**: koszt energii w trzech wariantach — **rzeczywistość** (zakup − sprzedaż z cenami z każdej godziny), **bez baterii** (dom bierze z sieci to, czego nie pokryje PV) i **bateria bez planera** (ładuje się tylko z nadwyżki PV i oddaje do domu, z tą samą pojemnością, sprawnością, progiem i mocami). Do wyboru: dziś, 30 dni, ten miesiąc, ten rok, od początku; wykres oszczędności dzień po dniu.
- Dane zbiera nowy dziennik godzinowy (co 10 s: zużycie, PV, import, eksport, ładowanie i rozładowanie baterii, średnie ceny). Liczy się **od dnia instalacji tej wersji** — wstecz nie ma danych godzinowych.
- Nowy sensor `sensor.bms_savings` (oszczędność w tym miesiącu wobec braku baterii, w atrybutach dzień / rok i „w tym planer”).

## Trafność prognoz i korekta PV
- Nowa sekcja **„🎯 Trafność prognoz”**: średni błąd prognozy PV (zapisywanej rano, od 6:00) i zużycia (wydanej dzień wcześniej), czy prognoza jest zawyżona czy zaniżona, błąd planu SOC godzina po godzinie i wykresy prognoza / wykonanie z 30 dni.
- **Korekta prognozy PV w planerze:** prognoza jest mnożona przez stosunek wykonania do prognozy z ostatnich 14 dni (co najmniej 5 dni z prognozą ≥ 1 kWh, przy małej liczbie dni ściągana do 1, granice 0,7–1,2). Domyślnie **włączona** — przełącznik `switch.bms_pv_forecast_correction`. Widać ją w „Plan zakłada” na karcie; wykresy prognozy PV pokazują nadal surową prognozę.
- Nowy sensor `sensor.bms_forecast_accuracy` (błąd prognozy PV z 30 dni).

## Koszt zużycia baterii w planerze
- Nowe ustawienia `number.bms_battery_price_pln` (cena baterii) i `number.bms_battery_cycles` (liczba cykli, domyślnie 6000). Koszt = cena / (cykle × pojemność) zł na każdą kWh przechodzącą przez baterię.
- Planer dolicza go przy ładowaniu z sieci (noc i południe, taryfy strefowe i dynamiczne), przy sprzedaży z baterii i w ocenie opłacalności sprzedaży; pomija to, co się nie opłaca, i pisze dlaczego. **Domyślnie cena = 0, czyli bez zmian w działaniu**, dopóki jej nie ustawisz.

## Sterowanie urządzeniami
- W edytorze urządzenia nowa część **„🎛 Sterowanie (opcjonalne)”**: przełącznik urządzenia (`switch` / `input_boolean`) i tryb — **przy nadwyżce PV** (moc urządzenia, od jakiego SOC) albo **w najtańszych godzinach planu** (ile godzin) — oraz dzienny limit pracy.
- Zabezpieczenia: stan zmieniany najwyżej co 10 minut, warunek musi trwać 5 minut; BMS wyłącza tylko to, co sam włączył; po ręcznym przełączeniu nie steruje urządzeniem do końca dnia; przy zaniku sieci nic nie włącza, a włączone przez siebie wyłącza; dzienny limit; po wyłączeniu sterowania wyłącza swoje urządzenia; każda akcja w dzienniku.
- Całość działa tylko przy włączonym **„Sterowaniu urządzeniami”** (`switch.bms_device_control`, przełącznik nad listą urządzeń) — **domyślnie wyłączone**. Na kafelku widać tryb, stan i powód.

## Diagnostyka i naprawy
- **🩺 Autotest** (Diagnostyka, za hasłem): sprawdza na żywo dane z falownika, wpisy kreatora i źródło encji sterujących, prognozę PV (Solcast / Forecast.Solar, suma godzinowa vs dzienna), ceny, wykrywanie zaniku sieci po napięciu L1, urządzenia (encje, przełączniki, czy wyszukiwanie nie podsuwa liczników falownika), plan, zapisane ustawienia i zgłoszenia. Tylko odczyt. Przycisk **„Kopiuj raport”** daje tekst do wysłania. Usługa `self_test` (administrator).
- **Naprawy w HA** (Ustawienia → Naprawy): brak danych z falownika > 10 min, brak ceny sprzedaży > 30 min, brak godzinowej prognozy PV > 2 h, auto-stosowanie przy wyłączonym zapisie do falownika. Zgłoszenia znikają same.
- **Pobierz diagnostykę** (Ustawienia → Urządzenia i usługi → BMS komp-dec → ⋮): konfiguracja, stan, plan, wynik sprawdzenia, dziennik, urządzenia, oszczędności. Adres i numer seryjny falownika, usługa powiadomień i hasła są ukryte.

## Naprawione
- **Ustawienia powiadomień znikały po restarcie HA** (także znaczniki wysłanych podsumowań, przez co po restarcie mogło przyjść drugie podsumowanie dnia). Stan integracji zapisywał się, ale przy wczytaniu brane były tylko klucze znane od wersji 0.6 — teraz wszystkie.
- Podpowiedzi przełączników w edytorze urządzenia nie pokazują przełączników falownika.

## Testy w repozytorium
- Testy logiki (29 plików, atrapy HA) i karty w przeglądarce (40 plików, Playwright) są w `tests/` i uruchamiają się na GitHubie przy każdej zmianie (akcja „Testy”). Lokalnie: `python tests/run_python.py`, `node tests/run_ui.js`.

# BMS komp-dec — zmiany w 0.8.4 (z 0.8.3)

## Urządzenia: wyszukiwanie liczników kWh w Home Assistant
- **Nowy przycisk „🔍 Wyszukaj urządzenia”** w zakładce Urządzenia (administrator). Integracja szuka encji z jednostką Wh / kWh / MWh, grupuje je po urządzeniu HA i do każdego dobiera encję mocy (W / kW) tego samego urządzenia. Gdy urządzenie ma kilka liczników, wybiera całkowity (ze statystykami, bez „dziś / miesiąc” w nazwie) — pozostałe są do wyboru na liście.
- **Propozycja dla każdego urządzenia:** nazwa (z urządzenia HA), pomieszczenie (z obszaru HA), kategoria odgadnięta z nazwy (pralka, bojler, pompa ciepła, ładowarka, lodówka…), aktualna moc, oznaczenia „panel Energia”, „niedostępne”, „bez historii” (encja bez `state_class` — historia sprzed dodania nie zostanie uzupełniona). Nazwę, kategorię, pomieszczenie i encje można zmienić przed dodaniem.
- **Urządzenia z panelu Energia** („Urządzenia indywidualne”) są na początku listy i od razu zaznaczone; ich encja mocy z panelu ma pierwszeństwo.
- **Pomijane:** encje BMS i falowników, liczniki domu z panelu Energia (sieć, PV, bateria) razem z ich urządzeniami, encje z konfiguracji BMS, prognozy PV, kopie liczników z Utility Meter, encje wyłączone i urządzenia już dodane. Pod listą widać, ile czego pominięto.
- **„Dodaj zaznaczone”** zapisuje urządzenia z domyślnymi ustawieniami kategorii (próg pracy, cykle, powiadomienia — do zmiany w „Edytuj”); działa limit 40 urządzeń. Wyszukiwanie niczego nie zapisuje samo — nowa usługa `devices_discover` (tylko administrator) zwraca propozycje.

# BMS komp-dec — zmiany w 0.8.3 (z 0.8.2)

- Dołączone lokalne kopie bibliotek wykresów (Chart.js 4.4.1 i chartjs-adapter-date-fns 3.0.0, licencja MIT) w `frontend/vendor/` — wykres „Przebieg mocy, SOC i cen” działa także wtedy, gdy przeglądarka nie ma dostępu do internetu.
- Działanie integracji i karty bez zmian.

# BMS komp-dec — zmiany w 0.8.2 (z 0.8.1)

- Integracja przygotowana do wydania na GitHubie (repozytorium `decyng11/bms_komp_dec`): manifest z adresem dokumentacji i zgłoszeń, plik `hacs.json`, automatyczne sprawdzanie kodu i budowanie paczki `bms_komp_dec.zip` przy każdym wydaniu.
- Działanie integracji i karty bez zmian względem 0.8.1.

# BMS komp-dec — zmiany w 0.8.1 (z 0.8.0)

Karta, rozpoznawanie encji, jeden kreator „wszystko na raz”, prognoza PV z Forecast.Solar i zużycie z dzisiejszego dnia w planie. Sterowanie falownikiem (komendy, zabezpieczenia) bez zmian; planer zmienia się tam, gdzie opisano niżej.

## Urządzenia (nowa zakładka „🔌 Urządzenia”)
- **Dodawanie bezpośrednio w karcie** (administrator): nazwa, ikona, pomieszczenie i **kategoria z 35 pozycji w 9 grupach** (ogrzewanie i chłodzenie, transport, kuchnia, pranie, woda i basen, elektronika, oświetlenie, warsztat i ogród, inne). Encja mocy (W/kW) i/lub energii (Wh/kWh/MWh) — wystarczy jedna: sama moc → integracja liczy kWh, sam licznik → moc z przyrostów (średnia z 5 min). Kategoria ustawia domyślne: od czego zależy zużycie (temperatura / dzień tygodnia / stałe), czy urządzenie jest elastyczne, czy pracuje cyklami, czy liczyć czuwanie, próg pracy, koniec cyklu i limit ciągłej pracy — wszystko do zmiany. Do 40 urządzeń; zapis w integracji (usługi `devices_get`, `devices_set`), wspólny dla wszystkich urządzeń i działający przy zamkniętej karcie. Nowy sensor `sensor.bms_devices` (moc na żywo).
- **Wykresy 1 dzień / 7 dni / 30 dni / 3 / 6 / 12 miesięcy:** słupki z podziałem na urządzenia i „resztę domu” (godzinowo, dziennie, tygodniowo, miesięcznie). Filtr: wszystkie, kategoria, pomieszczenie albo jedno urządzenie. **Historia sprzed dodania urządzenia** jest uzupełniana ze statystyk długoterminowych Home Assistanta (jeśli encja je zapisywała — encje z `state_class`).
- **Ranking i koszty:** kWh i koszt w zakresie, udział w zużyciu domu, średnia cena za kWh, pobór w czuwaniu (najniższa moc 1:00–5:00) i jego koszt roczny, cykle (liczba, średnie kWh, koszt i czas), skąd energia (PV / bateria / sieć — szacunek z bilansu domu), „do zaoszczędzenia” dla urządzeń elastycznych. Koszt liczony po cenie zakupu z sieci.
- **Porównanie miesięcy** (ten / poprzedni / ten sam rok temu, te same dni), **pomieszczenia**, **mapa godzin** (14 dni × 24 h) dla wybranego urządzenia, **eksport CSV**.
- **Plan dla elastycznych urządzeń:** najlepsze okno w planie 24 h — energia z nadwyżki PV liczona po cenie, którą dałaby jej sprzedaż, reszta po cenie zakupu.
- **Prognoza zużycia z podziałem na duże urządzenia** (≥ 15% zużycia domu, po co najmniej 14 dniach danych): „reszta domu” tym samym modelem + każde duże urządzenie własnym modelem (np. pompa ciepła — zależność od stopniodni). **Zastępuje zwykłą prognozę tylko wtedy, gdy na ostatnich 7 dniach była dokładniejsza** — w zakładce widać, czy jest używana i dlaczego.
- **Powiadomienia (nowa grupa „Urządzenia” w konfiguratorze):** koniec cyklu (czas, kWh, koszt), nietypowa praca (ciągła praca dłużej niż limit, zużycie dnia ponad 2× typowe), „uruchom teraz” (nadwyżka PV przy pełnej baterii albo najtańsza godzina taryfy dynamicznej — raz na dobę na urządzenie), wieczorny plan dla elastycznych urządzeń, nierozpoznany odbiornik w „reszcie domu” (raz w tygodniu), duży pobór przy zaniku sieci (z listą urządzeń). Powiadomienie o zaniku sieci pokazuje też, co teraz najwięcej pobiera. Przy każdym urządzeniu można wyłączyć jego powiadomienia.

## Naprawione: prognoza zużycia zawyżona przy zimnej pogodzie
- **Temperatura i pora roku były liczone dwa razy.** Model bierze średnią z ostatnich dni (już zimnych), a potem mnożył ją jeszcze przez poprawkę temperaturową liczoną od „ciepłego” poziomu i przez współczynnik sezonowy. W listopadzie dawało to prognozę wyższą o kilkadziesiąt procent (np. 13,3 kWh przy typowych 8–10). Teraz poprawki są **względne**: prognoza rośnie tylko wtedy, gdy prognozowany dzień jest zimniejszy niż dni, z których policzono średnią (i analogicznie dla miesiąca). Korekta obciążenia modelu (×0,88) przeliczy się sama w ciągu kilku dni.

## Powiadomienia: konfigurator (Diagnostyka → 🔔 Powiadomienia, za hasłem)
- **Każdy rodzaj osobno:** włącz/wyłącz, gdzie trafia (📱 telefon + HA albo 🏠 tylko HA), jak często najwyżej (od „każde” po „co 7 dni”) i czy może przyjść na telefon w ciszy nocnej. Przy części rodzajów jest próg (np. °C, kWh, zł/kWh, %). Przyciski „wszystkie / żadne” dla grupy, „Domyślne”, „Wyślij testowe”.
- **Cisza nocna** (np. 22:00–7:00, także przez północ): w tym czasie powiadomienia trafiają tylko do HA, a na telefon jedynie rodzaje z zaznaczonym „w ciszy” (domyślnie: alarm falownika, brak danych, zanik sieci, wysoka temperatura baterii).
- **Ustawienia zapisują się w integracji** (usługi `notify_settings_get`, `notify_settings_set`, `notify_test` — tylko administrator), więc działają przy zamkniętej karcie. Główny wyłącznik `switch.bms_notifications_enabled` działa jak dotąd.
- **31 rodzajów w 5 grupach** (domyślne ustawienia istniejących powiadomień bez zmian):
  - *Bateria:* niski stan, naładowana do pełna, ładowanie z sieci poniżej celu planu, wysoka i niska temperatura, spadek sprawności cyklu;
  - *Falownik:* alarm (Fxx), brak danych, zanik i powrót sieci, niepotwierdzona komenda, zmiana parametru po zapisie, zadziałanie zabezpieczenia, duży pobór z sieci;
  - *Ceny i plan:* brak cen RCE na jutro, niskie/ujemne ceny jutro, wysoka cena jutro (z planem sprzedaży), brak cen zakupu przy taryfie dynamicznej, brak prognozy PV, słaba prognoza PV (z planowanym ładowaniem z sieci), zużycie dziś ponad prognozę, codzienna propozycja harmonogramu, zmiana przez auto-stosowanie, plan niedostępny, pominięty start harmonogramu;
  - *Działanie:* start/koniec sprzedaży, start/koniec ładowania z sieci, reakcja na niską cenę, tryb burzowy (włączenie i wygaśnięcie);
  - *Podsumowania:* dnia, tygodnia, raport miesięczny.
- **Podsumowania z godzinami do wyboru:** dzienne (domyślnie 21:00: bilans zł, energia, SOC min/max, wykonane komendy, jutro: PV, zużycie i plan), tygodniowe (dzień i godzina; sumy 7 dni, porównanie z poprzednim tygodniem, najlepszy/najsłabszy dzień, sprawność), miesięczne (dzień 1–28 i godzina; raport z porównaniem do poprzedniego miesiąca). Dzienne i tygodniowe są domyślnie wyłączone.
- **Zmienione identyfikatory powiadomień w HA:** `bms_storm_on` → `bms_storm`, `bms_monthly_report` → `bms_summary_monthly`, `bms_schedule_proposal` → `bms_proposal` (ważne tylko, jeśli masz automatyzacje na nie).
- **Kreator instalacji** jest teraz sekcją Diagnostyki widoczną dopiero po podaniu hasła.

## Prognoza PV: Solcast albo Forecast.Solar (uniwersalnie)
- **Forecast.Solar działa w planie i na karcie.** Wcześniej planer i karta czytały prognozę godzinową tylko z atrybutów Solcasta, więc z Forecast.Solar plan liczył tak, jakby nie było słońca (np. „najniższy SOC 20% o 14:00”, pominięta blokada PV). Teraz prognoza godzinowa Forecast.Solar jest pobierana z Home Assistanta (ta sama funkcja, z której korzysta panel Energia), co 10 minut.
- **Kilka połaci** (kilka wpisów Forecast.Solar) jest sumowanych — godzinowo i w sumie dziennej.
- **Solcast ma pierwszeństwo**, gdy jest skonfigurowany; nic się dla niego nie zmienia.
- **Jednostki:** suma dzienna jest przeliczana z Wh / MWh na kWh według jednostki encji.
- **Karty wyglądają tak samo**, ale dane biorą z integracji (atrybuty `pv_hourly_today`, `pv_hourly_tomorrow`, `pv_daily`, `pv_forecast_source` w `sensor.bms_reserve_soc`): kafelki pogody z prognozą PV, „Produkcja PV dziś — rzeczywista vs prognoza”, „Plan dnia”, „Do rozładowania / naładowania”. Napisy „Solcast” zastąpione „prognoza PV” (ze źródłem w nawiasie). Ze starszą integracją karta czyta encje Solcast jak dotąd. Forecast.Solar w darmowej wersji daje tylko dziś i jutro, więc w widoku 7 dni dalsze dni są puste.
- **Diagnostyka:** nowy punkt „Prognoza PV godzinowa” (źródło i dni) z podpowiedzią, gdy jej brak.

## Plan: zużycie z dzisiejszego dnia
- **Godziny do północy liczone z tempa dnia.** Planer brał na każdą godzinę (także dzisiejszy wieczór i noc) prognozę na jutro. Teraz do północy używa tego, co dom zużyje jeszcze dziś: prognoza bieżąca (uwzględnia zużycie od rana) minus zużycie dotychczas, rozłożone według profilu godzinowego. Godziny jutra — jak dotąd z prognozy na jutro. To samo w dynamicznej rezerwie SOC.
- **Profil godzinowy osobno dla dni roboczych i wolnych** (weekendy i święta), gdy jest co najmniej 4 dni danego typu; inaczej profil ze wszystkich dni.
- **Linia „Plan zakłada”** pod wykresem planu: zużycie do północy (z dzisiejszego zużycia albo z profilu), jutro, PV jutro i źródło prognozy. Gdy brak prognozy godzinowej PV na jutro — czerwone ostrzeżenie.

## Karta
- **Nowy wykres bilansu dziennego** w „Bilans w PLN” i w raporcie miesięcznym: słupki z kwotą, daty pod spodem, przerywana linia „narastająco” z sumą w legendzie. Tekst ma stały rozmiar na telefonie i monitorze; przy wielu dniach kwoty są tylko przy najlepszym, najgorszym i ostatnim dniu.

## Ceny Pstryk
- **pstryk-ha-next** (Miosp, `sensor.pstryk_current_price`): czytnik rozumie listy `today_prices` / `tomorrow_prices` z cenami `gross` / `net` (zgodnie z ustawieniem „basis” tej integracji), a wykrywanie znajduje tę encję jako cenę zakupu. Integracje balgerion / kriskomp (`sensor.pstryk_current_buy_price` + `sensor.pstryk_json_buy`) działały i działają — sprawdzone na kształcie danych z ich kodu.

## Kreator „wszystko na raz” (nowe menu: Kreator)
- Jeden przepływ: **falownik → czekanie, aż jego encje się pojawią → dopasowanie encji z walidacją → wpis planera BMS**. Wcześniej trzeba było przejść dwa osobne kreatory.
- **Bezpieczny start:** zapis do falownika wyłączony, automatyczne stosowanie propozycji wyłączone. Włączasz je sam w konfiguracji.
- **Walidacja dopasowania:** sprawdza, że wymagane encje (bateria, PV, sieć, dom, SOC) istnieją, mają właściwą domenę i jednostkę (W / V / A / % / kWh). Błędne pola są wyświetlane z nazwą problemu, a podpowiedzi wskazujące na nieistniejące encje są usuwane zamiast zgadywane.
- Jeśli falownik nie uruchomi się w ciągu 40 s, wpis falownika jest usuwany (nie zostaje martwy wpis), a kreator pokazuje błąd.
- Dotychczasowe wejścia („BMS”, „Falownik”) zostają w menu.

- **Czekanie na prawdziwe odczyty.** Po dodaniu falownika kreator czeka (do 45 s), aż co najmniej 3 główne encje (SOC, PV, dom, bateria, sieć) mają wartość liczbową, a nie `unavailable`/`unknown`. Jeśli falownik jeszcze milczy, pokazuje ekran „Falownik jeszcze nie odpowiada”: „Zatwierdź” sprawdza ponownie (do 20 s) i nie dodaje drugiego wpisu.
- **Pojemność baterii z falownika** (podpowiedź, zawsze do poprawienia): najpierw encja „Battery Capacity” w kWh (działa tak samo dla baterii LV i HV), a gdy jej nie ma — przybliżenie z „Battery Capacity” w Ah × napięcie baterii, wyraźnie oznaczone w opisie jako przybliżenie. Wartości spoza 1–100 kWh są odrzucane.
- **Pole pojemności przyjmuje setne części** (np. 12,56). Wcześniej krok wynosił 0,5 kWh i formularz odrzucał 12,56 jako „Podaj poprawną wartość”.
- **Prognoza PV z Forecast.Solar:** kolejność to Solcast, potem Forecast.Solar (rozpoznawany po integracji i kluczu tłumaczenia, więc działa też z polskimi nazwami encji; warianty „remaining” i „hour” są pomijane). Dotyczy kreatora, nowej instalacji i „Wykryj encje ponownie”, które nie nadpisują prognozy, jeśli wskazana encja istnieje.
- **Diagnostyka:** ostrzeżenie, gdy własny szacunek pojemności z ładowania (co najmniej 3 pomiary) różni się od skonfigurowanej o więcej niż 30%. Pojemność nie jest podmieniana samodzielnie.

## Fazy L1/L2/L3 (falownik 3-fazowy)
- **Wykrywanie wszystkich faz:** napięcie, prąd i moc sieci oraz napięcie, prąd i moc domu dla L1, L2, L3 (18 ról). Wartości są dobierane po jednostce (V / A / W), więc napięcie nie trafia w pole prądu.
- **Poprawione domyślne nazwy L1** (`inverter_grid_l1_current`, `inverter_load_l1_voltage`, `inverter_load_l1_current`) — wcześniej nie pasowały do nazw z profilu Deye, stąd brak rozpoznania nawet L1.
- **Rozstrzyganie 1- i 3-fazowego profilu:** gdy dwa profile mają tyle samo trafień, wygrywa ten, którego liczba faz zgadza się z faktycznie znalezionymi encjami. Wcześniej falownik 3-fazowy bywał opisany jako „Deye hybrydowy 1-fazowy”.
- **Karta pokazuje wszystkie fazy** w szczegółach węzła sieci i domu („Napięcie L1 · L2 · L3” itd.); instalacja 1-fazowa wygląda jak dotąd.
- **Zapasowe liczenie mocy** (gdy łączna moc sieci/domu ≈ 0, a encje faz istnieją): suma mocy faz zamiast iloczynu U×I tylko z L1.

## Naprawione
- **Błąd przy usuwaniu wpisu** (`KeyError: 'bms_komp_dec'` w logu „Error unloading entry”): przy wyładowywaniu wpisu, dla którego dane integracji już nie istniały, wyjątek przerywał usuwanie.

## Karta: „Do rozładowania do X%”
- **Próg z falownika zamiast sztywnych 20%.** Karta bierze próg odcięcia z tego, co integracja już wyznacza: SOC wyłączenia z falownika plus SOC aktywnego programu Time of Use, albo wartość wpisaną ręcznie w „Próg odcięcia baterii w falowniku”. Źródło progu widać w podpowiedzi po najechaniu na nagłówek. Gdy integracja nie podaje progu, karta przyjmuje 20% i pisze „(domyślnie)”.
- **Wynik główny z obecnego poboru.** Czas liczony jest z aktualnego rozładowania baterii; gdy bateria się ładuje, z aktualnego zużycia domu (bez PV). Wcześniej karta liczyła tylko z prognoz, więc przy 631 W zużycia potrafiła pokazać „1 d 17 h”.
- **Prognoza jako druga, mniejsza linia** („wg prognozy z PV: …”), tylko gdy różni się od wyniku głównego. Symulacja uwzględnia zmianę progu w ciągu doby z programami ToU.
- **Nowy atrybut** `inverter_floor_hourly` (24 wartości) w `sensor.bms_reserve_soc`, niezapisywany w historii.

## Czego nie sprawdziłem
- Na prawdziwym HA i falowniku nie uruchamiałem. Testy działają na atrapach Home Assistanta i karty.
- **Forecast.Solar:** dane godzinowe pobieram funkcją `async_get_solar_forecast` z platformy energy Forecast.Solar (sprawdziłem jej kod w aktualnym Home Assistant). Na prawdziwym HA tego nie uruchamiałem; jeśli starsza wersja HA ma inną postać tej funkcji, diagnostyka pokaże „brak prognozy godzinowej”.
- **„Wybrano nieznaną encję”** na ekranie dopasowania: nie znam pewnej przyczyny. Dodane czekanie na odczyty usuwa najbardziej prawdopodobną (kreator szedł dalej przed pierwszym połączeniem z falownikiem), ale nie potwierdziłem tego na prawdziwym HA.
- **Pojemność:** wartość z falownika jest tylko podpowiedzią. Encja w kWh na Twoim falowniku może pokazywać szacunek, który różni się od naklejki baterii — porównaj przed zatwierdzeniem. Przybliżenie Ah × napięcie jest mniej pewne, zwłaszcza dla HV.
- **Kreator:** zakłada, że HA utworzy wpis falownika przez `flow.async_init` i że wpis osiągnie stan „loaded”. Tego nie da się sprawdzić poza prawdziwym HA — to pierwsza rzecz do obejrzenia na serwerze testowym.
- **„Mylenie” encji** zgłoszone przez użytkownika nie zostało odtworzone w całości; poprawiłem to, co znalazłem (jednostki faz, nazwy L1, remis 1-/3-fazowy).
- Pojemność baterii bierze się z `capacity_kwh`; gdy jest zła, wynik ETA będzie zły.

# BMS komp-dec — zmiany w 0.8.0 (z 0.7.0)

Zawiera wszystko z 0.7.0 (falownik dodawany bezpośrednio, eksperymentalnie) i wcześniejszych wersji. **Istniejąca instalacja z taryfą strefową (np. G12w) działa po aktualizacji dokładnie tak samo jak w 0.7.0** — sprawdzone testem porównującym obie wersje na 900 losowych scenariuszach (zero różnic w propozycjach i planie). Nowe funkcje włączasz sam w konfiguracji.

## Ceny zakupu i sprzedaży z innych integracji (Pstryk, RCE PSE, inne)
- **Wspólny czytnik cen** dla sprzedaży i zakupu. Rozumie listy cen godzinowych i 15-minutowych (uśrednia do godziny), w zł/kWh i zł/MWh, ze znacznikami czasu `time` / `start` / `dtime` / `period_start` i cenami `price` / `value` / `rce_pln` / `cena`. Obsługuje m.in. `prices_today` / `prices_tomorrow` / `prices` (obie integracje Pstryk wg ich dokumentacji), `raw_today` / `raw_tomorrow` (Nord Pool) i listy RCE PSE.
- **Ochrona przed pomyleniem stron:** encja, której nazwa wskazuje na zakup (`buy`, `zakup`, `import`, `g12`, `taryf`…), nigdy nie jest zgadywana jako źródło cen sprzedaży. Jeśli sam wskażesz taką encję jako cenę sprzedaży, zostanie użyta.
- **Wykrywanie encji cen:** przy nowej instalacji i przy „Wykryj encje ponownie”, gdy wskazana encja nie istnieje, brana jest pierwsza znana: dla sprzedaży RCE PSE, potem Pstryk; dla zakupu G12w (energy_hub), potem Pstryk.
- **Pstryk (wariant kriskomp):** gdy encja zakupu to `sensor.pstryk_current_buy_price`, pełna lista cen jest brana z `sensor.pstryk_json_buy`. Według dokumentacji Pstryka ta encja jest opcjonalna; jeśli jej nie widzisz, włącz ją w ustawieniach integracji Pstryk.

## Taryfa dynamiczna w planerze
- **Nowe pole „Tryb taryfy”:**
  - **strefowa:** stałe okna szczytu, jak dotąd;
  - **auto:** ceny godzinowe, gdy encja zakupu je podaje i mają w dobie co najmniej 4 różne poziomy; lista G12w z 2 poziomami zostaje strefowa;
  - **dynamiczna:** zawsze ceny godzinowe.
  Istniejące wpisy zostają na „strefowej”, nowe instalacje startują z „auto”. Zmiana: Ustawienia → Urządzenia i usługi → BMS komp-dec → Konfiguruj.
- **Okna szczytu liczone każdego dnia z cen zakupu:** szczyt to godziny droższe niż najtańsze godziny doby po stratach cyklu baterii (+0,05 zł). Drobne skoki ceny (< 10% największego szczytu) są pomijane. Okien jest najwyżej dwa, bo planer ma dwa zestawy sprzedaży i jedno okno południowe. Dzień bez pełnej listy cen (np. jutro przed publikacją) używa okien z konfiguracji.
- **Ładowanie z sieci w najtańszych godzinach przed szczytem**, a nie „tuż przed szczytem”. Cel ładowania uwzględnia zużycie domu między końcem ładowania a początkiem szczytu. Ładowanie jest pomijane, gdy różnica cen nie pokrywa strat cyklu. To samo dotyczy doładowania w południe (zestaw 2).
- **Sprzedaż z baterii:** każdy zestaw bierze okno szczytu z dnia, którego dotyczy, bo jutro okna mogą być inne niż dziś.
- **Bez uczenia „szczyt/noc” z jednej ceny:** przy taryfie dynamicznej planer nie uczy się dwóch cen z bieżącej ceny zakupu; koszty liczy z cen godzinowych.
- **Karta:**
  - tabela cen pokazuje dokładnie te ceny, których używa planer (w zł/kWh), a przy taryfie dynamicznej także drugą tabelę z cenami zakupu;
  - wykres historii używa skonfigurowanej encji ceny sprzedaży zamiast stałej `sensor.rce_pse_cena`;
  - opis decyzji planera mówi, czy taryfa jest dynamiczna.
- **Diagnostyka (kreator):** pokazuje tryb taryfy i źródło cen zakupu. Błąd, gdy tryb jest „dynamiczny”, a encja zakupu nie podaje cen godzinowych.

## Tryb bezpośredni (poprawki do 0.7.0)
- **Odczyt kontrolny po zapisie tylko dla rejestrów czytanych kodem 3.** Około 29 encji w profilach Kstar, Sofar hybrid i Hinen czyta wartość kodem 4 i mogło dostać fałszywe „falownik nie przyjął wartości”. Deye tego nie dotyczyło.
- **Niebezpieczne przyciski z profili** (np. Afore „Factory reset”, „Clear records”, „Restart”; Kstar „Restart”) są domyślnie wyłączone w rejestrze encji. Włączasz je świadomie.
- **Diagnostyka ostrzega** (błąd z instrukcją), gdy encje sterujące planera należą do falownika dodanego bezpośrednio, który ma wyłączony zapis — wtedy komendy BMS nie zmieniają jego ustawień.
- **Odporność na uszkodzone i obce ramki z sieci:** krótkie i błędne ramki są pomijane bez błędów w logu; po powrocie poprawnych odpowiedzi odczyt działa dalej.
- **DNS i listowanie katalogu profili poza pętlą zdarzeń HA** (wcześniej mogły ją na chwilę blokować).
- **Walidacja nazwy profilu** z ustawień wpisu: tylko plik z folderu definicji albo z `custom/`, bez `..` i ścieżek bezwzględnych.

## Poprawki błędów (dotyczą też 0.7.0 i starszych)
- **Stan „nan” / „inf” w encji ceny zakupu** zapisywał się jako nauczona cena taryfy i dawał NaN w planie i na karcie. Teraz takie wartości są odrzucane, także przy wczytywaniu zapisanych cen.

## Bezpieczeństwo — wynik przeglądu
- **Kod:** brak `eval`, `exec`, `pickle`, `subprocess` i podobnych. Pliki YAML są wczytywane bezpiecznie (`safe_load`). Część Python nie łączy się z internetem; w trybie bezpośrednim rozmawia tylko z loggerem (TCP 8899 i rozgłoszenie UDP).
- **Usługi:** magazyn Diagnostyki, kontrola zapisu i kreator wymagają administratora; dane wejściowe są sprawdzane, a magazyn ma limity rozmiaru.
- **Karta:** test ze złośliwym HTML wstrzykniętym we wszystkie encje i odpowiedzi usług przechodzi; nowe tabele cen też.
- **Ryzyka, które zostają (nie da się ich usunąć w samej integracji):**
  - Wykres historii pobiera Chart.js z cdn.jsdelivr.net bez sprawdzania integralności. Diagnostyka ostrzega, dopóki nie wgrasz 2 plików do `frontend/vendor/` (instrukcja w `README.txt` w tym folderze). Nie mogłem ich dołączyć do paczki, bo w moim środowisku pobieranie z npm i CDN jest zablokowane, a nie dołączam plików, których nie potrafię sprawdzić.
  - Hasło Diagnostyki to blokada przed przypadkową zmianą, nie zabezpieczenie: skrót hasła jest w pliku karty, który HA udostępnia bez logowania, a każdy zalogowany użytkownik HA i tak może zmieniać encje falownika. Nie używaj tam hasła, którego używasz gdzie indziej.
  - Protokół Solarman V5 nie ma uwierzytelnienia ani szyfrowania: każde urządzenie w sieci lokalnej może rozmawiać z loggerem. Tak samo jest w ha-solarman.

## Czego nie sprawdziłem
- **Pstryk i RCE PSE:** struktury encji zbudowałem z dokumentacji tych integracji (README), nie z prawdziwych encji. Sprawdź w Diagnostyce wiersz „Taryfa” i tabelę cen na karcie. Jeśli coś się nie zgadza, przyślij atrybuty encji z Narzędzia deweloperskie → Stany.
- **Taryfa dynamiczna:** sprawdzona na danych testowych (ceny podobne do TGE, brak cen jutra, zmiana czasu, dane losowe). Na prawdziwych cenach przez kilka dni nie działała. Zacznij od trybu „auto” z wyłączonym „Auto-stosowaniem”, żeby najpierw oglądać propozycje.
- **Prawdziwe HA, logger i telefon:** nic z tego nie było uruchamiane na prawdziwym sprzęcie. Wszystko sprawdzone na atrapach HA i symulatorze loggera.

## Testy
- **Nowe:**
  - taryfa dynamiczna (56 sprawdzeń, m.in. najtańszy blok ładowania sprawdzany siłowo, SOC o początku szczytu, okna per dzień, dane losowe, wstrzyknięty NaN);
  - równoważność ze starą wersją dla taryfy strefowej (3 × 300 scenariuszy);
  - złośliwy logger (losowe bajty, ucięte ramki, złe sumy, ogromne długości, zalew danych);
  - tabela cen na karcie (w tym próba wstrzyknięcia HTML).
- **Mutacje:** testy wykrywają celowe uszkodzenia nowych funkcji (11 wariantów).
- **Regresja:** planer, karta, tryb bezpośredni, tłumaczenia, fuzz i lint bez nowych błędów. Jedyne znane odstępstwo: „historia alarmów” w `diag_prefix_test`, występuje od wcześniej.

# BMS komp-dec — zmiany w 0.7.0 (z 0.6.8) — EKSPERYMENTALNE

Zawiera wszystko z 0.6.8 (ostrzeżenia o zasobach karty), 0.6.7 (dwa wykresy godzinowe) i wcześniejsze. **Planer BMS i karta działają jak w 0.6.8** — nowością jest opcjonalny tryb, w którym falownik dodajesz bezpośrednio w tej integracji, bez integracji ha-solarman. Jeśli go nie dodasz, nic się u Ciebie nie zmienia (poza dwiema poprawkami z sekcji „Poprawki”).

## Falownik dodawany bezpośrednio (odczyt i zapis)
- **Dodawanie:** Ustawienia → Urządzenia i usługi → Dodaj integrację → BMS komp-dec → menu: „Planer BMS” albo „Falownik połączony bezpośrednio”. Gdy planer BMS już jest, od razu otwiera się formularz falownika. Można dodać kilka falowników (każdy ma własny adres i nazwę), ale planer BMS korzysta z jednego — tego, który najlepiej pasuje do jego ról (SOC, PV, sieć, dom).
- **Formularz:** adres IP loggera (podpowiadany z wyszukiwania UDP w sieci), port (domyślnie 8899), transport (Solarman V5 przez TCP, Modbus TCP, Modbus RTU przez TCP), profil („Auto” albo jeden z 30 dołączonych), „Zezwól na zapis do falownika” oraz zwinięta sekcja opcji dodatkowych (wariant profilu, liczba MPPT, faz i pakietów baterii, napięcie nominalne i żywotność baterii, adres Modbus). Te same pola są w „Konfiguruj” przy wpisie falownika.
- **Wszystkie profile z ha-solarman — 30 plików, bez zmian:** Afore (2MPPT, BNTxxxKTL-2MPPT, hybrid), Anenji hybrid, Astro-Energy micro, Chint CPS SCE-TL, Deye (hybrid, micro, 3-fazowy, string), Hinen hybrid, INVT XD-TL, Kstar hybrid, Maxge string, Megarevo R-3H, Pylontech Force, Renon IFL, Sofar (G3, G3 HYD, hybrid, string), Solarman DTSD422-D3 (licznik), Solis (1P-5G, 3P-4G, 3P-5G, hybrid, S6-GR1P), SRNE ASF, Swatten SIH-TH, TSUN TSOL-MS. Pliki są identyczne z repozytorium ha-solarman (stan z 4.11.2026), własne profile można dodać do `config/custom_components/bms_komp_dec/direct/inverter_definitions/custom/`.
- **Odczyt i zapis przez encje:** sensor, binary_sensor, number, select, switch, time, datetime, button — tak jak w ha-solarman. Dla Deye hybrid to m.in. tryb pracy, prąd ładowania, Time of Use, programy 1–6 (godziny, SOC, ładowanie). Encje mają angielskie nazwy z profilu (jak w ha-solarman po angielsku), więc planer rozpoznaje je tak samo jak encje ha-solarman.
- **Autodetekcja Deye:** typ falownika z rejestru 0x0000 wybiera profil (hybrid / string / micro / 3-fazowy) i ustawia liczbę MPPT, faz i pakietów baterii.
- **Planer:** encje falownika dodanego bezpośrednio są dla wykrywania encji (kreator, „Wykryj encje ponownie”, próg odcięcia baterii) traktowane jak encje ha-solarman.

## Bezpieczeństwo zapisu (różnice względem oryginału ha-solarman)
- **Zapis jest domyślnie wyłączony** i włącza się osobno dla każdego falownika (pole „Zezwól na zapis”). Przy wyłączonym zapisie próba zmiany wartości kończy się czytelnym błędem, a do loggera nie wychodzi żadna ramka zapisu.
- **Odczyt kontrolny po każdym zapisie** (jedno ponowienie po 0,5 s). Jeśli falownik nie przyjął wartości (zakres, tryb, blokada), encja zgłasza błąd z odczytaną i oczekiwaną wartością i **nie pokazuje** wartości, której falownik nie ma.
- **Brak usług „zapisz dowolny rejestr”** — zapis przechodzi wyłącznie przez encje i ich zakresy z profilu.
- **Nic nie zmienia ustawień loggera:** usunięte zostały przełączniki chmury Solarman, trybu pracy loggera, punktu dostępowego i restartu oraz wszystkie żądania HTTP do jego strony. Integracja używa z loggerem tylko portu 8899 i wyszukiwania UDP (adres, MAC, numer seryjny).

## Poprawki (dotyczą też użytkowników bez trybu bezpośredniego)
- **Tłumaczenia kreatora nigdy nie działały:** pliki `en.json`, `pl.json` i `strings.json` leżały obok kodu, a Home Assistant czyta tłumaczenia integracji niestandardowych tylko z folderu `translations/`. Przeniesione tam (po polsku i angielsku); przy okazji dopisane brakujące etykiety 19 pól formularza planera (napięcia, prądy i moce faz, temperatura baterii, PV1/PV2) oraz teksty błędów w oknie „Konfiguruj”. **Po aktualizacji formularze mogą wyglądać inaczej niż dotąd (będą miały opisy zamiast nazw pól).**
- **Sprzątanie starych encji BMS** przy starcie planera usuwałoby każdą encję platformy `bms_komp_dec` bez prefiksu BMS — czyli także encje falownika dodanego bezpośrednio. Teraz je pomija (wykryte przy przeglądzie, zanim trafiło do Ciebie).
- Manifest: dodana zależność `network` (wyszukiwanie loggera po UDP).

## Co musisz wiedzieć przed testem
1. **Logger zwykle przyjmuje jedno połączenie lokalne naraz** (to ogólna wiedza o loggerach Solarman, nie sprawdzona na Twoim egzemplarzu). Na czas testu **wyłącz** wpis ha-solarman dla tego falownika (Ustawienia → Urządzenia i usługi → ha-solarman → ⋮ → Wyłącz), inaczej połączenia będą sobie przeszkadzać.
2. **Nazwij falownik inaczej niż w ha-solarman** (np. „Falownik test”), żeby identyfikatory encji się nie zderzyły (`_2`). Zmieni to ID encji względem Twoich obecnych — ustawienia BMS wskazujące na `sensor.inverter_…` trzeba będzie przestawić (kreator: „Wykryj encje ponownie”).
3. **Kolejność:** najpierw sam odczyt (porównaj kilka wartości z aplikacją falownika), dopiero potem włącz „Zezwól na zapis” i zmień **jedną** mało groźną wartość (np. prąd ładowania baterii), po czym sprawdź ją w falowniku.
4. **Pełny restart Home Assistanta** po wgraniu (zmienił się manifest i dodano nowe pliki).
5. Logi: `logger:` → `logs:` → `custom_components.bms_komp_dec.direct: debug`. Niezgodność po zapisie (falownik nie przyjął wartości) trafia do logu jako ostrzeżenie.
6. Wycofanie: **najpierw usuń wpis falownika**, potem ewentualnie wróć do 0.6.8 — starsza wersja nie zna wpisów falowników i potraktowałaby taki wpis jak drugi planer BMS. Planer BMS nie zależy od wpisu falownika, więc jego usunięcie niczego w planerze nie psuje.

## Czego NIE sprawdziłem (uczciwie)
- **Żadna marka nie była testowana na prawdziwym sprzęcie ani w prawdziwym Home Assistancie.** Warstwa komunikacji została sprawdzona na symulatorze loggera, który napisałem na podstawie kodu klienta ha-solarman — dowodzi, że okablowanie, rejestry, skalowanie i zapis działają zgodnie z tym kodem, ale **nie** że prawdziwy logger i falownik odpowiedzą tak samo. Kreator, rejestr encji i tłumaczenia sprawdziłem na atrapach HA napisanych na podstawie jego kodu.
- Dla wszystkich 30 profili sprawdziłem tylko wartości proste (jeden rejestr × skala; 479 wartości). Listy wyboru, walidację, maski bitów i wartości z kilku rejestrów sprawdzałem dokładniej tylko na profilu Deye hybrid (odczyt SOC; zapis prądu ładowania, trybu pracy i godziny programu 1).
- Nie wiem, jak zachowa się Twój logger przy dwóch połączeniach, ani jak szybko zwraca odpowiedzi przy pełnym profilu.
- Kod klienta, parser i warstwa encji pochodzą z ha-solarman (licencja MIT) i pysolarman (MIT), a dołączony klient Modbus uModbus ma licencję MPL-2.0 — pliki licencji leżą w `direct/`.

## Testy
- Nowe testy (wszystkie przechodzą; celowe uszkodzenia kodu są wykrywane): statyczny import i brak niezdefiniowanych nazw we wszystkich plikach trybu bezpośredniego i wczytanie 30 profili dla trzech zestawów parametrów; klient na symulatorze (V5 i Modbus TCP, odczyt kodów 3/4, zapis 6/16, wyjątek Modbus, jedno połączenie, numer seryjny z odpowiedzi); urządzenie (odczyt wartości prostych ze wszystkich 30 profili, autodetekcja Deye dla każdego typu, blokada zapisu, odczyt kontrolny, odrzucenie zapisu przez falownik, ponowienie po zgubionej odpowiedzi); koordynator i wszystkie platformy encji; kreator (menu, duplikaty, opcje); wykrywanie encji przez planer; sprzątanie encji; tłumaczenia.
- Regresja planera BMS, fuzz, lint i testy karty w przeglądarce bez zmian w wynikach (jedyne znane odstępstwo: test „historia alarmów” w `diag_prefix_test` — występuje od wcześniej i nie dotyczy tej wersji).

# BMS komp-dec — zmiany w 0.6.8 (z 0.6.7)

Zawiera wszystko z 0.6.7 (dwa wykresy godzinowe „dziś” i „jutro”), 0.6.6, 0.6.5 i wcześniejsze. **Ta wersja nie zmienia wyglądu karty ani planera.** Dotyczy wyłącznie tego, jak integracja podaje przeglądarce adres pliku karty — i co zapisuje w logu, gdy to się nie uda.

## Po co ta zmiana
Po wgraniu 0.6.7 na ekranie telefonu zostawał stary wykres. Na liście zasobów dashboardu (Ustawienia → Pulpity → ⋮ → Zasoby) były dwa wpisy: `/bms_komp_dec/bms-panel.js?v=0.6.1.…` (adres z wersji 0.6.1, który nigdy się nie zaktualizował) oraz stara ręczna kopia `/local/bms-panel-final.js`. Ten sam adres = przeglądarka, aplikacja albo Cloudflare mają prawo podać starą kopię z pamięci podręcznej, a przy dwóch kopiach karty wygrywa ta załadowana jako pierwsza (druga jest po cichu ignorowana — `customElements.define` nie zgłasza błędu).

Integracja miała podmieniać adres na `?v=<wersja>.<data pliku>` przy każdej aktualizacji, ale **gdy się to nie udawało, błąd był zapisywany tylko na poziomie debug — czyli niewidoczny**. Dlaczego aktualizacja adresu nie zadziałała u Ciebie, nie wiem; ta wersja ma to ujawnić w logu, nie naprawia przyczyny na ślepo.

## Co się zmieniło
- **Nieudana aktualizacja lub dodanie zasobu → OSTRZEŻENIE w logu** (wcześniej debug), z obecnym adresem, docelowym adresem i przyczyną (razem ze śladem wyjątku). Tak samo nieudane wczytanie listy zasobów.
- **Druga, stara kopia karty na liście zasobów → OSTRZEŻENIE** z jej adresem i podpowiedzią, gdzie ją usunąć. Rozpoznawane są adresy zawierające `bms-panel` lub `bms_panel` (wielkość liter bez znaczenia) inne niż adres integracji. **Integracja niczego sama nie usuwa** — to Twój wpis.
- **Zasób karty wpisany na liście więcej niż raz → OSTRZEŻENIE**; aktualizowany jest pierwszy wpis.
- Tryb YAML (brak zasobów w storage) → komunikat informacyjny, że karta ładuje się przez `add_extra_js_url`.
- Poprawna aktualizacja → komunikat informacyjny „zaktualizowano zasób … → …”.
- **Uwaga o widoczności logu:** domyślnie Home Assistant pokazuje w logu tylko ostrzeżenia i błędy. Komunikaty informacyjne (udana aktualizacja, tryb YAML) zobaczysz dopiero po dodaniu w `configuration.yaml`: `logger:` → `logs:` → `custom_components.bms_komp_dec: info`. Ostrzeżenia z listy wyżej są widoczne zawsze.

## Co musisz zrobić ręcznie (wersja nie zrobi tego za Ciebie)
1. Ustawienia → Pulpity → ⋮ → Zasoby: **usuń `/local/bms-panel-final.js`**, jeśli nadal tam jest.
2. Pełny restart Home Assistanta (nie samo przeładowanie integracji — przeładowanie nie wczytuje na nowo kodu Pythona ani nie podmienia adresu zasobu).
3. Aplikacja: zamknij ją całkiem i otwórz ponownie; w razie potrzeby Ustawienia aplikacji → Rozwiązywanie problemów → Zresetuj pamięć podręczną interfejsu.
4. Po restarcie wpis na liście zasobów powinien mieć `?v=0.6.8.<liczba>`. Jeśli nie ma — poszukaj w logu linii zawierających „BMS” i przyślij je.

## Testy
- Nowy `test_resources`: 34 sprawdzenia na atrapie kolekcji zasobów — dodanie wpisu, aktualizacja ze starego adresu `?v=0.6.1`, aktualny adres bez zmian, nieudana aktualizacja / utworzenie / wczytanie (ostrzeżenie + ślad wyjątku), niewczytana kolekcja, druga kopia karty (kilka wariantów adresu, obce karty i CSS bez ostrzeżenia, brak automatycznego usuwania), duplikat, `lovelace` jako obiekt lub słownik, tryb YAML, błąd przy odczycie listy, rejestracja od razu (HA działa) i po zdarzeniu startu (HA startuje). Celowe uszkodzenia kodu (wyłączone ostrzeżenia, brak aktualizacji, brak wykrywania kopii, brak `exc_info`, brak wczytania kolekcji, rozróżnianie wielkości liter) są wykrywane.
- **Zweryfikowane tylko na atrapie** zasobów Lovelace napisanej na podstawie kodu Home Assistanta (nie uruchamiałem prawdziwego HA). Nie sprawdziłem, czy w Twojej wersji HA nazwy metod kolekcji zasobów są takie same — jeśli nie, w logu pojawi się ostrzeżenie z przyczyną.

# BMS komp-dec — zmiany w 0.6.7 (z 0.6.6)

Zawiera wszystko z 0.6.6 (wykres godzinowy z linią, zmiana czasu, odporność planera), 0.6.5, 0.6.4 i wcześniejsze. **Po wgraniu zrestartuj Home Assistanta (nowy atrybut sensora), a w przeglądarce odśwież kartę (Ctrl+F5); w aplikacji mobilnej: Ustawienia aplikacji → Rozwiązywanie problemów → Zresetuj pamięć podręczną interfejsu.**

## Dwa wykresy godzinowe: „dziś” i „jutro” (Wykresy)
- **Prognoza godzinowa — dziś** (nowy, nad wykresem jutra):
  - słupki: prognoza zużycia na dziś godzina po godzinie (szczyty ≥ 70% maksimum na bursztynowo);
  - miętowa linia: rzeczywiste zużycie zakończonych godzin; bieżąca godzina oznaczona „teraz”; w godzinach bez pełnego pomiaru (np. restart HA) linia jest przerwana;
  - nagłówek: „Dziś do 15:00: 5.1 kWh (prognoza 4.9) · cały dzień: prognoza 9.2 kWh” — porównanie dotyczy **tych samych godzin**; przy lukach w pomiarze: „Dziś (13 godz. z pomiarem): …”;
  - tabela: Godz. / Prog. / Rzecz. / Różn. (w Wh). „Różn.” porównuje teraz rzeczywiste zużycie z prognozą **na ten sam dzień** (w 0.6.6 porównywało z profilem na jutro).
- **Prognoza godzinowa — jutro:** sama prognoza (słupki + tabela Godz. / Jutro), **bez linii „dziś”** — linia jest tylko na wykresie dzisiejszym.
- Wspólne: równe kroki osi, oś godzin co 1 h (szeroki ekran) lub co 2–3 h (wąski), tabela pod wykresem dobiera układ (24 kolumny → 2 × 12 → 3 × 8) i rozmiar czcionki tak, by nic się nie ucinało; jasny i ciemny motyw. Kolumna etykiet w tabeli i lewy margines wykresu mają 46 px (było 40), żeby zmieściło się „Rzecz.”; etykiety „Prog.” i „Rzecz.” są skrótami — wyjaśnia je legenda.
- **Backend:** nowy atrybut `hourly_forecast_today` w `sensor.bms_load_forecast` = średni profil godzinowy × prognoza „wydana” na dziś (ta sama liczba co pozycja „Dziś” w tabeli prognoz; stała w ciągu dnia). Gdy nie ma wpisu wydanej prognozy, używany jest model bez korekty na żywo.
- **Czego ten wykres nie robi:** słupki dzisiejsze **nie** uwzględniają „tempa dnia” (korekty na podstawie zużycia do tej pory) — to celowe, żeby porównanie z rzeczywistością było uczciwe. Po północy do średniego profilu dochodzi profil z wczoraj, więc kształt słupków „dziś” może się nieznacznie różnić od tego, co wczoraj pokazywał wykres „jutro”.

## Testy
- `hourly_chart_test`: 86 sprawdzeń (w 0.6.6: 77) — oba wykresy na jednej stronie, brak linii na wykresie jutra (sprawdzane na pikselach), niezależność danych dziś/jutro, tabela pod słupkami, luki, śmieci w danych, ponowne rysowanie (zmiana godziny rysuje tylko „dziś”; zmiana szerokości i motywu — oba), brak ucinania komórek 300–1100 px. Cztery nowe celowe uszkodzenia kodu są wykrywane (linia na jutrze, prognoza jutra na wykresie dziś, reset pamięci podręcznej, suma prognozy dla tych samych godzin).
- `test_hourly_today`: 25 sprawdzeń (7 nowych dla `hourly_forecast_today`: suma = prognoza wydana, kształt z profilu, niezależność od prognozy na jutro, zmiana wydanej prognozy, brak profili, JSON).
- **Zweryfikowane tylko w środowisku testowym** (Chromium z atrapą HA), nie w prawdziwym HA ani w aplikacji mobilnej; wygląd z Twoimi danymi i czcionkami telefonu zobaczysz dopiero po wgraniu.

# BMS komp-dec — zmiany w 0.6.6 (z 0.6.5)

Zawiera wszystko z 0.6.5 (Diagnostyka: ładowanie modułów), 0.6.4 (planer: ładowanie na noc), 0.6.3, 0.6.2 i 0.6.1. **Po wgraniu zrestartuj Home Assistanta (zmiany w Pythonie i nowy atrybut sensora), a w przeglądarce odśwież kartę (Ctrl+F5); w aplikacji mobilnej: Ustawienia aplikacji → Rozwiązywanie problemów → Zresetuj pamięć podręczną interfejsu.**

## Wykres „Prognoza godzinowa” (Wykresy → Profil godzinowy jutra) — wersja C z linią „dziś”
- **Słupki:** prognoza zużycia na jutro, godzina po godzinie; godziny szczytu (≥ 70% maksimum) bursztynowe.
- **Linia „dziś”:** rzeczywiste zużycie dziś dla zakończonych godzin, rysowana na słupkach jutra (miętowa, z ciemnym obrysem, czytelna w obu motywach). Bieżąca godzina jest podświetlona i opisana „teraz”. Linia jest **przerwana tam, gdzie nie było pełnego pomiaru** (np. HA był zrestartowany w tej godzinie) — zamiast pokazywać zaniżoną wartość.
- **Czytelność:** oś pionowa ma równe kroki (np. 0,2 / 0,4 / 0,6 / 0,8) zamiast przypadkowych wartości; liczby nad słupkami usunięte (zasłaniały się); oś godzin co 1 h na szerokim ekranie, co 2–3 h na wąskim.
- **Tabela pod wykresem (Wh):** Godz. / Jutro / Dziś / Różn. Na szerokim ekranie 24 kolumny dokładnie pod słupkami. Układ jest dobierany do szerokości i najdłuższej liczby tak, żeby nic się nie ucinało: 24 kolumny → 2 bloki po 12 → 3 bloki po 8. **Na typowym telefonie wychodzą 3 bloki po 8 (nie 2 × 12 jak w makiecie)**, bo wartości czterocyfrowe, jak „+110” lub „1200”, nie mieściły się w 12 kolumnach. Gdy liczby są krótkie, na telefonie jest 2 × 12. Blok bez żadnych danych z dziś nie pokazuje pustych wierszy.
- **Nagłówek:** „Jutro: 9.2 kWh · dziś do 15:00: 5.1 kWh”; przy lukach w pomiarze: „dziś (13 godz. z pomiarem): …”.
- **Uwaga co do „Różn.”:** porównuje rzeczywiste zużycie dziś z **profilem godzinowym prognozy na jutro** (nie z prognozą wydaną na dziś), więc to orientacyjna miara „czy dziś jest podobnie jak zakładam na jutro”.
- Gdy nie ma danych „dziś” (np. tuż po północy), wykres wygląda jak wcześniej — same słupki, bez linii i bez wierszy „Dziś/Różn.”.
- **Backend:** `sensor.bms_load_forecast` ma nowe atrybuty `hourly_today` (24 wartości w kWh; `null` dla godziny bieżącej, przyszłych i tych bez pełnego pomiaru) oraz `hourly_today_hour`. Pokrycie pomiaru (ile sekund każdej godziny faktycznie zmierzono) jest zapisywane razem z akumulatorem; zapis sprzed 0.6.6 nie zna pokrycia, więc przyjmowane są pełne godziny — **pierwszego dnia po aktualizacji godzina, w której HA był restartowany, może wyjść zaniżona**. W dniu jesiennej zmiany czasu godzina 02:00 (występuje dwa razy) pokazywana jest jako średnia z obu.

## Planer i monitor: zmiana czasu (23 / 25 godzin)
- **Objaw potencjalny:** w dni zmiany czasu ceny RCE mają 23 lub 25 wartości zamiast 24, a lista cen przypisana „po kolei” przesuwała godziny o 1 po 02:00 (cena z 03:00 trafiała na 02:00 itd.); kontrola „ceny RCE na jutro” w monitorze i w Diagnostyce uznawała 23 godziny za brak danych.
- **Naprawa:** pozycje na liście są mapowane na godziny lokalne według faktycznych przesunięć UTC (wiosną dzień ma 23 godziny, jesienią 25, a podwójna godzina 02:00 jest uśredniana); kontrola oczekuje 23 / 24 / 25 godzin zależnie od dnia. Najbliższa zmiana czasu: 28 marca 2027; ta z 25 października 2026 już minęła, więc nie miałem jak sprawdzić na prawdziwych danych.

## Planer: odporność na dziwne wartości z czujników
Test losowy (setki scenariuszy: „nan”, „inf”, tekst, ujemne wartości, zerowa pojemność baterii, urwane listy cen, dzień zmiany czasu) znalazł te miejsca:
- stan **„nan” / „inf”** w czujniku (zdarza się w czujnikach szablonowych) przechodził przez `float()` jako liczba: SOC baterii, cena RCE, prognoza PV (suma i godziny), prognoza zużycia, liczby z encji `number` — teraz są ignorowane jak „niedostępne”. Wcześniej NaN w cenie dawał krzywą planu, której nie da się zapisać jako JSON;
- **SOC** spoza 0–100 jest przycinany do tego zakresu (dawniej krzywa mogła pokazywać np. −3,5%);
- **pojemność baterii = 0** (lub błędna) w konfiguracji dawała `ZeroDivisionError` w planerze — teraz używana jest wartość domyślna; to samo dla mocy ładowania/rozładowania i docelowego SOC.
- Część scenariuszy testu losowego jest celowo bardziej złośliwa niż realny HA (np. tekst w polu konfiguracji liczbowej, którego formularz i tak nie przyjmie); realne ryzyko to głównie „nan” z czujników szablonowych i zerowa pojemność.

## Testy
- Nowe: `test_dst` (18 sprawdzeń), `test_hourly_today` (18; w tym sprawdzane przez celowe uszkodzenie kodu: ignorowanie pokrycia, bieżąca godzina widoczna, brak zerowania po północy, stary zapis bez pokrycia, podwójna godzina), `test_fuzz` (w regresji 3 ziarna × 150 scenariuszy; przed poprawkami ok. połowa z 250 scenariuszy kończyła się wyjątkiem, NaN lub SOC poza zakresem, po poprawkach 0 z 1250 w pięciu ziarnach), `hourly_chart_test` (77 sprawdzeń w Chromium: kolor i położenie punktów linii na pikselach, wyrównanie tabeli ze słupkami, luki, śmieci w danych, ponowne rysowanie przy zmianie szerokości, brak ucinania komórek dla szerokości 300–1100 px, jasny/ciemny motyw; 5 celowych uszkodzeń kodu jest wykrywanych).
- **Zweryfikowane tylko w środowisku testowym** (Chromium z atrapą HA i symulowany falownik) — nie w prawdziwym HA, aplikacji mobilnej ani na falowniku. Wykres wygląda tak, jak na zrzutach z testu, ale jego wygląd z Twoimi danymi i czcionkami telefonu zobaczysz dopiero po wgraniu.

# BMS komp-dec — zmiany w 0.6.5 (z 0.6.4)

Zawiera wszystko z 0.6.4 (planer: ładowanie na noc), 0.6.3, 0.6.2 i 0.6.1. **Po wgraniu zrestartuj Home Assistanta, a w przeglądarce odśwież kartę (Ctrl+F5); w aplikacji mobilnej: Ustawienia aplikacji → Rozwiązywanie problemów → Zresetuj pamięć podręczną interfejsu.**

## Diagnostyka: „Ładowanie modułu Diagnostyki…” i brak Trybów
- **Objaw:** w zakładce Diagnostyka widać tylko napis „Ładowanie modułu Diagnostyki…”, a „Tryby i powiadomienia” zniknęły z EMS i nie ma ich w Diagnostyce.
- **Przyczyna (odtworzona w testach):** karta pobiera Diagnostykę z osobnego pliku (`bms-diag.js`). Gdy rdzeń karty nie potrafił ustalić własnego adresu (zdarza się, gdy HA działa długo i przeglądarka ma pełny bufor zasobów), moduł był pobierany pod adresem **bez numeru wersji**. Taki adres jest identyczny w każdej wersji, a HA nie wysyła dla niego nagłówków pamięci podręcznej, więc przeglądarka mogła podać **starą kopię modułu** sprzed aktualizacji. Stary moduł zostawia napis „Ładowanie…” i nie zawiera Trybów, a nowy rdzeń już nie pokazuje ich w EMS — dokładnie ten zestaw objawów. Na Twojej instalacji nie mogłem tego potwierdzić; to najlepiej pasujące wyjaśnienie.
- **Naprawa:**
  - adres modułu zawsze niesie numer wersji karty;
  - rdzeń i moduły mają teraz wbudowany numer wersji i porównują go — przy niezgodności moduł jest pobierany jeszcze raz pod unikalnym adresem (omija pamięć podręczną), bez udziału użytkownika;
  - jeśli i to nie pomoże, zamiast samego napisu „Ładowanie…” pojawia się komunikat z przyczyną, wersjami (karta · integracja · moduł) i przyciskiem „Spróbuj ponownie”;
  - to samo przy wyjątku w otwieraniu Diagnostyki, przy module, który niczego nie narysował, i przy pobieraniu, które wisi dłużej niż 20 s;
  - to samo dotyczy modułu dodatków (plan 24 h, raport, kreator).
- **Wersje widoczne w Diagnostyce:** u dołu ekranu blokady i w trybie instalatora jest linia „Karta X · integracja Y”. Jeśli wersje się różnią (pliki zaktualizowane, ale HA nie zrestartowany), pojawia się ostrzeżenie.
- Tryby i powiadomienia: Diagnostyka → odblokuj hasłem → zakładka „🛡️ Tryby”.

## Testy
- Nowy `stale_module_test` (20 sprawdzeń): stara kopia modułu z pamięci podręcznej (leczona automatycznie), stara kopia wszędzie (komunikat + ponowienie), wyjątek w `_dgOpen`, moduł bez widoku, wiszące pobieranie (20 s), niezgodność wersji integracji i karty, stara kopia modułu dodatków. Trzy celowe uszkodzenia kodu są wykrywane przez te testy.
- Zweryfikowane tylko w środowisku testowym (Chromium z atrapą HA), nie w prawdziwym HA ani w aplikacji mobilnej.

# BMS komp-dec — zmiany w 0.6.4 (z 0.6.3)

Zawiera wszystko z 0.6.3 (ponawianie planu z błędem po 20 s), 0.6.2 i 0.6.1. **Po wgraniu zrestartuj Home Assistanta.** Karta bez zmian (odświeżenie Ctrl+F5 nie jest konieczne).

## Planer: „bateria wystarczy do rana” nie wystarczała
- **Przyczyna:** przy decyzji, czy planować ładowanie z sieci na noc, planer porównywał SOC z godziny 22:00 z SOC potrzebnym o 06:00 — **nie wliczając zużycia domu w nocy**. Przykład: o 22:00 bateria 45%, potrzeba 41% → „pomiń, wystarczy”, a przez noc dom zużywał kolejne kilkanaście procent i bateria schodziła do progu falownika przed świtem. Krzywa planu pokazywała to wprost, a propozycja ładowania mimo to była pomijana.
- **Naprawa:** planer symuluje teraz noc bez ładowania i porównuje przewidywany SOC **na końcu okna nocnego** (o 06:00) z potrzebnym. Ładowanie jest pomijane tylko wtedy, gdy bateria faktycznie dotrwa do rana. Powód pominięcia podaje liczby: „przewidywany SOC X% o 06:00 bez ładowania, potrzeba ok. Y%”.
- Prawdopodobnie to też przyczyna wcześniejszego zgłoszenia „bateria zeszła do progu i nie zaproponowano ładowania z sieci”.
- **Uwaga:** blok ładowania jest planowany pod koniec okna nocnego (np. 05:00–06:00), więc w środku nocy SOC nadal może dojść do progu falownika (25%). Taryfa nocna jest tania, więc to świadomy wybór planera; jeśli wolisz ładować wcześniej i nie schodzić do progu w nocy, to osobna zmiana.

## Testy
- Nowy `test_night_plan`: scenariusze SOC 45/60/50% przy 10–14 kWh/d (dawniej pomijane), siatka 90 kombinacji pora × SOC × zużycie — o 06:00 SOC musi być > próg + 5 pp; kontrola, że przy wysokim SOC ładowanie jest nadal pomijane. Na starym kodzie test oblewa (5 niepowodzeń), na nowym przechodzi.
- `test_floor`: jedna asercja kodowała dawne błędne pomijanie — zmieniona na porównanie celów SOC.
- Zweryfikowane tylko w środowisku testowym (symulowany falownik), nie na prawdziwym HA i falowniku.

# BMS komp-dec — zmiany w 0.6.3 (z 0.6.2)

Zawiera wszystko z 0.6.2 (poprawka cen RCE na jutro, Tryby w Diagnostyce — opis niżej). **Po wgraniu zrestartuj Home Assistanta i odśwież kartę (Ctrl+F5).**

## Plan 24 h: „Plan niedostępny: SOC niedostępny” nie zostaje na 15 minut
- **Przyczyna:** gdy odczyt SOC jest chwilowo niedostępny (typowo po restarcie Home Assistanta, zanim falownik odpowie), plan z błędem był zapamiętywany tak samo jak poprawny — na 15 minut. Karta pokazywała błąd jeszcze długo po powrocie odczytu.
- **Naprawa:** plan z błędem jest ponawiany po 20 s (poprawny plan nadal co 15 min), więc po powrocie SOC plan wraca w ciągu kilkudziesięciu sekund.
- Jeśli komunikat utrzymuje się dłużej niż minutę lub dwie po restarcie, to znaczy, że SOC naprawdę jest niedostępny — sprawdź encję baterii (np. `sensor.inverter_battery`) i połączenie z falownikiem (Solarman).

# BMS komp-dec — zmiany w 0.6.2 (z 0.6.1)

**Po wgraniu zrestartuj Home Assistanta i odśwież kartę (Ctrl+F5).**

## Ceny RCE: fałszywy alarm „brak cen RCE na jutro (0/24 godzin)”
- **Przyczyna:** integracja czytała ceny na jutro tylko z dwóch nazw encji i tylko z atrybutów o nazwach `prices` / `raw_today` / `today` / `forecast`. Karta szuka cen „jutro” szerzej (m.in. `sensor.cena_pradu_jutro`, `sensor.rce_prices_tomorrow`, `sensor.energy_price_tomorrow` i każda encja o nazwie pasującej do wzorca), więc na ekranie ceny były, a plan i monitor ich nie widziały. Dotyczyło to też planowania, nie tylko powiadomienia.
- **Naprawa:** czytnik cen używa teraz tych samych nazw i wzorców co karta, rozpoznaje atrybuty `raw_tomorrow` / `tomorrow` / `prices_tomorrow` / `tomorrow_prices` oraz dowolną listę ze znacznikami czasu, a dla każdego dnia wybiera źródło z największym pokryciem godzin. Lista z encji „jutro” nigdy nie jest brana za ceny „dziś”, a dwa identyczne dni nadal są traktowane jak kopia.
- **Alarm mówi, co zobaczył:** treść powiadomienia podaje odczytane encje i listy w atrybutach (np. `sensor.x: prices[96]`), więc ewentualny kolejny fałszywy alarm da się zdiagnozować bez zgadywania. To samo widać w zakładce EMS → kreator → „Sprawdź konfigurację” (pozycje „Ceny RCE dziś/jutro”).
- **Alarm sam znika**, gdy ceny na jutro pojawią się w komplecie (wcześniej powiadomienie zostawało).

## Tryby i powiadomienia przeniesione do Diagnostyki
- Sekcja (tryb burzowy, urlopowy, powiadomienia, „Auto-stosowanie: tylko podgląd”, czas trybu burzowego, zużycie w trybie urlopowym) jest teraz w **Diagnostyka → 🛡️ Tryby** i zniknęła z zakładki EMS. Wymaga konta administratora i odblokowania hasłem, tak jak reszta Diagnostyki.
- Działa tak samo jak wcześniej, z dodatkami: przyciski „Zapisz” przy polach liczbowych (też klawisz Enter), sprawdzanie zakresu z encji przed zapisem i odświeżanie, które nie kasuje wpisywanej wartości.
- Pasek statusu na stronie głównej nadal pokazuje aktywny tryb burzowy i urlopowy, a kafelek „Rezerwa” — informację o trybie burzowym.

## Drobne
- Po załadowaniu Diagnostyki znika napis „Ładowanie modułu Diagnostyki…”, który zostawał nad panelem (błąd z 0.6.0).

## Czego nie sprawdzono
- Formatu Twojej encji z cenami RCE nie widziałem; poprawka obejmuje typowe formaty (RCE PSE, Nord Pool, listy liczb, osobna encja „jutro”). Jeśli alarm się powtórzy, jego treść wskaże, co dokładnie odczytano.

# BMS komp-dec — zmiany w 0.6.1 (z 0.6.0)

Przegląd bezpieczeństwa i odporności na błędne dane. Zmiany tylko po stronie integracji (karta bez zmian). **Po wgraniu zrestartuj Home Assistanta.**

## Poprawki
- **`bms_komp_dec.monthly_report`:** rok i miesiąc są teraz sprawdzane (rok 2000–2100, miesiąc 1–12, oba albo żadne). Wcześniej miesiąc 13, 0 albo tekst kończyły się surowym wyjątkiem (`IllegalMonthError`, `ValueError`, `TypeError`) zamiast czytelnego komunikatu.
- **`bms_komp_dec.auto_apply_now`:** `dry_run: "false"` podane jako tekst (zdarza się w automatyzacjach i szablonach) było traktowane jako prawda, więc zamiast zastosowania zmian zrobiłby się tylko podgląd. Teraz „false / 0 / off / nie” znaczy fałsz.
- **`bms_komp_dec.watch_write`:** `label`, `expected`, `previous` i `entity_id` mają limit długości (120 / 80 / 80 / 120 znaków), więc wywołanie z gigantycznym tekstem nie rozdmie zapisanego stanu. Lista kontroli nadal trzyma ostatnie 30 pozycji.

## Sprawdzone i bez zmian (testy dodane do regresji)
- Karta nie wykonuje HTML wstrzykniętego w dane z Home Assistanta: nazwy encji, stany, opcje list, atrybuty czujników BMS, komunikaty błędów oraz odpowiedzi usług (kontrola zapisu, zdrowie, raport, magazyn Diagnostyki) zawierały `<img onerror>`, `<svg onload>` i `<script>` — we wszystkich zakładkach, popupach i sekcjach Diagnostyki nic się nie wykonało, a tekst był widoczny jako zwykły tekst.
- Usługi z danymi Diagnostyki i kontroli zapisu są tylko dla administratora; zwykły użytkownik dostaje `Unauthorized`.
- `apply_schedule_times` przyjmuje tylko znane klucze i format `GG:MM`; reszta jest pomijana z komunikatem.
- Magazyn Diagnostyki: lista dozwolonych kluczy i limity rozmiaru (400 KB na wartość, 1,5 MB łącznie).

## Czego to NIE jest (uczciwie)
- **Hasło Diagnostyki w karcie to zabezpieczenie przed przypadkowym kliknięciem, nie zabezpieczenie przed atakiem.** Plik karty jest serwowany przez Home Assistanta bez logowania, a w nim jest skrót hasła — słabe hasło da się odgadnąć offline. Prawdziwą barierą jest konto administratora HA i sprawdzanie uprawnień w usługach.
- Usługi sterujące harmonogramem (`apply_schedule_times`, `auto_apply_now`, `undo_auto_apply`, `get_plan`) mogą wywołać wszyscy zalogowani użytkownicy HA — tak samo jak encje `time.*` / `switch.*`, którymi sterują. Jeśli w domu są konta, którym nie ufasz, ogranicz im dostęp na poziomie HA (konta nie-administratorskie i ukrycie panelu).
- Nadal nie sprawdzono na prawdziwym Home Assistancie i falowniku: dostarczanie powiadomień, prawdziwe uprawnienia użytkowników, rzeczywisty Chart.js i nazwy usług Modbus w Twojej wersji Solarmana.

# BMS komp-dec — zmiany w 0.6.0 (z 0.5.0)

Wydanie „przenośność, bezpieczeństwo i powiadomienia”. **Po wgraniu zrestartuj Home Assistanta i odśwież kartę (Ctrl+F5).**
Wszystko poniżej sprawdzono w testach z atrapami Home Assistanta i przeglądarki (Playwright); nie testowano na prawdziwym falowniku — patrz „Czego nie sprawdzono”.

## Przenośność (działa też u innych niż my)
- **Brak zaszytych nazw encji i wartości falownika.** Encje sterujące (tryb pracy, prąd ładowania, moc eksportu, TOU) są brane z konfiguracji albo wykrywane po prefiksie sąsiednich encji; nazwy opcji select (np. „Export First” / „Selling First”) dobierane z listy opcji encji; wartości przycinane do `min`/`max` encji (mały falownik z limitem 37 A nie dostanie 170 A). Gdy się nie da — czytelny błąd z podpowiedzią („Zmień konfigurację → Wykryj encje ponownie”).
- **Znak mocy baterii** (ładowanie = + czy −) wykrywany automatycznie z zachowania SOC i mocy, z ręcznym nadpisaniem (`number.bms_battery_charge_sign`: 0 = auto, ±1). Strzałki na schemacie i bilanse korzystają z tej samej wartości.
- **Taryfa konfigurowalna:** godziny szczytu (np. `6-13,15-22`, „brak” = taryfa jednostrefowa), weekendy i święta w strefie taniej — w konfiguracji integracji. Planowanie nocne i południowe (okno 13–15) wynika z taryfy, nie z liczb w kodzie.
- **Próg odcięcia falownika** (u Ciebie 25%) odczytywany z falownika; `number.bms_inverter_floor_soc` pozwala go ustawić ręcznie (0 = auto). Po instalacji sprawdź, czy karta pokazuje 25%.
- **Plan nocny uwzględnia doładowanie południowe 13–15** (gdy zestaw 2 jest włączony) — noc nie kupuje energii „na zapas”, którą pokryłoby tanie okno w ciągu dnia.

## Powiadomienia (nowe)
- Powiadomienie w HA (dzwonek) i opcjonalnie na telefon (`notify_service`, np. `notify.mobile_app_telefon`) dla: niskiego SOC przy progu odcięcia, alarmu/błędu falownika (z opisem kodu Fxx), zmiany parametru po zapisie, braku cen RCE na jutro (od 18:00), utraty łączności z falownikiem (10 min). Każde zdarzenie ma własny „cooldown”, a czasy wysyłek przeżywają restart HA. Wyłącznik: `switch.bms_notifications_enabled`.
- **Opisy kodów F dotyczą hybryd niskonapięciowych Deye (SG01LP1 / SG03LP1 / SG04LP3 / SG05LP1).** W innych seriach znaczenia bywają inne (np. HP3: F42, F46, F56) — powiadomienia, baner i Diagnostyka mają o tym zastrzeżenie.

## Kontrola po zapisie parametru — po stronie integracji
- Usługa `bms_komp_dec.watch_write` rejestruje zapis, a integracja sama sprawdza wartość po 1, 3 i 6 min — **także gdy karta jest zamknięta**. Rozbieżność = powiadomienie + wpis w dzienniku + alarm w karcie. Rozpoznaje przepełnienie rejestru U16 (np. −20 W → 65 516 W). Przywrócenie poprzedniej wartości zostaje decyzją użytkownika.
- Diagnostyka zgłasza każdy zapis do tej kontroli; gdy usługa jest niedostępna, działa dotychczasowa kontrola lokalna (przy otwartej karcie) z czytelnym komunikatem.

## Diagnostyka
- **Dziennik zmian, kopie automatyczne, profile i alarmy zapisują się w Home Assistant** (a nie tylko w localStorage przeglądarki): te same dane na każdym urządzeniu, przeżywają czyszczenie danych przeglądarki. Jednorazowa migracja z przeglądarki, dane z HA mają pierwszeństwo, przy błędzie zapisu ostrzeżenie i automatyczna ponowna próba. Usługi `diag_store_*` tylko dla administratora (limity: 400 KB/wartość, 1,5 MB łącznie).
- **Odczyt/zapis rejestrów Modbus naprawiony:** dwie popularne integracje Solarman mają różne nazwy usług i pól (`read_holding_register` + `register` albo `read_holding_registers` + `address`; `write_holding_register` + `value` albo `write_multiple_registers` + `values`; pole `device`). Karta czyta rejestr usług HA i dobiera właściwe; gdy usługa nie zwraca odpowiedzi — mówi o tym zamiast pokazywać puste pole. Zapis walidowany (0–65535).
- Znacznik ⚠ na zakładce także od alarmów z integracji.

## Karta
- **Podział na moduły:** rdzeń (`bms-panel.js`) jest o ponad jedną trzecią mniejszy; Diagnostyka (`bms-diag.js`) i dodatki (`bms-extras.js`) ładują się przy pierwszym użyciu, z parametrem wersji (po aktualizacji nie zostaje stara kopia w pamięci podręcznej) i kontrolą zgodności. Awaria pobrania pokazuje komunikat z przyciskiem „Spróbuj ponownie”, a reszta karty działa.
- **Baner statusu** na górze: alarm falownika (z opisem kodu), dryf parametru po zapisie (6 h), tryb burzowy (do kiedy), tryb urlopowy.
- **EMS → 📈 Plan na najbliższe 24 h:** przewidywany SOC godzina po godzinie z progiem odcięcia, godzinami ładowania z sieci i sprzedaży, szczytem taryfy, paskami cen kupna/sprzedaży, podpowiedzią po najechaniu/dotknięciu i zmianami harmonogramu, które plan zakłada. Przycisk „Przelicz teraz”.
- **EMS → 🛡️ Tryby i powiadomienia:** tryb burzowy (rezerwa 100%, bez sprzedaży, wyłącza się sam po `storm_mode_hours`), tryb urlopowy (stałe zużycie `vacation_load_w`), powiadomienia, **auto-stosowanie tylko jako podgląd** (`auto_apply_dry_run` — liczy i zapisuje w dzienniku, nic nie wysyła do falownika).
- **EMS → 🧭 Kreator instalacji:** sprawdza encje sterujące, ceny RCE, prognozę PV, powiadomienia i pokazuje, co zrobiłby każdy przycisk — bez zapisu do falownika. „Kopiuj raport” do wklejenia znajomemu.
- **Zysk i log → 📅 Raport miesięczny** (bilans z siecią, sprzedaż/zakup, autokonsumpcja, samowystarczalność, bateria, najlepszy/najsłabszy dzień; nawigacja po miesiącach) i **🔋 Zdrowie i sprawność baterii** (sprawność cyklu 7/30/90 dni, trend, szacunek pojemności). Oszczędności i pojemność to **szacunki orientacyjne**, nie pomiary.

## Nowe encje i usługi
- Przełączniki: `notifications_enabled`, `storm_mode`, `vacation_mode`, `auto_apply_dry_run`. Liczby: `storm_mode_hours`, `vacation_load_w`, `inverter_floor_soc`, `battery_charge_sign`. Sensory: `plan_curve`, `battery_health`, `monthly_report`, `monitor_status`.
- Usługi: `watch_write`, `watch_status`, `watch_clear`, `health_check`, `monthly_report`, `get_plan`, `diag_store_get_all`, `diag_store_set`, `diag_store_delete`.

## Czego nie sprawdzono (bez prawdziwego Home Assistanta i falownika)
- Faktycznej dostawy powiadomień (HA, usługa `notify` na telefon) i działania uprawnień administratora na prawdziwych kontach.
- Zachowania prawdziwego falownika po zapisie, wykrywania progu odcięcia i znaku baterii na rzeczywistych danych.
- Wykresu historii na prawdziwej bibliotece Chart.js (w testach atrapa; konfiguracja jest zgodna z API Chart.js 4).
- Nazw usług Modbus dla Twojej wersji integracji Solarman (karta wykrywa je sama; przetestowane na schematach obu integracji z dokumentacji).

# BMS komp-dec — zmiany w 0.4.4

Dokładniejsza prognoza zużycia domu:
- **Typ dnia zamiast samego dnia tygodnia.** Dni robocze i dni wolne (weekendy oraz polskie święta ustawowe, także te w środku tygodnia) mają osobną bazę. Prognoza na poniedziałek po święcie czy na święto w środę liczy się już jak dzień wolny — wcześniej tylko dzień bieżący był rozpoznawany z sensora „workday”. Dla jednakowego typu liczą się też „ten sam dzień tygodnia” i przedział ufności.
- **Szybsza reakcja na zmianę nawyków.** Gdy dwa ostatnie dni tego samego typu odbiegają w tę samą stronę o ponad 25% od wcześniejszej średniej, waga ostatnich dni rośnie (alfa 0,3 → 0,6).
- **Samokorekta obciążenia.** Mediana stosunku (rzeczywiste / model liczony wstecz) z 14 dni, połowa różnicy, ograniczenie ±25% (potrzeba min. 6 dni). Dotyczy prognozy na dziś i przyszłość; wartości wstecz w tabeli są bez korekty. Atrybut `forecast_bias` w `sensor.bms_load_forecast`, widoczny w tabeli „Ostatnie 14 dni”.
- Zmieniono `load_forecast.py`, `sensor.py`, `bms-panel.js` — po wgraniu zrestartuj HA.

# BMS komp-dec — zmiany w 0.4.3

- **Tabela „Ostatnie 14 dni: rzeczywiste vs prognoza”** pod wykresem Porównanie: dzień tygodnia i święta, zużycie rzeczywiste, prognoza wydana dzień wcześniej, różnica w kWh i %, temperatura. Podsumowanie: średni błąd (kWh), obciążenie (czy model zawyża/zaniża) i liczba trafień ±20%. Dni bez zapisanej prognozy pokazują model liczony wstecz (oznaczony gwiazdką, poza podsumowaniem).
- Nowy atrybut `history_14d` w `sensor.bms_load_forecast`.
- Zmieniono `load_forecast.py`, `sensor.py`, `bms-panel.js` — po wgraniu zrestartuj HA.

# BMS komp-dec — zmiany w 0.4.2

- **Prognoza zużycia — realne dane, bez skoków o północy.** Słupek prognozy dla „Wczoraj” i „Dziś” to teraz prognoza wydana dzień wcześniej (ta, którą widać jako „Jutro”), stała w ciągu dnia i po północy. Wcześniej „Dziś” było mieszane z dotychczasowym zużyciem (np. 5,9), a po północy ten sam dzień dostawał prognozę samego modelu (9,6).
- **Tempo dnia:** szacunek na koniec doby (model + zużycie dotychczas) pokazuje pomarańczowa przerywana kreska „≈ X” przy dzisiejszym słupku; legenda pod wykresem uzupełniona. Atrybut `days[].nowcast` w `sensor.bms_load_forecast`.
- Zmieniono `load_forecast.py` i `bms-panel.js` — po wgraniu zrestartuj HA.

# BMS komp-dec — zmiany w 0.4.1

- **Diagnostyka: wykrywanie falownika niezależne od nazw encji.** Zakładka bierze encje przypisane przez HA do integracji Solarman i sama ustala prefiks (np. `inverter`, `deye_sg04`, `mojdeye`). Gdy w HA jest kilka urządzeń Solarman (np. falownik i licznik), wybierany jest ten z największą liczbą ustawień, a lista wykrytych jest w „Zaawansowane”. Prefiks nadal można ustawić ręcznie.
- **Inne falowniki:** parametry spoza słownika Deye dostają nazwę z definicji, grupę dobraną po słowach kluczowych i są traktowane jak ryzykowne (dodatkowe potwierdzenie przy zapisie).
- Zmieniono tylko `bms-panel.js`.

# BMS komp-dec — zmiany w 0.4.0

- **Nowa zakładka 🛠️ Diagnostyka (instalator).** Widoczna tylko dla administratorów HA, dodatkowo za hasłem (odblokowanie na 15 min). Hasło jest blokadą przed przypadkową zmianą, a nie prawdziwym zabezpieczeniem — realną barierą jest konto administratora HA.
  - **Przegląd:** stan falownika na żywo (moce, PV1/PV2, bateria, sieć, temperatury, tryb pracy, alarmy, komunikacja) i wyszukiwarka wszystkich odczytów.
  - **Konfiguracja:** wszystkie parametry falownika (number/select/switch/time/button) wykrywane automatycznie, w sekcjach, z polskimi nazwami i opisami, zakresem z encji, wyszukiwarką. Zapis z oknem „było → będzie”, dodatkowym potwierdzeniem dla parametrów ryzykownych (⚠), weryfikacją odczytem i wpisem do dziennika.
  - **Strefy czasowe:** edytor programów 1–6 (godzina, moc, napięcie, SOC, źródło ładowania) z osią 24 h i podglądem przed zapisem.
  - **Wykresy:** zakresy 1h / 1d / 7d / 30d / 90d / 365d, dowolne serie, osie według jednostek, zestawy gotowe, porównanie z poprzednim okresem, min/średnia/maks., eksport CSV.
  - **Alarmy:** czujniki błędów z opisem kodów Fxx, historia z 30 dni.
  - **Kopie i profile:** eksport/import konfiguracji (JSON), profile (np. zima/lato), automatyczna kopia przed każdą zmianą z przywracaniem.
  - **Dziennik zmian** z przyciskiem „Przywróć”; **Zaawansowane:** prefiks encji, odczyt/zapis rejestrów Modbus (usługi Solarman).
- Pasek zakładek na telefonie przewija się zamiast skracać nazwy do „…”.
- Zmieniono tylko `bms-panel.js`.

# BMS komp-dec — zmiany w 0.3.21 (z 0.3.20)

- **Wykres „Przebieg mocy, SOC i cen”:** nowy, sekwencyjny loader Chart.js — najpierw lokalne pliki z `frontend/vendor/`, a gdy ich nie ma albo są błędne, CDN. Eliminuje wyścig ładowania biblioteki i adaptera dat. Instrukcja pobrania dwóch plików: `frontend/vendor/README.txt` (po wgraniu: restart HA i Ctrl+F5).
- **Pogoda:** animowane ikony (własne SVG: słońce, chmury, deszcz, śnieg, burza, mgła, wiatr, księżyc), wyłączane przy ustawieniu systemowym „ogranicz ruch”. Przy prognozie produkcji dopisane „kWh”.
- **Tryb jasny przygaszony:** tło i karty to teraz złamana biel (`#e4e4e9` / `#f0f0f4`) zamiast czystej bieli, łagodniejszy cień — mniej oślepia.
- **Plan dnia — bateria:** dwa paski „Ładowanie/Rozładowanie baterii” zastąpione jednym: „W baterii teraz” (np. 8,5 kWh · 67%) w skali 0–pojemność; dzienne naładowanie i oddanie jako opis pod paskiem.
- **Plan dnia — moc PV teraz:** nowy pasek z aktualną mocą (kW), białą kreską z prognozą Solcast na bieżącą godzinę i oceną „% prognozy” (zielony ≥90%, pomarańczowy ≥60%, czerwony poniżej). Skala to szczyt prognozy (dziś/jutro).
- Zmieniono `bms-panel.js` i `__init__.py` (rejestracja `/bms_komp_dec/vendor/`).

# BMS komp-dec — zmiany w 0.3.19

- **Telefon: okno z wykresem i danymi po dotknięciu ikony nie jest już ucinane.** Na wąskim ekranie (do 600 px) karta schematu wydłuża się tak, żeby okno mieściło się w całości (wszystkie wejścia PV1–PV4, napięcia, prądy), a po zamknięciu wraca do swojej wysokości. Na komputerze bez zmian.
- Tylko `bms-panel.js`.

# BMS komp-dec — zmiany w 0.3.18

- **„Do rozładowania” i „Do pełnego naładowania”:** podpis dnia liczony z kalendarza (dziś / jutro / pojutrze / dzień tygodnia). Wcześniej każdy dzień poza dzisiejszym był opisany jako „jutro”, np. 31 h 57 min wyświetlało „jutro 05:17” zamiast „pojutrze 05:18”.
- Czas trwania od doby wzwyż w dniach: „1 d 7 h” zamiast „31 h 57 min”.
- Tylko `bms-panel.js`.

# BMS komp-dec — zmiany w 0.3.17

- **Wykresy:** wartości nad słupkami także w „Prognoza godzinowa” i „Produkcja PV” (na wąskim ekranie co druga lub co trzecia godzina i szczyty, żeby się nie nakładały).
- **Legendy** pod wykresami „Porównanie” (zielony = rzeczywiste, niebieski = prognoza, żółty = jutro), „Najbliższe 7 dni” i „Prognoza godzinowa”.
- **Zakładka EMS:** zamiast nazw encji (np. `time.bms_bateria_sprzedaz_start [ok]`) krótkie opisy po polsku, co dane ustawienie robi. Nazwa encji pojawia się tylko, gdy encji brakuje lub jest niedostępna.
- Tylko `bms-panel.js`.

# BMS komp-dec — zmiany w 0.3.16

- **Usunięto własny styl ekranu logowania HA** (middleware, `login.css`, `login.js` i opcja w konfiguracji). Integracja nie dotyka już strony logowania. Wymaga restartu HA.

# BMS komp-dec — zmiany w 0.3.15

- Ekran logowania: „Nie wylogowuj mnie” wyśrodkowane, mniejsze i stonowane, z niebieskim akcentem pola wyboru (nadal działa jak dawniej).

# BMS komp-dec — zmiany w 0.3.14

**Ekran logowania HA: wariant A (słońce za panelami PV), bez karty, „Witaj”**
- Formularz bez „kwadratu”: pola loginu i hasła leżą bezpośrednio na tle.
- Logo HA podmieniane na ilustrację: panel PV ze słońcem. Tytuł „Witaj w domu!” → „Witaj”.
- Ukryte: wybór języka, „Pomoc” i „Zapomniałeś hasła?”. Zostają pola, „Nie wylogowuj mnie”, oko i „Zaloguj się”.
- Mały skrypt (`frontend/login.js`) nie dotyka pól ani haseł, nie łączy się z siecią, a przy jakimkolwiek błędzie nic nie zmienia. Gdy nie znajdzie logo, po 6 s wstawia ilustrację na górze.
- Wyłączanie: Konfiguruj → „Własny styl ekranu logowania…”. Wymaga **restartu HA**.

# BMS komp-dec — zmiany w 0.3.13

**Styl ekranu logowania Home Assistanta pod Centrum Energii** (opcjonalny, domyślnie włączony)
- Do strony `/auth/authorize` dokładany jest wyłącznie blok CSS (`frontend/login.css`): akcent `#0a84ff`, karta i pola jak w karcie BMS, zaokrąglenia, poświata w tle i podpis „Centrum Energii · BMS” u góry. Wersja ciemna i jasna zależy od ustawienia systemu. Układ strony i logo HA zostają oryginalne.
- Działa niezależnie od drogi dostępu (adres lokalny, Cloudflare, Tailscale), bo zmiana jest w samym HA, nie w serwerze pośredniczącym.
- Bez skryptów i bez dotykania formularza. Każdy błąd (brak pliku, inny układ strony, wyjątek) oznacza oddanie oryginalnej strony.
- Wyłączanie: Ustawienia → Urządzenia i usługi → BMS komp-dec → Konfiguruj → odznacz „Własny styl ekranu logowania…”.
- Wymaga **restartu HA** (middleware wpina się przed startem serwera HTTP).

# BMS komp-dec — zmiany w 0.3.12

**Inteligentny harmonogram tłumaczy swoje decyzje**
- Na górze opis danych, na których oparto plan: SOC, wschód/zachód, prognoza PV dziś/jutro, zużycie jutro, ceny RCE (z informacją, gdy jutrzejszych jeszcze nie ma) i ceny G12w, oraz wynik („zmieniam 1, pomijam 4”).
- Pary START/STOP połączone w jedną kartę decyzji: werdykt (Zmieniam / Bez zmian / Pomijam), godziny „było → będzie” i czytelne „Dlaczego tak” / „Dlaczego pomijam” (wcześniej drobny, wyszarzony tekst powtórzony przy START i STOP).
- Jedno pole wyboru na kartę zapisuje obie godziny.
- Rozwijana sekcja „Jak podejmuję decyzje” z zasadami działania; widoczna też przed kliknięciem „Zaproponuj”.
- Tylko `bms-panel.js`.

# BMS komp-dec — zmiany w 0.3.11

- Napięcia, prądy, częstotliwość i temperatura baterii przeniesione z kafelków do okna po najechaniu/kliknięciu — pojawiają się **pod wykresem 24 h** jako lista (np. PV1 312 V · 5,2 A; bateria: napięcie · prąd, temperatura). Kafelki znów pokazują tylko moc. Tylko `bms-panel.js`.

# BMS komp-dec — zmiany w 0.3.10

- **Mini wykres 24 h nie jest już ucinany** — okno wykresu jest układane w granicach karty: pod kafelkiem, a gdy się nie mieści, nad nim albo przy dolnej krawędzi.
- **Dodatkowe parametry przy kafelkach** (z encji falownika ha-solarman, bez ustawień): PV — napięcie i prąd każdego wejścia (PV1, PV2…), dom — napięcie, częstotliwość i prąd, sieć — napięcie, częstotliwość i prąd, bateria — napięcie, prąd i temperatura. Kafelek bez czujnika po prostu nie pokazuje danej linii. Tylko `bms-panel.js`.

# BMS komp-dec — zmiany w 0.3.9

**Inteligentny harmonogram uwzględnia wschód i zachód słońca**
- Wschód/zachód brane z HA (lokalizacja domu). PV poza przedziałem wschód–zachód liczy się jako 0, więc Solcast o zmierzchu/świcie nie wpływa na plan. Gdy HA nie poda słońca, granice wynikają z godzin dodatniej prognozy.
- Stały próg „PV ≥ 1 kWh/h” zastąpiony progiem względnym (3% szczytu prognozy dnia, min. 0,05 kWh). W listopadzie stary próg odrzucał prawie wszystkie godziny, więc blokada PV i koszt alternatywny sprzedaży były liczone błędnie.
- **Sprzedaż z baterii nie zostawi domu bez energii do świtu.** Okno sprzedaży jest skracane, aż SOC po drodze do świtu (pierwszej godziny, w której PV pokrywa dom) nie spadnie poniżej progu. W uzasadnieniu jest godzina świtu i minimalny SOC.
- Ładowanie nocne: o 05:00–05:59 planuje nadchodzącą noc (wcześniej pisało „propozycja pojawi się po południu”). Przy słabej prognozie PV cel obejmuje także drogi szczyt taryfy 6–22, o ile szczyt jest droższy od ładowania nocnego.
- Blokada PV: SOC po blokadzie uwzględnia, że dom jedzie z baterii (wcześniej martwy kod zakładał brak zużycia).

**Poprawka cen RCE „jutro”**
- Gdy encja RCE nie ma znaczników czasu na wpisach, „jutro” było kopią „dziś” (identyczne średnie na zrzucie: 0,925 / 0,925). Teraz taka lista służy tylko do „dziś”, rozpoznawany jest też klucz `dtime`, a identyczne dwa dni są traktowane jako brak cen jutra.

Karta: w nagłówku harmonogramu godziny wschodu i zachodu oraz prognoza PV dziś/jutro.

# BMS komp-dec — zmiany w 0.3.8

- **Mini wykres mocy z ostatnich 24 h** w widoku węzłów: najedź kursorem (lub kliknij/stuknij) w PV, dom, sieć albo baterię. Wykres pokazuje przebieg mocy, energię (kWh), szczyt i średnią; dla sieci import/eksport, dla baterii ładowanie/rozładowanie z przerywaną linią SOC.
- Po kliknięciu wykres zostaje przypięty: przesuwanie kursora/palca po wykresie pokazuje godzinę i moc; zamykanie przez ×, Esc albo kliknięcie obok.
- Dane z historii HA (recorder), pobierane przy pierwszym otwarciu i trzymane 5 min w pamięci karty. Tylko `bms-panel.js`.

# BMS komp-dec — zmiany w 0.3.7

- Gdy integracja nie podaje pojemności baterii (np. nie podmieniono sensor.py), karta pozwala wpisać ją ręcznie (zapamiętywane w przeglądarce) — czasy do pełna i do 20% działają od razu.

# BMS komp-dec — zmiany w 0.3.6

- **Automatyczne wykrywanie encji na podstawie definicji ha-solarman v25.08.16** (30 definicji: Deye, Solis, Sofar, Afore, KSTAR, Anenji, CHINT, Hinen, INVT, SRNE i inne). Dopasowanie po `translation_key` z rejestru encji, więc działa też przy tłumaczonych nazwach i innym prefiksie urządzenia. Przy kilku falownikach wybiera urządzenie z baterią.
- W „Konfiguruj” / „Zmień konfigurację” nowe pole **Wykryj encje ponownie**.
- Uwaga: sterowanie (tryb pracy, prąd ładowania, Time of Use) jest nadal napisane pod Deye — dla innych marek wykrywane są głównie encje pomiarowe.

# BMS komp-dec — zmiany w 0.3.5

- **Rekonfiguracja bez usuwania integracji**: przycisk „Konfiguruj” (opcje) oraz „Zmień konfigurację” (⋮ przy integracji) — zmiana encji, pojemności baterii, mocy, cen i prognoz. Po zapisie integracja przeładowuje się sama.
- Ustawienia z opcji zastępują dane początkowe w całości (wyczyszczone pole = wartość domyślna).

# BMS komp-dec — zmiany w 0.3.4

- Czas do pełnego naładowania i do rozładowania do 20% przeniesiono do „Planu dnia”.
- Gdy bateria akurat się nie ładuje (np. w nocy), czas liczony jest z prognozy PV (Solcast) i prognozy zużycia, a nie pokazuje „nie ładuje się”.
- Osobne paski ładowania i rozładowania baterii w „Planie dnia”.

# BMS komp-dec — zmiany w 0.3.3

- Usunięto „Bilans dnia” i duży kafelek baterii z głównej zakładki.
- Nowe kafelki nad przepływem: czas do pełnego naładowania i czas do rozładowania do 20% (szacunek przy bieżącej mocy; bez ładowania/rozładowania liczony przy aktualnym zużyciu domu).
- Sensor rezerwy SOC udostępnia pojemność baterii (`capacity_kwh`).

# BMS komp-dec — zmiany w 0.3.2

- Główna zakładka: zamiast diagramu Sankeya widok węzłów (PV, dom, sieć, bateria z pierścieniem SOC) z animowanym przepływem; animacja w CSS, więc bez ciągłego przerysowywania.
- Nowa sekcja „Plan dnia”: PV vs prognoza Solcast, zużycie vs prognoza BMS, ładowanie/rozładowanie baterii, eksport/import.
- Wykres historii w kontenerze o stałej wysokości (koniec „rozjeżdżania w dół”).

# BMS komp-dec — zmiany w 0.3.1

## 0.5.0
- **Planer zna rzeczywisty próg odcięcia baterii w falowniku** (wcześniej zakładał 10–15% i liczył na energię, której falownik nie oddaje — dom przechodził na sieć przy ~25%). Próg = większy z „SOC wyłączenia” i SOC aktywnego programu Time of Use (godzina po godzinie), wykrywany po encjach Solarman; nowa encja `number.bms_inverter_floor_soc` (0 = auto) pozwala ustawić go ręcznie. Uwzględniony w: ładowaniu nocnym, sprzedaży z baterii, blokadzie PV, rezerwie dynamicznej.
- Ładowanie nocne celuje w próg odcięcia + potrzeba do świtu + margines (`number.bms_dawn_margin_soc`, domyślnie 10 pkt %) zamiast „rezerwa + 5”.
- Nowa propozycja: **ładowanie dzienne 13–15** w dni robocze G12w (zestaw 2 ładowania z sieci), gdy bateria zeszłaby do progu przed końcem szczytu 15–22; z szacunkiem zysku. Wymaga włączonego przełącznika „Ładowanie z sieci (zestaw 2)” — propozycja o tym informuje.
- Karta: alert „Bateria blisko progu odcięcia” z najbliższym tanim oknem, znacznik progu i dostępna energia (kWh) na pasku baterii.
- Atrybuty sensora rezerwy SOC: `inverter_floor`, `inverter_floor_source`, `usable_kwh`, `cheap_start`, `cheap_end`, `cheap_now`.

## 0.4.9
- Schemat przepływu na telefonie (szerokość < 520 px): przycięte puste marginesy, schemat ok. 20% większy. PC bez zmian.

## 0.4.8
- Schemat przepływu: strzałki sum dziennych baterii zgodne z kierunkiem względem kółka (↓ ładowanie, ↑ rozładowanie); sieć bez zmian (↓ import, ↑ eksport).

## 0.4.7
- Diagnostyka — poprawka po incydencie „Zero Export Power = −20 W” (rejestr jest bez znaku, odczyt wracał jako 65 515 W):
  - zablokowane wartości ujemne (poza kompensacją temperaturową), 0–100 % dla parametrów w %, ostrzeżenia przy nietypowo dużych wartościach i skokach ≥10×; te same reguły dla importu/profili/cofania; zapis rejestru Modbus tylko 0–65535;
  - kontrola odczytu po zapisie po 1, 3 i 6 min — czerwony alarm z przyciskiem „Przywróć poprzednią”, znacznik ⚠ na zakładce, status w dzienniku zmian;
  - komunikat po zapisie nie twierdzi już, że „falownik potwierdził” (HA widzi wartość — resztę sprawdza kontrola);
  - ostrzeżenie w wierszu, gdy odczyt jest poza zakresem encji lub podejrzanie duży;
  - usunięta nieprawdziwa podpowiedź „wartość ujemna = lekki eksport”; Zero Export Power: zalecane 20–100 W (instrukcja Deye);
  - podpowiedzi: ryzyko przy każdym parametrze, 💡 rekomendacje i domyślne wartości z instrukcji Deye SG01LP1 (SOC wyłączenia/restartu/alarmu, prądy baterii, Time of Use, peak shaving), oznaczenie „✓ wg instrukcji” / „opis ogólny”, rozbudowany opis parametrów nierozpoznanych, ściągawka „Co można ustawiać” z uwagami o różnych modelach falowników.

## 0.4.6
- Schemat przepływu mocy: sumy dzienne pod każdym kółkiem (PV, dom, sieć ↓import/↑eksport, bateria ↑ładowanie/↓oddanie, kWh).
- Pasek cen: usunięty kafelek z godziną.

## 0.4.5
- Strona główna: pasek z aktualną ceną kupna i sprzedaży (zł/kWh) i godziną (atrybuty `price_buy`/`price_sell` sensora rezerwy).
- Harmonogram: poprawny powód pominięcia sprzedaży z baterii, gdy do końca szczytu zostaje mniej niż 2 h (wcześniej mylące „Brak pełnych cen RCE"). „Brak cen" tylko przy faktycznym braku, z listą godzin.

## Inteligentny harmonogram (przepisany)
- **Ładowanie z sieci**: SOC liczony na moment startu (symulacja zużycia i PV), cel = tyle, ile dom potrzebuje do rana (dynamiczna rezerwa), okno kończy się o 06:00 przed szczytem; bez „00:00”; przechodzi przez północ.
- **Sprzedaż**: okna tylko w przyszłości i w szczycie G12w, liczba godzin z dostępnej energii i mocy rozładowania, SOC prognozowany na start okna, bramka opłacalności (cena × sprawność − koszt alternatywny ≥ marża), uwzględnienie bilansu 2-dniowego (zakaz arbitrażu) i planowanego ładowania z sieci.
- **Blokada PV**: tylko gdy cena przewyższa średnią cenę godzin PV o marżę i zostanie dość nadwyżki PV na dopełnienie baterii.
- Każda pominięta propozycja ma czytelny powód. Ceny jutra czytane także z atrybutów encji „dziś”.
- Auto-stosowanie akceptuje pary ładowania z sieci przechodzące przez północ.

## Interfejs
- Nowy wygląd „Nordic” z przełącznikiem motywu jasny/ciemny (☀️/🌙 w nagłówku, zapamiętywany w przeglądarce; domyślnie zgodnie z motywem HA).

# BMS komp-dec — zmiany w 0.3.0

## Naprawione błędy
- **Pusty wykres „Historia energii i cen”** — przy `minimal_response` HA podaje czas w polu `lu`; kod go nie czytał (wszystkie punkty = NaN).
- **Profil godzinowy „1/3 dni” w nieskończoność** — akumulator żył tylko w pamięci i każdy restart HA go zerował. Teraz jest zapisywany, a brakujące dni są odtwarzane ze statystyk rekordera.
- **Zapisy na dysk nigdy nie następowały** — `Store.async_delay_save` przesuwa termin przy każdym wywołaniu (a wołaliśmy co kilka sekund). Nowy `ThrottledStore` (taryfa, prognoza, dziennik, księga).
- **Losowy „Błąd konfiguracji” karty** — karta jest teraz rejestrowana także jako zasób dashboardu (ładowany przed renderem), ochrona przed podwójnym wykonaniem skryptu, odporny render (błąd jednej sekcji nie psuje całej karty), czekanie na adapter dat Chart.js.
- **Formularz konfiguracji** — pusty `default=""` w `EntitySelector` blokował zapis; teraz `suggested_value`. Dodane etykiety pól.
- **Nieużywane ustawienia** — `Min SOC do przejścia w auto`, `Min SOC do stopu eksportu PV` oraz `min_sell_margin` nic nie robiły; teraz działają.
- **Bilans 2-dniowy (arbitraż)** — „wczoraj” ginęło po restarcie (snapshot 23:59:30); teraz bieżący zapis dobowy.
- **Propozycje przy nieznanym SOC** liczone były jak dla 0% — teraz zwracają błąd.
- **Ceny RCE w PLN/MWh** są normalizowane do PLN/kWh.
- **Dzienna propozycja** przeniesiona z 14:00 na 16:00 (ceny na jutro nie były jeszcze opublikowane).
- G12w: święta traktowane jak dzień pozaszczytowy.
- Sprzedaż z harmonogramu nie startuje, gdy nie ma odczytu mocy z sieci.

## Nowe funkcje
1. **Reakcja na niskie/ujemne ceny RCE** — wstrzymuje eksport (Zero Export), po powrocie ceny (+histereza 0,02) wznawia sprzedaż.
2. **Sprawdzanie opłacalności** — `cena × sprawność − koszt alternatywny ≥ min. marża`.
3. **Dynamiczna rezerwa SOC** — energia potrzebna domowi do czasu, aż PV pokryje zużycie.
4. **Dziennik decyzji + odczyt zwrotny** — sensor `sensor.bms_decision_log`, weryfikacja komend po 20 s, jedno ponowienie.
5. **Bilans w PLN** — dziś / miesiąc / łącznie, wykres 31 dni.
6. **Auto-stosowanie propozycji** — z limitem przesunięcia, kontrolą par start/stop, wstrzymaniem w trakcie pracy i cofnięciem.
7. **Dni tygodnia + polskie święta** oraz tryb cykliczny harmonogramu.

Wszystkie nowe funkcje automatyczne są domyślnie **wyłączone** (przełączniki w zakładce „💰 Zysk i log”).
Wyjątki włączone domyślnie: dni tygodnia, „święta jak niedziela”, odczyt zwrotny komend.
