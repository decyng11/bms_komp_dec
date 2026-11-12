"""Jakość propozycji planera: sprzedaż z baterii przy małej produkcji PV, minimalna wielkość/zysk, „bez zmian”."""
import asyncio, sys
import common
sys.path.insert(0, ".")
from common import *   # noqa
from datetime import date, timedelta


def mk(soc=90, now=(2026, 10, 28, 16), load=8.0, price=None):
    hass, c, opt0, rt = build(); S = hass.states
    c.data = {"load_forecast": {"tomorrow_forecast": load}, "energy_battery_charge_today": 0.0, "energy_pv_today": 20.0}
    sched = scheduler.ScheduleOptimizer(hass, c, dict(const.SCHEDULER_DEFAULTS))
    at(*now)
    d0, d1 = date(*now[:3]), date(*now[:3]) + timedelta(days=1)
    pr = price or (lambda h: 300 + (400 if 18 <= h < 21 else 0))
    S.set("sensor.rce_pse_cena", 0.6, {"prices": arr(d0, pr) + arr(d1, lambda h: 300)})
    def solc(d, f): return {"detailedHourly": [{"period_start": f"{d.isoformat()}T{h:02d}:00:00+01:00", "pv_estimate": f(h)} for h in range(24)]}
    S.set("sensor.solcast_pv_forecast_forecast_today", 20, solc(d0, lambda h: 3.0 if 9 <= h < 15 else 0.0))
    S.set("sensor.solcast_pv_forecast_forecast_tomorrow", 18, solc(d1, lambda h: 3.0 if 9 <= h < 15 else 0.0))
    S.set(c.config["soc"], soc)
    return hass, c, sched, rt



class T:
    pass
T.mk = staticmethod(mk)


def setpv(hass, now, f0, f1):
    d0, d1 = date(*now[:3]), date(*now[:3]) + timedelta(days=1)
    def solc(d, f): return {"detailedHourly": [{"period_start": f"{d.isoformat()}T{h:02d}:00:00+01:00", "pv_estimate": f(h)} for h in range(24)]}
    hass.states.set("sensor.solcast_pv_forecast_forecast_today", 5, solc(d0, f0))
    hass.states.set("sensor.solcast_pv_forecast_forecast_tomorrow", 5, solc(d1, f1))


