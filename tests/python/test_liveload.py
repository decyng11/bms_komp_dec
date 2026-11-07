"""0.8.7: korekta planu o bieżące zużycie domu (średnia krocząca ~15 min, ograniczona, tylko najbliższe 3 godziny)."""
import asyncio, sys, types
from datetime import datetime, timedelta
sys.path.insert(0, ".")
from common import *   # noqa
import common
from custom_components.bms_komp_dec import load_forecast as lfm

T0 = datetime(2026, 11, 7, 6, 0, tzinfo=stubs.TZ)


def feed(lf, kw, seconds, start, step=10):
    t = start
    for _ in range(int(seconds / step)):
        t += timedelta(seconds=step)
        lf._update_live(kw, step, t)
    return t


async def main():
    hass = stubs.FakeHass()
    lf = lfm.LoadForecaster(hass, lambda: "sensor.x")
    check("średnia: brak danych → None", lf.live_load_kw(T0) is None)
    t = feed(lf, 3.0, 300, T0)
    check("średnia: po 5 min jeszcze None (za krótko)", lf.live_load_kw(t) is None)
    t = feed(lf, 3.0, 600, t)
    v = lf.live_load_kw(t)
    check("średnia: po 15 min stałych 3 kW ≈ 3 kW", v is not None and abs(v - 3.0) < 0.05, v)
    check("średnia: nieświeży odczyt (>5 min) → None", lf.live_load_kw(t + timedelta(minutes=6)) is None)
    # skok 10 s o 10 kW na tle stałych 1 kW prawie nie rusza średniej
    lf2 = lfm.LoadForecaster(hass, lambda: "sensor.x")
    t2 = feed(lf2, 1.0, 1200, T0)
    lf2._update_live(10.0, 10, t2 + timedelta(seconds=10))
    v2 = lf2.live_load_kw(t2 + timedelta(seconds=10))
    check("skok na 10 s (czajnik) nie zmienia średniej o więcej niż 0,2 kW", v2 is not None and abs(v2 - 1.0) < 0.2, v2)
    # dłuższa zmiana (pompa ciepła 20 min × 3 kW) przesuwa średnią w stronę 3 kW
    t3 = feed(lf2, 3.0, 1200, t2 + timedelta(seconds=10))
    v3 = lf2.live_load_kw(t3)
    check("20 min po 3 kW → średnia > 2,3 kW", v3 is not None and v3 > 2.3, v3)
    # przerwa w danych > 5 min → liczymy od nowa (i znów 10 min zanim zacznie działać)
    t4 = t3 + timedelta(minutes=10)
    lf2._update_live(1.0, 10, t4)
    check("po przerwie w danych korekta wyłączona do czasu nowych 10 min", lf2.live_load_kw(t4) is None)

    # ---------- planer: _apply_live_load
    hass, c, opt0, rt = build()
    cfg = dict(const.SCHEDULER_DEFAULTS); cfg.update({"battery_capacity_kwh": 12.6})
    at(2026, 11, 7, 6, 31)
    sched = scheduler.ScheduleOptimizer(hass, c, cfg)
    state = {"live": 3.0}
    c.load_forecast = types.SimpleNamespace(live_load_kw=lambda now: state["live"])
    base = [None] * 6 + [1.0] * 18
    out = sched._apply_live_load(list(base))
    check("zużycie 3 kW wobec 1 kW: godziny 06,07,08 podniesione o 2 / 1,2 / 0,6", [round(out[h], 2) for h in (6, 7, 8)] == [3.0, 2.2, 1.6], out[6:10])
    check("godziny od 09 bez zmian, przeszłość bez zmian", out[9] == 1.0 and out[5] is None and out[23] == 1.0)
    check("opis korekty zapisany", sched._live_load == {"live_kw": 3.0, "expected_kw": 1.0, "delta_kw": 2.0}, sched._live_load)
    state["live"] = 1.1
    out = sched._apply_live_load(list(base))
    check("małe odchylenie (1,1 vs 1,0 kW) — bez korekty", out == base and sched._live_load is None, out[6:9])
    state["live"] = 9.0
    out = sched._apply_live_load(list(base))
    check("bardzo duży pobór: korekta ograniczona do +4 kW", abs(out[6] - 5.0) < 1e-9, out[6])
    state["live"] = 0.0
    out = sched._apply_live_load(list(base))
    check("dom prawie nic nie bierze: obniżenie najwyżej o połowę", abs(out[6] - 0.5) < 1e-9, out[6])
    state["live"] = None
    check("brak świeżego pomiaru → bez korekty", sched._apply_live_load(list(base)) == base)
    state["live"] = 3.0
    hass.states.set("switch.bms_live_load_correction", "off")
    check("przełącznik wyłączony → bez korekty", sched._apply_live_load(list(base)) == base and sched._live_load is None)
    hass.states.set("switch.bms_live_load_correction", "on")
    check("brak wartości na bieżącą godzinę i dalej → bez błędu", sched._apply_live_load([None] * 24) == [None] * 24)
    # godzina 23: korekta nie wychodzi poza dobę
    at(2026, 11, 7, 23, 10)
    b2 = [None] * 23 + [1.0]
    o2 = sched._apply_live_load(list(b2))
    check("23:10: tylko ostatnia godzina doby, bez wyjścia poza listę", len(o2) == 24 and abs(o2[23] - 3.0) < 1e-9, o2[22:])

    # ---------- przez _load_today i założenia planu
    at(2026, 11, 7, 6, 31)
    c.data = {"load_forecast": {"hourly_remaining_today": [None] * 6 + [1.0] * 18}}
    lt = sched._load_today()
    check("_load_today stosuje korektę", lt is not None and abs(lt[6] - 3.0) < 1e-9, lt[5:9] if lt else lt)
    ctx = {"now": stubs.CLOCK["now"], "load_today": lt, "load_h": [0.5] * 24, "pv": [None, None], "pv_kwh": [None, None], "mode": "normal", "load_tomorrow": 7.7, "wear": 0.0, "pv_factor": 1.0}
    asm = sched._assumptions(ctx)
    check("założenia: źródło „tempo dnia + bieżące zużycie” i dane korekty", asm["load_today_source"] == "tempo dnia + bieżące zużycie" and asm["load_live"]["delta_kw"] == 2.0, asm.get("load_today_source"))

    print(f"LIVELOAD PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)

asyncio.run(main())
