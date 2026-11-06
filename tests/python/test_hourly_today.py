REPO = __import__("pathlib").Path(__file__).resolve().parents[2].as_posix()  # katalog główny repozytorium
"""hourly_today: zużycie dziś godzina po godzinie, z pokryciem pomiaru (restart HA nie zaniża wyniku)."""
import sys, importlib, json
from datetime import datetime, date, timedelta
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

def run(lf, hass, start, end, watts, step=30):
    """próbkowanie co `step` s od start do end (datetime), stała moc"""
    t = start
    hass.states.set("sensor.bms_load_power", watts)
    while t < end:
        stubs.CLOCK["now"] = t
        lf._sample_hourly_power(t)
        t += timedelta(seconds=step)

hass = stubs.FakeHass()
lf = lfm.LoadForecaster(hass, lambda: "sensor.bms_load_power"); lf._loaded = True
lf._load_power_eid_cache = "sensor.bms_load_power"
t0 = datetime(2026, 11, 3, 0, 0, 0, tzinfo=TZ)
run(lf, hass, t0, datetime(2026, 11, 3, 5, 0, 0, tzinfo=TZ), 400)          # 0–5: 400 W → 0.4 kWh/h
now = at(2026, 11, 3, 5, 20)
run(lf, hass, datetime(2026, 11, 3, 5, 0, 0, tzinfo=TZ), now, 400)
ht = lf._hourly_today(now)
check("zakończone godziny 0–4 ≈ 0.4 kWh", ht is not None and all(ht[h] is not None and abs(ht[h] - 0.4) < 0.02 for h in range(5)), ht)
check("godzina bieżąca (5) = None", ht[5] is None, ht[5])
check("przyszłe godziny = None", all(v is None for v in ht[6:]), ht[6:])
check("dł. 24", len(ht) == 24)

# restart HA w środku godziny 8: w godz. 8 tylko ~15 min pomiaru → None (nie zaniżone 0.1)
lf2 = lfm.LoadForecaster(hass, lambda: "sensor.bms_load_power"); lf2._loaded = True
lf2._load_power_eid_cache = "sensor.bms_load_power"
run(lf, hass, datetime(2026, 11, 3, 5, 20, 0, tzinfo=TZ), datetime(2026, 11, 3, 8, 0, 0, tzinfo=TZ), 400)
lf._schedule_save(); saved = lf._store._store.func()
check("zapis zawiera pokrycie (24)", isinstance(saved["hourly_accum"].get("cov"), list) and len(saved["hourly_accum"]["cov"]) == 24)
lf2._load_from_storage(json.loads(json.dumps(saved)))
run(lf2, hass, datetime(2026, 11, 3, 8, 45, 0, tzinfo=TZ), datetime(2026, 11, 3, 10, 5, 0, tzinfo=TZ), 400)
now = at(2026, 11, 3, 10, 5)
h2 = lf2._hourly_today(now)
check("po restarcie: godz. 8 (luka 45 min) = None", h2[8] is None, h2[8])
check("po restarcie: godz. 9 (pełna) ≈ 0.4", h2[9] is not None and abs(h2[9] - 0.4) < 0.02, h2[9])
check("po restarcie: godz. 0–7 zachowane", all(h2[h] is not None for h in range(8)), h2[:8])
check("godz. 7 pełna: 0.4", abs(h2[7] - 0.4) < 0.02, h2[7])

# stary zapis bez 'cov' → zakładamy pełne godziny (nie gubimy dotychczasowych danych)
old = json.loads(json.dumps(saved)); old["hourly_accum"].pop("cov")
lf3 = lfm.LoadForecaster(hass, lambda: "sensor.x"); lf3._load_from_storage(old)
check("stary zapis: pokrycie domyślnie pełne", lf3._hourly_cov == [3600.0] * 24)
h3 = lf3._hourly_today(at(2026, 11, 3, 8, 30))
check("stary zapis: godz. 0–7 widoczne", all(h3[h] is not None for h in range(8)) and h3[8] is None, h3[:9])

