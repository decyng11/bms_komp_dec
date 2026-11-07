REPO = __import__("pathlib").Path(__file__).resolve().parents[2].as_posix()  # katalog główny repozytorium
"""Sumy dzienne zużycia: licznik falownika resetowany po północy (zegar falownika) i niepełne dni nie trafiają do historii."""
import sys, importlib
from datetime import datetime, date, timedelta, timezone
sys.path.insert(0, ".")
import stubs
stubs.install()
sys.path.insert(0, REPO + "")
importlib.import_module("custom_components.bms_komp_dec")
from custom_components.bms_komp_dec import load_forecast as lfm
TZ = stubs.TZ
PASS = FAIL = 0
def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1
    else: FAIL += 1; print("FAIL:", name, extra)
def at(y, m, d, hh, mm=0, ss=0):
    stubs.CLOCK["now"] = datetime(y, m, d, hh, mm, ss, tzinfo=TZ); return stubs.CLOCK["now"]

EID = "sensor.inverter_today_load_consumption"
def mk():
    hass = stubs.FakeHass()
    lf = lfm.LoadForecaster(hass, lambda: EID); lf._loaded = True
    lf._last_weather_fetch = 1e18      # bez pobierania pogody w teście
    return hass, lf
def feed(hass, lf, now, val):
    hass.states.set(EID, val); stubs.CLOCK["now"] = now; lf.update()

# ---- 1. licznik resetuje się o 00:20 (zegar falownika spóźnia się o 20 min): odczyty 00:15–00:20 to jeszcze WCZORAJ
hass, lf = mk()
lf.days["2026-11-03"] = 25.40
feed(hass, lf, at(2026, 11, 4, 0, 5), 25.4)      # 4.11: licznik jeszcze nie zresetowany (wynik 3.11)
feed(hass, lf, at(2026, 11, 4, 0, 18), 25.5)     # ... i dalej rośnie (zużycie 3.11 po północy)
check("stary odczyt po północy nie zostaje wynikiem nowego dnia", "2026-11-04" not in lf.days or lf.days["2026-11-04"] < 5, lf.days)
check("ten odczyt dopisuje się do poprzedniego dnia (kontynuacja jego cyklu)", abs(lf.days["2026-11-03"] - 25.5) < 0.011, lf.days)
feed(hass, lf, at(2026, 11, 4, 0, 40), 0.2)      # reset
feed(hass, lf, at(2026, 11, 4, 12, 0), 14.0)
feed(hass, lf, at(2026, 11, 4, 23, 55), 32.9)
check("po resecie wynik dnia = rzeczywisty (32.9)", abs(lf.days["2026-11-04"] - 32.9) < 0.011, lf.days)
# następnego dnia ten sam scenariusz: realne zużycie 28.0 < wczorajsze 32.9 — dotąd dzień zostawał z 32.9
feed(hass, lf, at(2026, 11, 5, 0, 7), 32.9)
feed(hass, lf, at(2026, 11, 5, 0, 19), 33.0)
feed(hass, lf, at(2026, 11, 5, 0, 42), 0.1)
feed(hass, lf, at(2026, 11, 5, 23, 50), 28.0)
check("5.11: wynik 28.0, nie przepisane 32.9 z poprzedniego dnia", abs(lf.days["2026-11-05"] - 28.0) < 0.011, lf.days["2026-11-05"])
check("4.11 wzrósł tylko o to, co zużyto po północy (33.0)", abs(lf.days["2026-11-04"] - 33.0) < 0.011, lf.days["2026-11-04"])

# ---- 2. licznik resetuje się równo o północy: bez zmian w zachowaniu
hass, lf = mk(); lf.days["2026-11-03"] = 25.40
feed(hass, lf, at(2026, 11, 4, 0, 1), 0.0)
feed(hass, lf, at(2026, 11, 4, 9, 0), 6.0)
feed(hass, lf, at(2026, 11, 4, 23, 59), 26.2)
check("reset o północy: dzień = 26.2", abs(lf.days["2026-11-04"] - 26.2) < 0.011 and abs(lf.days["2026-11-03"] - 25.4) < 0.011, lf.days)

