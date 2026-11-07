"""0.8.8: zmiana czasu (osobno od test_dst.py) — reguły harmonogramu o 02:xx (wiosną nieistniejąca godzina, jesienią powtórzona) i plan w dobach 23/25 h."""
import asyncio, sys
sys.path.insert(0, ".")
from common import *   # noqa
import common
from datetime import date, datetime, timedelta, timezone
from custom_components.bms_komp_dec import runtime as rtm

TZ = stubs.TZ
def L(y, m, d, hh, mm=0, ss=0, fold=0): return datetime(y, m, d, hh, mm, ss, tzinfo=TZ, fold=fold)

def day_hours(d):
    s = datetime(d.year, d.month, d.day, tzinfo=TZ).astimezone(timezone.utc)
    e = datetime(d.year, d.month, d.day, tzinfo=TZ) + timedelta(days=1)
    e = datetime(e.year, e.month, e.day, tzinfo=TZ).astimezone(timezone.utc)
    return [(s + timedelta(hours=i)).astimezone(TZ) for i in range(int(round((e - s).total_seconds() / 3600)))]
def rce(d, f): return [{"start": t.isoformat(), "rce_pln": f(t.hour)} for t in day_hours(d)]
def solc(d, f): return {"detailedHourly": [{"period_start": t.isoformat(), "pv_estimate": f(t.hour)} for t in day_hours(d)]}