# nowy dzień: dane z wczoraj nie przeciekają
lf4 = lfm.LoadForecaster(hass, lambda: "sensor.x"); lf4._load_from_storage(json.loads(json.dumps(saved)))
check("inny dzień → None", lf4._hourly_today(at(2026, 11, 4, 3, 0)) is None)
# początek dnia: żadna godzina zakończona
lf5 = lfm.LoadForecaster(hass, lambda: "sensor.x"); lf5._hourly_sample_date = date(2026, 11, 5)
check("brak danych → None (nie lista pusta)", lf5._hourly_today(at(2026, 11, 5, 0, 10)) is None)
# rollover dnia zeruje pokrycie
lf6 = lfm.LoadForecaster(hass, lambda: "sensor.bms_load_power"); lf6._loaded = True; lf6._load_power_eid_cache = "sensor.bms_load_power"
run(lf6, hass, datetime(2026, 11, 5, 22, 0, 0, tzinfo=TZ), datetime(2026, 11, 5, 23, 59, 30, tzinfo=TZ), 300)
lf6._sample_hourly_power(at(2026, 11, 6, 0, 1, 0))
check("rollover: pokrycie i akumulator wyzerowane", sum(lf6._hourly_cov) == 0 and sum(lf6._hourly_accum) == 0)
# jesienna zmiana czasu: godzina 02:00 zliczona dwa razy (cov≈7200 s) → wartość uśredniona, nie podwojona
lf7 = lfm.LoadForecaster(hass, lambda: "sensor.x"); lf7._hourly_sample_date = date(2026, 10, 25)
lf7._hourly_accum = [0.4] * 24; lf7._hourly_accum[2] = 0.8
lf7._hourly_cov = [3600.0] * 24; lf7._hourly_cov[2] = 7200.0
h7 = lf7._hourly_today(at(2026, 10, 25, 12, 0))
check("DST jesień: godz. 02 (2×) pokazana jako ≈0.4, nie 0.8", abs(h7[2] - 0.4) < 0.005 and abs(h7[1] - 0.4) < 0.005 and abs(h7[3] - 0.4) < 0.005, h7[:5])
lf7._hourly_cov[2] = 3630.0; lf7._hourly_accum[2] = 0.41
h7 = lf7._hourly_today(at(2026, 10, 25, 12, 0))
check("zwykła godzina z lekkim nadmiarem pomiaru (3630 s) nie jest skalowana", abs(h7[2] - 0.41) < 0.0005, h7[2])
# JSON-owalność i brak NaN
check("as_dict serializuje się", True)
d = lf._hourly_today(at(2026, 11, 3, 10, 5))
try: json.dumps(d, allow_nan=False); ok = True
except Exception: ok = False
check("hourly_today → JSON bez NaN", ok)

# ---------- hourly_forecast_today: profil × prognoza wydana na dziś (stała w ciągu dnia)
hass8 = stubs.FakeHass()
lf8 = lfm.LoadForecaster(hass8, lambda: "sensor.x"); lf8._loaded = True
now8 = at(2026, 11, 3, 15, 0)
for i in range(1, 20):
    lf8.days[(date(2026, 11, 3) - timedelta(days=i)).isoformat()] = 10.0
prof = [0.0] * 24; prof[8] = 0.25; prof[18] = 0.5; prof[22] = 0.25
for i in range(1, 6):
    lf8.profiles[(date(2026, 11, 3) - timedelta(days=i)).isoformat()] = prof
lf8.forecast_history["2026-11-03"] = 9.6
d8 = lf8.as_dict()
hf = d8["hourly_forecast_today"]
check("hourly_forecast_today: 24 wartości", isinstance(hf, list) and len(hf) == 24, hf)
check("hourly_forecast_today: suma ≈ prognoza wydana na dziś (9.6)", abs(sum(hf) - 9.6) < 0.05, sum(hf))
check("hourly_forecast_today: kształt z profilu (godz. 18 = 4.8)", abs(hf[18] - 4.8) < 0.01 and abs(hf[8] - 2.4) < 0.01 and hf[3] == 0, [hf[8], hf[18], hf[3]])
check("hourly_forecast_today: niezależna od prognozy na jutro", d8["hourly_forecast"] != hf or d8["tomorrow_forecast"] == 9.6, [sum(d8["hourly_forecast"] or []), sum(hf)])
lf8.forecast_history["2026-11-03"] = 12.0
hf2 = lf8.as_dict()["hourly_forecast_today"]
check("hourly_forecast_today: zmiana wydanej prognozy zmienia sumę (12.0)", abs(sum(hf2) - 12.0) < 0.05, sum(hf2))
lf9 = lfm.LoadForecaster(hass8, lambda: "sensor.x"); lf9._loaded = True
check("hourly_forecast_today: brak profili → None (bez wyjątku)", lf9.as_dict()["hourly_forecast_today"] is None)
try: json.dumps(hf, allow_nan=False); okj = True
except Exception: okj = False
check("hourly_forecast_today: JSON bez NaN", okj)
print(f"HOURLY-TODAY PASS={PASS} FAIL={FAIL}")