# ---- 3. po restarcie HA o 02:00, gdy licznik jeszcze nie zresetowany: nie przypisujemy wczorajszego wyniku dzisiaj
hass, lf = mk(); lf.days["2026-11-03"] = 25.40
feed(hass, lf, at(2026, 11, 4, 2, 0), 25.4)
check("restart w nocy: stary odczyt nie jest dzisiejszym", "2026-11-04" not in lf.days, lf.days)

# ---- 4. rozpoznawanie podejrzanych dni (dane już zapisane: duplikat wczorajszego wyniku, niepełny dzień)
days = {}
base = date(2026, 10, 24)
vals = [34.2, 39.7, 26.8, 30.0, 25.6, 29.6, 30.4, 28.6, 28.3, 2.5, 25.4, 32.9, 32.9, 25.8]
for i, v in enumerate(vals): days[(base + timedelta(days=i)).isoformat()] = v
S = lfm.suspect_days(days)
check("duplikat: 5.11 (32.9 = 4.11) oznaczony", S.get("2026-11-05") == "duplicate", S)
check("pierwszy z pary (4.11) zostaje", "2026-11-04" not in S, S)
check("niepełny dzień: 2.11 (2.5 kWh przy ok. 28) oznaczony", S.get("2026-11-02") == "partial", S)
check("zwykłe dni nie są oznaczone", set(S) == {"2026-11-05", "2026-11-02"}, S)
# stała historia (np. 8.0 przez 30 dni) to nie przepisane wyniki
const_h = {(base + timedelta(days=i)).isoformat(): 8.0 for i in range(30)}
check("stała historia: brak oznaczeń", lfm.suspect_days(const_h) == {}, lfm.suspect_days(const_h))
# trzy dni z rzędu z wynikiem 32.9 w otoczeniu ok. 28 (dwa kolejne dni „przepisane”) — oba oznaczone, pierwszy zostaje
chain = {(base + timedelta(days=i)).isoformat(): v for i, v in enumerate([28.0, 27.5, 29.0, 32.9, 32.9, 32.9, 28.2, 27.7, 29.3])}
sc = lfm.suspect_days(chain)
check("seria 32.9×3 w otoczeniu ok. 28: drugi i trzeci oznaczone, pierwszy zostaje", set(sc) == {(base + timedelta(days=4)).isoformat(), (base + timedelta(days=5)).isoformat()}, sc)
# za mało sąsiadów → nie oceniamy
check("2 dni historii: brak oznaczeń", lfm.suspect_days({"2026-11-01": 25.0, "2026-11-02": 2.0}) == {})
# prawdziwie niski dzień przy niskim poziomie (dom 6–9 kWh): 4.0 to nie 25%
low = {(base + timedelta(days=i)).isoformat(): v for i, v in enumerate([7.1, 8.4, 6.9, 7.7, 8.0, 7.2, 4.0, 7.5])}
check("niski dzień przy niskiej bazie (4.0 przy ok. 7.5) nie jest oznaczany", lfm.suspect_days(low) == {}, lfm.suspect_days(low))

# ---- 5. oznaczone dni nie wchodzą do modelu, MAPE, korekty
hass, lf = mk(); lf.days = dict(days)
today = date(2026, 11, 7); at(2026, 11, 7, 12)
h = lf._valid_history_before(today)
check("model nie widzi 2.11 ani 5.11", date(2026, 11, 2) not in h and date(2026, 11, 5) not in h, sorted(h))
check("model widzi pozostałe 12 dni", len(h) == 12, len(h))
hist14 = lf.as_dict()["history_14d"]
r = {x["date"]: x for x in hist14}
check("as_dict: 2.11 ma suspect=partial, 5.11 duplicate", r["2026-11-02"].get("suspect") == "partial" and r["2026-11-05"].get("suspect") == "duplicate", {k: v.get("suspect") for k, v in r.items()})
check("as_dict: normalny dzień bez suspect", r["2026-11-03"].get("suspect") is None)
lf.forecast_history = {"2026-11-02": 23.3, "2026-11-03": 24.6}
check("MAPE nie liczy dnia 2.11 (tylko 3.11: |25.4-24.6|/25.4≈3%)", abs(lf._compute_mape() - 3.1) < 0.2, lf._compute_mape())

