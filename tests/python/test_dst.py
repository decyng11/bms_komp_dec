"""Doby ze zmianą czasu (23 / 25 godzin; 92 / 100 wpisów 15-min): ceny RCE mają trafić w prawdziwe godziny lokalne,
a monitor i health nie mogą zgłaszać „brak cen” dla kompletnej doby wiosennej (23 godziny)."""
import asyncio, sys
from datetime import datetime, timezone, time as dtime
sys.path.insert(0, ".")
from common import *   # noqa
import common
from custom_components.bms_komp_dec import monitor as mon, health

def local_entries(d, step, key="start", valkey="rce_pln", f=lambda i, h: 1000 + i):
    """Wpisy co `step` minut dla CAŁEJ doby lokalnej d, z prawdziwymi przesunięciami (+01:00 / +02:00)."""
    s = datetime.combine(d, dtime.min).replace(tzinfo=TZ).astimezone(timezone.utc)
    e = datetime.combine(d + timedelta(days=1), dtime.min).replace(tzinfo=TZ).astimezone(timezone.utc)
    out, i, t = [], 0, s
    while t < e:
        lt = t.astimezone(TZ)
        out.append({key: lt.isoformat(), valkey: f(i, lt.hour)})
        i += 1; t += timedelta(minutes=step)
    return out

def fresh(now, cfg=None):
    hass, c, opt0, rt = build()
    hass.states._s.pop("sensor.rce_pse_cena", None)
    sched = scheduler.ScheduleOptimizer(hass, c, dict(const.SCHEDULER_DEFAULTS))
    at(*now)
    d0 = date(*now[:3])
    return hass, c, sched, d0, d0 + timedelta(days=1)

def nz(v): return helpers.normalize_price(float(v))
def priced(arr): return sum(1 for v in (arr or []) if isinstance(v, (int, float)))