async def main():
    now = (2026, 11, 12, 10)
    price = lambda h: 300 + (500 if 18 <= h < 21 else 0)
    # 1. dużo PV (jutro też) → sprzedaż wieczorna ma sens
    hass, c, sched, rt = T.mk(soc=95, now=now, load=8.0, price=price)
    setpv(hass, now, lambda h: 3.0 if 9 <= h < 15 else 0.0, lambda h: 3.0 if 9 <= h < 15 else 0.0)
    P = (await sched.suggest())["proposals"]
    ok = not P["bateria_sprzedaz_start_2"]["skip"]
    check("dużo PV: sprzedaż wieczorna zaproponowana", ok, P["bateria_sprzedaz_start_2"]["reason"])
    g = P["bateria_sprzedaz_start_2"].get("gain_pln")
    check("sprzedaż ma szacowany zysk w zł", isinstance(g, float) and g >= 0.5 and g == P["bateria_sprzedaz_stop_2"].get("gain_pln"), g)
    # 2. listopad, mała produkcja (PV ~1 kWh/dobę, dom 12 kWh) → sprzedaż bez sensu (koszt odtworzenia z sieci)
    hass, c, sched, rt = T.mk(soc=95, now=now, load=4.0, price=lambda h: 300 + (300 if 18 <= h < 21 else 0))
    setpv(hass, now, lambda h: 0.2 if 10 <= h < 14 else 0.0, lambda h: 0.2 if 10 <= h < 14 else 0.0)
    P = (await sched.suggest())["proposals"]
    p = P["bateria_sprzedaz_start_2"]
    check("mała produkcja: sprzedaż pominięta", p["skip"], p)
    check("mała produkcja: powód wspomina o PV i sieci", "PV odrobi" in p["reason"] and "sieci" in p["reason"], p["reason"])
    # 3. mała produkcja, ale ogromny spread cen → nadal można sprzedać (marża rośnie do 2×, nie blokada)
    hass, c, sched, rt = T.mk(soc=95, now=now, load=4.0, price=lambda h: 300 + (1500 if 18 <= h < 21 else 0))
    setpv(hass, now, lambda h: 0.2 if 10 <= h < 14 else 0.0, lambda h: 0.2 if 10 <= h < 14 else 0.0)
    P = (await sched.suggest())["proposals"]
    check("mała produkcja, spread 1,5 zł: sprzedaż możliwa", not P["bateria_sprzedaz_start_2"]["skip"], P["bateria_sprzedaz_start_2"]["reason"])
    # 4. za mała sprzedaż (SOC tuż nad progiem) → pominięta z powodem „za mała”
    hass, c, sched, rt = T.mk(soc=52, now=now, load=2.0, price=price)
    setpv(hass, now, lambda h: 3.0 if 9 <= h < 15 else 0.0, lambda h: 3.0 if 9 <= h < 15 else 0.0)
    P = (await sched.suggest())["proposals"]
    p = P["bateria_sprzedaz_start_2"]
    check("mała sprzedaż: pominięta albo ≥ 1,5 kWh", p["skip"] or "~" in p["reason"], p["reason"])
    if not p["skip"]:
        import re
        m = re.search(r"sprzedaż ~([\d.]+) kWh", p["reason"])
        check("mała sprzedaż: zaproponowana ilość ≥ 1,5 kWh", m and float(m.group(1)) >= 1.5, p["reason"])
    # 5. _prune: różnica ≤ 15 min = bez zmian
    pr = {"pv_export_start": {"current": "11:00", "proposed": "11:10", "skip": False, "confidence": "high", "reason": "x"},
          "pv_export_stop": {"current": "14:00", "proposed": "14:00", "skip": False, "confidence": "high", "reason": "y"}}
    ctx = {"mode": "normal", "grid_kwh": 5.0, "midday_hours": set(), "grid_hours": set(), "grid_targets": {}}
    sched._prune_proposals(pr, ctx)
    check("prune: różnica 10 min → proponowane = bieżące", pr["pv_export_start"]["proposed"] == "11:00" and pr["pv_export_start"]["reason"].startswith("Bez zmian"), pr)
    pr = {"pv_export_start": {"current": "11:00", "proposed": "12:00", "skip": False, "confidence": "high", "reason": "x"},
          "pv_export_stop": {"current": "14:00", "proposed": "14:00", "skip": False, "confidence": "high", "reason": "y"}}
    sched._prune_proposals(pr, ctx)
    check("prune: różnica 1 h → bez ingerencji", pr["pv_export_start"]["proposed"] == "12:00")
    pr = {"pv_export_start": {"current": "11:00", "proposed": "12:00", "skip": False, "confidence": "low", "reason": "x"},
          "pv_export_stop": {"current": "14:00", "proposed": "15:00", "skip": False, "confidence": "low", "reason": "y"}}
    sched._prune_proposals(pr, ctx)
    check("prune: niska pewność → pominięta", pr["pv_export_start"]["skip"] and pr["pv_export_start"]["proposed"] is None, pr)
    # 6. nocne okno „na styk” (< 0,5 kWh) pomijane
    pr = {"start_grid_charge": {"current": "22:00", "proposed": "05:00", "skip": False, "confidence": "high", "reason": "x"},
          "stop_grid_charge": {"current": "06:00", "proposed": "06:00", "skip": False, "confidence": "high", "reason": "y"}}
    ctx = {"mode": "normal", "grid_kwh": 0.2, "midday_hours": set(), "grid_hours": {5}, "grid_targets": {5: 50}}
    sched._prune_proposals(pr, ctx)
    check("prune: ~0 kWh → okno pominięte", pr["start_grid_charge"]["skip"] and ctx["grid_kwh"] == 0.0 and not ctx["grid_hours"], pr)
    print(f"PROPOSALS PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
