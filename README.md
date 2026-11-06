# BMS komp-dec — Centrum Energii dla Home Assistant

Integracja Home Assistant do zarządzania domowym magazynem energii z falownikiem hybrydowym Deye (przez ha-solarman albo bezpośrednie połączenie z loggerem), z własną kartą Lovelace „Centrum Energii”.

## Co potrafi

- **Planer 24 h:** ładowanie z sieci w najtańszych godzinach, sprzedaż z baterii w drogich, blokada ładowania z PV przy wysokich cenach; taryfy strefowe (G12w i inne) oraz dynamiczne (Pstryk).
- **Prognozy:** zużycie domu (z podziałem na duże urządzenia), produkcja PV (Solcast albo Forecast.Solar), ceny RCE.
- **Karta „Centrum Energii”:** przepływ energii na żywo, plan, bilans w zł, raport miesięczny, zdrowie baterii, urządzenia (wyszukiwanie liczników kWh w HA, wykresy 1 dzień – 12 miesięcy, koszty, cykle).
- **Powiadomienia z konfiguratorem:** ponad 35 rodzajów, cisza nocna, podsumowania dzienne, tygodniowe i miesięczne.
- **Diagnostyka (za hasłem):** kreator instalacji, parametry falownika, strefy czasowe, alarmy, wykresy serwisowe, kopie ustawień.

## Wymagania

- Home Assistant 2024.11 lub nowszy.
- Falownik Deye (hybrydowy 1- lub 3-fazowy) z loggerem Solarman — przez integrację ha-solarman albo bezpośrednio.
- Opcjonalnie: ceny RCE PSE / Pstryk, prognoza PV (Solcast lub Forecast.Solar), encja pogody.

## Instalacja

### A. Przez HACS (tylko gdy repozytorium jest publiczne)

HACS nie obsługuje prywatnych repozytoriów.

1. HACS → menu ⋮ → **Niestandardowe repozytoria** → wklej adres tego repozytorium, typ **Integracja**.
2. Wyszukaj „BMS komp-dec” → **Pobierz**.
3. Zrestartuj Home Assistant.

### B. Ręcznie (działa też przy repozytorium prywatnym)

1. Na stronie repozytorium wejdź w **Releases** i pobierz `bms_komp_dec.zip` z najnowszego wydania.
2. Rozpakuj zawartość do `/config/custom_components/bms_komp_dec/` (w paczce jest sam folder z plikami integracji).
3. Zrestartuj Home Assistant (pełny restart).

### Pierwsza konfiguracja

1. **Ustawienia → Urządzenia i usługi → Dodaj integrację → BMS komp-dec**.
2. Wybierz **Kreator** — doda falownik (albo użyje encji ha-solarman), poczeka na pierwsze odczyty i dopasuje encje.
3. Zapis do falownika i automatyczne stosowanie są na starcie **wyłączone** — włączasz je sam w konfiguracji.
4. Dodaj kartę: edytuj pulpit → **Dodaj kartę** → „BMS Centrum Energii” (`custom:bms-panel-card`). Zasób karty integracja rejestruje sama.

## Aktualizacja

- HACS: pojawi się powiadomienie o nowej wersji.
- Ręcznie: przed aktualizacją zrób kopię zapasową HA, usuń stary folder `bms_komp_dec`, rozpakuj nowy, pełny restart, w przeglądarce Ctrl+F5 (w aplikacji: wyczyść pamięć podręczną frontendu).

Lista zmian: [CHANGELOG.md](CHANGELOG.md).

## Dla autora: jak wydać nową wersję

1. Zmień wersję w `custom_components/bms_komp_dec/manifest.json` (oraz `VERSION` w `const.py` i `CARD_VERSION` w `frontend/bms-panel.js`, `install.version` w modułach `frontend/bms-*.js` — wszystkie muszą być równe).
2. Uzupełnij `CHANGELOG.md`.
3. `git tag v0.8.3 && git push origin v0.8.3` — akcja **Wydanie** sprawdzi zgodność wersji i doda `bms_komp_dec.zip` do wydania.

## Licencja

Wszelkie prawa zastrzeżone — szczegóły w pliku [LICENSE](LICENSE). Integrację można bezpłatnie zainstalować we własnym Home Assistant do użytku osobistego; kopiowanie, rozpowszechnianie, przerabianie do dalszego udostępniania i użycie komercyjne wymagają zgody autora.

W folderze `custom_components/bms_komp_dec/direct/` jest kod z projektów ha-solarman i pysolarman (licencja MIT) oraz umodbus (Mozilla Public License 2.0) — obowiązują dla niego jego własne licencje, zawarte w plikach `LICENSE-*.txt` w tym folderze.

W folderze `custom_components/bms_komp_dec/frontend/vendor/` są biblioteki Chart.js 4.4.1 i chartjs-adapter-date-fns 3.0.0 (licencja MIT) — dzięki nim wykresy działają bez dostępu przeglądarki do internetu.