async def main():
    # --- A. doba wiosenna 2027-03-28 (23 godziny), wpisy ze znacznikami czasu
    for step in (60, 15):
        hass, c, s, d0, d1 = fresh((2027, 3, 27, 20, 12))
        ents = local_entries(d1, step, f=lambda i, h: 400 + h)           # cena = 400 + godzina lokalna
        hass.states.set("sensor.rce_pse_cena", 0.6, {"raw_today": local_entries(d0, step, f=lambda i, h: 300 + h, valkey="value"), "raw_tomorrow": [dict(x, value=x["rce_pln"]) for x in ents]})
        r = s._read_rce_arrays().get(d1.isoformat())
        ok = r and priced(r) == 23 and r[2] is None and all(abs(r[h] - nz(400 + h)) < 1e-9 for h in range(24) if h != 2)
        check(f"A{step}: doba wiosenna ({len(ents)} wpisów): 23 godziny w prawdziwych godzinach lokalnych, 02:00 nie istnieje", ok, r)
        check(f"A{step}: oczekiwana liczba godzin doby wiosennej = 23, zwykłej = 24", s.rce_expected_hours(d1) == 23 and s.rce_expected_hours(d0) == 24, (s.rce_expected_hours(d1), s.rce_expected_hours(d0)))
        rt = rtm.BmsRuntime(hass, c, s); c.runtime = rt
        now = at(2027, 3, 27, 20, 12)
        m = mon.Monitor(rt); await m._rce(now)
        nn = [x for x in hass.services.calls if x[0] == "persistent_notification" and x[1] == "create"]
        check(f"A{step}: kompletna doba wiosenna (23 h) → brak fałszywego alarmu „brak cen RCE”", not nn, [x[2].get("message", "")[:90] for x in nn])
        hc = health.health_check(rt)
        ck = {x["id"]: x for x in hc["checks"]} if isinstance(hc, dict) and "checks" in hc else {}
        check(f"A{step}: health: ceny RCE jutro (doba wiosenna) = ok, nie ostrzeżenie", ck.get("rce_jutro", {}).get("status") == "ok", ck.get("rce_jutro"))
    # --- B. doba jesienna 2026-10-25 (25 godzin)
    for step in (60, 15):
        hass, c, s, d0, d1 = fresh((2026, 10, 24, 20, 12))
        ents = local_entries(d1, step, f=lambda i, h: 400 + h)
        hass.states.set("sensor.rce_pse_cena", 0.6, {"raw_today": local_entries(d0, step, f=lambda i, h: 300 + h, valkey="value"), "raw_tomorrow": [dict(x, value=x["rce_pln"]) for x in ents]})
        r = s._read_rce_arrays().get(d1.isoformat())
        check(f"B{step}: doba jesienna ({len(ents)} wpisów): wszystkie 24 godziny lokalne, powtórzona 02:00 uśredniona", r and priced(r) == 24 and all(abs(r[h] - nz(400 + h)) < 1e-9 for h in range(24)), r)
        check(f"B{step}: oczekiwana liczba godzin doby jesiennej = 24", s.rce_expected_hours(d1) == 24)
    # --- C. listy liczb bez znaczników czasu (np. atrybut „today”): kolejność = prawdziwy czas
    def lst(n): return [1000 + i for i in range(n)]
    hass, c, s, d0, d1 = fresh((2027, 3, 28, 10, 5))                      # „dziś” = doba wiosenna
    hass.states.set("sensor.rce_pse_cena", 0.6, {"today": lst(23)})
    r = s._read_rce_arrays().get(d0.isoformat())
    check("C: 23 liczby w dobie wiosennej → godziny 0,1,3,4…23 (bez 2)", r and r[2] is None and abs(r[1] - nz(1001)) < 1e-9 and abs(r[3] - nz(1002)) < 1e-9 and abs(r[23] - nz(1022)) < 1e-9 and priced(r) == 23, r)
    hass, c, s, d0, d1 = fresh((2027, 3, 28, 10, 5))
    hass.states.set("sensor.rce_pse_cena", 0.6, {"today": lst(92)})
    r = s._read_rce_arrays().get(d0.isoformat())
    exp = lambda h: nz(1000 + (h * 4 if h < 2 else (h - 1) * 4) + 1.5)    # średnia 4 kwadransów
    check("C: 92 kwadranse w dobie wiosennej → właściwe godziny (dawniej 3 wpisy na godzinę, doba urwana)", r and r[2] is None and priced(r) == 23 and all(abs(r[h] - exp(h)) < 1e-9 for h in range(24) if h != 2), r)
    hass, c, s, d0, d1 = fresh((2026, 10, 25, 10, 5))                     # „dziś” = doba jesienna
    hass.states.set("sensor.rce_pse_cena", 0.6, {"today": lst(25)})
    r = s._read_rce_arrays().get(d0.isoformat())
    check("C: 25 liczb w dobie jesiennej → 02:00 = średnia dwóch, dalej bez przesunięcia", r and priced(r) == 24 and abs(r[2] - nz(1002.5)) < 1e-9 and abs(r[3] - nz(1004)) < 1e-9 and abs(r[23] - nz(1024)) < 1e-9, r)
    hass, c, s, d0, d1 = fresh((2026, 10, 25, 10, 5))
    hass.states.set("sensor.rce_pse_cena", 0.6, {"today": lst(100)})
    r = s._read_rce_arrays().get(d0.isoformat())
    check("C: 100 kwadransów w dobie jesiennej → 24 godziny, ostatnia = ostatnie 4 wpisy", r and priced(r) == 24 and abs(r[23] - nz(1000 + 96 + 1.5)) < 1e-9, r)
    hass, c, s, d0, d1 = fresh((2026, 10, 25, 10, 5))
    hass.states.set("sensor.rce_pse_cena", 0.6, {"today": lst(96)})        # dostawca ignoruje zmianę czasu: 96 = 24 × 4
    r = s._read_rce_arrays().get(d0.isoformat())
    check("C: 96 kwadransów w dobie jesiennej (dostawca bez DST) → po staremu 24 × 4", r and priced(r) == 24 and abs(r[5] - nz(1000 + 20 + 1.5)) < 1e-9, r)
    hass, c, s, d0, d1 = fresh((2026, 11, 3, 10, 5))                      # zwykła doba: bez zmian
    hass.states.set("sensor.rce_pse_cena", 0.6, {"today": lst(24)})
    r = s._read_rce_arrays().get(d0.isoformat())
    check("C: zwykła doba, 24 liczby → bez zmian", r and priced(r) == 24 and all(abs(r[h] - nz(1000 + h)) < 1e-9 for h in range(24)), r)
    print(f"DST PASS={common.PASS} FAIL={common.FAIL}")
asyncio.run(main())