async def main():
    # ---------- due_times: które „HH:MM” są teraz na czasie
    check("zwykły dzień: tylko bieżąca minuta", rtm.BmsRuntime.due_times(L(2027, 3, 20, 2, 0)) == {"02:00"})
    d = rtm.BmsRuntime.due_times(L(2027, 3, 28, 3, 0))
    check("po skoku 02→03: cała nieistniejąca godzina 02:00–02:59 + 03:00", len(d) == 61 and "02:00" in d and "02:30" in d and "02:59" in d and "03:00" in d and "01:59" not in d, sorted(d)[:3])
    check("po skoku 03:01 nadal (2 min okno)", "02:30" in rtm.BmsRuntime.due_times(L(2027, 3, 28, 3, 1)))
    check("po skoku 03:05: już tylko bieżąca minuta", rtm.BmsRuntime.due_times(L(2027, 3, 28, 3, 5)) == {"03:05"})
    check("tuż przed skokiem 01:59: tylko bieżąca", rtm.BmsRuntime.due_times(L(2027, 3, 28, 1, 59)) == {"01:59"})
    check("jesienią 02:30 (pierwsze przejście): tylko bieżąca", rtm.BmsRuntime.due_times(L(2026, 10, 25, 2, 30, fold=0)) == {"02:30"})
    check("jesienią po cofnięciu: nic ekstra", rtm.BmsRuntime.due_times(L(2026, 10, 25, 2, 0, fold=1)) == {"02:00"})

    # ---------- reguła o 02:30 w wiosenną zmianę czasu: wykona się po skoku, raz
    def setup():
        hass, c, opt, rt = build(); S = hass.states
        S.set("time.bms_start_grid_charge", "02:30:00"); S.set("switch.bms_ladowanie_z_sieci_1", "on")
        return hass, c, opt, rt
    hass, c, opt, rt = setup()
    stubs.CLOCK["now"] = L(2027, 3, 28, 1, 59)
    res = await rt.process_rules(L(2027, 3, 28, 1, 59))
    check("wiosna 01:59: jeszcze nie", not any(r.get("fired") for r in res["results"]))
    stubs.CLOCK["now"] = L(2027, 3, 28, 3, 0, 10)
    res = await rt.process_rules(L(2027, 3, 28, 3, 0, 10))
    check("wiosna 03:00: reguła z 02:30 wykonana (godzina nie istnieje)", any(r.get("fired") and r.get("time_key") == "start_grid_charge" for r in res["results"]), res)
    n = len(hass.services.calls)
    stubs.CLOCK["now"] = L(2027, 3, 28, 3, 1, 10)
    await rt.process_rules(L(2027, 3, 28, 3, 1, 10))
    check("wiosna 03:01: bez dubla", len(hass.services.calls) == n)

    # ---------- jesień: reguła o 02:30 wykonuje się raz (drugie przejście godziny pomijane)
    hass, c, opt, rt = setup()
    stubs.CLOCK["now"] = L(2026, 10, 25, 2, 30, 5, fold=0)
    res = await rt.process_rules(L(2026, 10, 25, 2, 30, 5, fold=0))
    check("jesień 02:30 (1. przejście): wykonana", any(r.get("fired") for r in res["results"]), res)
    n = len(hass.services.calls)
    rt.fired.clear()          # sama blokada 90 s nie może być powodem pominięcia — ma je zapewnić rozpoznanie powtórzonej godziny
    stubs.CLOCK["now"] = L(2026, 10, 25, 2, 30, 5, fold=1)
    res = await rt.process_rules(L(2026, 10, 25, 2, 30, 5, fold=1))
    check("jesień 02:30 (2. przejście, fold=1): pominięta", not any(r.get("fired") for r in res["results"]) and len(hass.services.calls) == n, res)
    check("fold=1 różni się od fold=0 w tym samym zegarze", L(2026, 10, 25, 2, 30, fold=1).utcoffset() != L(2026, 10, 25, 2, 30, fold=0).utcoffset())
    # test ręczny (dry-run) działa także w powtórzonej godzinie
    stubs.CLOCK["now"] = L(2026, 10, 25, 2, 30, 5, fold=1)
    res = await rt.process_rules(L(2026, 10, 25, 2, 30, 5, fold=1), dry_run=True)
    check("dry-run w powtórzonej godzinie nadal liczy reguły", isinstance(res, dict) and "results" in res)

    # ---------- plan w dobach 23/25 h: bez wyjątków, ceny i PV na właściwych godzinach zegarowych
    async def plan_at(now, soc=50):
        hass, c, opt0, rt = build(); S = hass.states
        c.data = {"load_forecast": {"tomorrow_forecast": 8.0}, "energy_battery_charge_today": 0.0, "energy_pv_today": 5.0}
        sched = scheduler.ScheduleOptimizer(hass, c, dict(const.SCHEDULER_DEFAULTS))
        stubs.CLOCK["now"] = now
        d0 = now.date(); d1 = d0 + timedelta(days=1)
        S.set("sensor.rce_pse_cena", 0.6, {"prices": rce(d0, lambda h: 100 + 10 * h) + rce(d1, lambda h: 101 + 10 * h)})
        S.set("sensor.solcast_pv_forecast_forecast_today", 20, solc(d0, lambda h: float(h) if h < 8 else 0.0))
        S.set("sensor.solcast_pv_forecast_forecast_tomorrow", 18, solc(d1, lambda h: float(h) if h < 8 else 0.0))
        S.set(c.config["soc"], soc)
        return await sched.suggest()
    for now in (L(2027, 3, 27, 20), L(2027, 3, 27, 23), L(2027, 3, 28, 1), L(2027, 3, 28, 3), L(2027, 3, 28, 16),
                L(2026, 10, 24, 20), L(2026, 10, 24, 23), L(2026, 10, 25, 1), L(2026, 10, 25, 3), L(2026, 10, 25, 16)):
        try:
            out = await plan_at(now)
            good = out.get("error") is None and len(out["curve"]["soc"]) >= 20 and all(isinstance(x, (int, float)) and x == x for x in out["curve"]["soc"])
            hhmm = all((p.get("proposed") is None) or (len(p["proposed"]) == 5 and p["proposed"][2] == ":") for p in out["proposals"].values())
        except Exception as err:  # noqa: BLE001
            good = hhmm = False; print("WYJĄTEK", now, repr(err))
        check(f"plan bez błędów: {now:%Y-%m-%d %H:%M}", good and hhmm)
    out = await plan_at(L(2027, 3, 27, 23))
    sell = [None if v is None else round(v * 1000) for v in out["curve"]["sell"][:6]]
    check("wiosna: brak ceny dla nieistniejącej godziny 02:00, reszta na właściwych godzinach", sell == [101, 111, None, 131, 141, 151], sell)
    out = await plan_at(L(2026, 10, 24, 23))
    sell = [None if v is None else round(v * 1000) for v in out["curve"]["sell"][:6]]
    check("jesień (doba 25 h): ceny 00–05 na właściwych godzinach", sell == [101, 111, 121, 131, 141, 151], sell)

    print(f"DSTRULES PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)

asyncio.run(main())