# ---- 6. backfill z rekordera: cykle licznika (reset po północy), niepełne cykle pomijane
rows = []
def hr(day, h): return datetime(2026, 11, day, h, 0, tzinfo=TZ).astimezone(timezone.utc)
# licznik resetowany o 00:40 czasu lokalnego: wiersz godziny 00 ma max = wynik poprzedniego cyklu
cyc = {3: 25.4, 4: 32.9, 5: 28.0, 6: 25.8}
t = datetime(2026, 11, 2, 12, 0, tzinfo=TZ)          # zaczynamy w środku cyklu 2.11 (niepełny — pominąć)
end = datetime(2026, 11, 6, 22, 0, tzinfo=TZ)        # kończymy w środku cyklu 6.11 (niepełny — pominąć)
def value_at(tt):
    shifted = tt - timedelta(minutes=40)
    k = shifted.day; frac = ((shifted.hour * 60 + shifted.minute) / 1440.0)
    return round({2: 24.0, 3: 25.4, 4: 32.9, 5: 28.0, 6: 25.8}[k] * frac, 2)
while t <= end:
    mx = max(value_at(t + timedelta(minutes=m)) for m in range(0, 60, 5))
    rows.append((t.astimezone(timezone.utc), mx)); t += timedelta(hours=1)
got = lfm.day_totals_from_rows(rows, TZ)
check("backfill: dni 3.11, 4.11, 5.11 z pełnych cykli", set(got) >= {"2026-11-03", "2026-11-04", "2026-11-05"}, got)
check("backfill: wyniki cykli bliskie rzeczywistym (±0.8)", all(abs(got[f"2026-11-0{d}"] - cyc[d]) < 0.8 for d in (3, 4, 5)), got)
check("backfill: brak przepisania wyniku poprzedniego dnia (5.11 ≠ 32.9)", abs(got["2026-11-05"] - 28.0) < 0.8, got)
check("backfill: niepełne cykle (początek 2.11, koniec 6.11) pominięte", "2026-11-02" not in got and "2026-11-06" not in got, got)

# ---- 7. cała ścieżka _async_backfill (rekorder podstawiony): te same dni co z funkcji pomocniczej, bez przepisanego 32.9
import asyncio, types
class _Inst:
    async def async_add_executor_job(self, f, *a): return f(*a)
rec = types.ModuleType("homeassistant.components.recorder"); rec.get_instance = lambda hass: _Inst()
stt = types.ModuleType("homeassistant.components.recorder.statistics")
stt.statistics_during_period = lambda hass, st, en, ids, per, units, types_: {EID: [{"start": r[0], "max": r[1]} for r in rows]}
saved_mods = {k: sys.modules.get(k) for k in (rec.__name__, stt.__name__)}
sys.modules[rec.__name__] = rec; sys.modules[stt.__name__] = stt
try:
    hass, lf = mk(); at(2026, 11, 7, 12)
    asyncio.run(lf._async_backfill())
finally:
    for k, v in saved_mods.items():
        if v is None: sys.modules.pop(k, None)
        else: sys.modules[k] = v
check("_async_backfill: dni 3–5.11 z cykli, 5.11 ≈ 28.0 (nie 32.9)", set(lf.days) == {"2026-11-03", "2026-11-04", "2026-11-05"} and abs(lf.days["2026-11-05"] - 28.0) < 0.8, lf.days)

print(f"DAYTOTALS PASS={PASS} FAIL={FAIL}")
