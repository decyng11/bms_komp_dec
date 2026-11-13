"""Licznik energii z sieci w baterii: zakaz „ładuj z sieci → sprzedaj” (runtime + plan)."""
import asyncio, sys
from datetime import timedelta, datetime
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import scheduler, const
from homeassistant.util import dt as dt_util


def run(rt, c, S, t, minutes, chg_w, grid_w):
    """Symuluje `minutes` minut pracy: chg_w > 0 ładowanie baterii, grid_w > 0 pobór z sieci."""
    sign = 1 if int(rt.battery_sign()["sign"]) >= 0 else -1
    c.data = dict(c.data or {}); c.data["battery_power"] = chg_w * sign
    S.set(c.config["grid_power"], grid_w)
    for _ in range(minutes * 6):
        t += timedelta(seconds=10)
        rt._track_grid_batt(t)
    return t


async def main():
    hass, c, opt, rt = build(); S = hass.states
    c.data = {"energy_battery_charge_today": 0.0, "energy_pv_today": 30.0}     # bilans 2-dniowy nie blokuje
    t = dt_util.now().replace(microsecond=0)
    rt._track_grid_batt(t)
    check("start: licznik 0, brak blokady", rt.grid_batt_kwh() == 0.0 and rt.sell_block_reason() is None, rt.sell_block_reason())
    t = run(rt, c, S, t, 60, 2500, 2700)             # 1 h ładowania 2,5 kW przy poborze 2,7 kW
    check("ładowanie z sieci 1 h × 2,5 kW → ~2,5 kWh", abs(rt.grid_batt_kwh() - 2.4) < 0.15, rt.grid_batt_kwh())
    S.set(c.config["grid_power"], 0)
    why = rt.sell_block_reason()
    check("sprzedaż zablokowana (energia z sieci w baterii)", bool(why) and "naładowanej z sieci" in why, why)
    try:
        await rt.run_command("sprzedaz_6000w", source="ręcznie")
        blocked = False
    except Exception:
        blocked = True
    check("ręczna sprzedaż też zablokowana", blocked)
    t = run(rt, c, S, t, 60, -3000, -3000)           # sprzedaż/eksport: rozładowanie idzie do sieci
    check("rozładowanie do sieci nie zmniejsza licznika", abs(rt.grid_batt_kwh() - 2.4) < 0.15, rt.grid_batt_kwh())
    t = run(rt, c, S, t, 60, -1000, 0)               # dom zużywa 1 kW z baterii przez 1 h
    check("dom zużył 1 kWh → zostaje ~1,4 kWh, nadal blokada", abs(rt.grid_batt_kwh() - 1.4) < 0.15 and rt.sell_block_reason(), rt.grid_batt_kwh())
    t = run(rt, c, S, t, 90, -1000, 0)
    check("dom zużył resztę → licznik 0, blokada zdjęta", rt.grid_batt_kwh() == 0.0 and rt.sell_block_reason() is None, (rt.grid_batt_kwh(), rt.sell_block_reason()))

    t = run(rt, c, S, t, 120, 3000, 60)              # ładowanie z PV, drobny pobór 60 W (szum)
    check("ładowanie z PV przy poborze 60 W nie nalicza", rt.grid_batt_kwh() == 0.0, rt.grid_batt_kwh())
    t = run(rt, c, S, t, 60, 3000, 1100)             # PV + sieć: 1,1 kW z sieci (−100 W strefy martwej)
    check("ładowanie mieszane: liczy się tylko część z sieci (~1 kWh)", abs(rt.grid_batt_kwh() - 1.0) < 0.1, rt.grid_batt_kwh())

    S.set(c.config["soc"], 5)                         # w baterii jest mniej energii niż wskazuje licznik
    t = run(rt, c, S, t, 1, 0, 0)
    cap = rt.battery_params()["cap"]
    check("licznik nie przekracza energii w baterii (SOC × pojemność)", rt.grid_batt_kwh() <= 0.05 * cap + 1e-6, (rt.grid_batt_kwh(), cap))

    S.set(c.config["soc"], 80)
    t = run(rt, c, S, t, 60, 2500, 2700)
    S.set("number.bms_grid_arbitrage_block_kwh", 0)
    check("tolerancja 0 = zabezpieczenie wyłączone", rt.grid_batt_block() is None)
    S.set("number.bms_grid_arbitrage_block_kwh", 0.5)
    check("stan zapisany (przetrwa restart)", (rt.state.get("grid_batt") or {}).get("kwh", 0) > 1.0)

    # przerwa w danych > 2 min nie nalicza
    before = rt.grid_batt_kwh()
    rt._track_grid_batt(t + timedelta(minutes=30))
    check("przerwa w danych: brak naliczenia", rt.grid_batt_kwh() == before)

    # --- plan: nocne ładowanie z sieci → poranna sprzedaż zablokowana, wieczorna dozwolona, gdy dom zużyje energię
    sched = scheduler.ScheduleOptimizer(hass, c, dict(const.SCHEDULER_DEFAULTS))
    now = datetime(2026, 11, 14, 1, 0, tzinfo=dt_util.now().tzinfo)
    ctx = {"now": now, "grid_batt": 0.0, "tol": 0.5, "grid_hours": {3, 4}, "midday_hours": set(), "grid_kwh": 4.0,
           "load_h": [0.6] * 24, "load_today": None, "pv": [[0.0] * 24, [0.0] * 24]}
    r7 = sched._grid_energy_at(ctx, 7)
    check("plan: o 7:00 po ładowaniu 3–5 zostaje ~2,8 kWh energii z sieci", abs(r7 - 2.8) < 0.05, r7)
    check("plan: poranna sprzedaż zablokowana", bool(sched._grid_energy_blocks_sale(ctx, 7)))
    check("plan: wieczorem (18:00) energia z sieci zużyta → sprzedaż dozwolona", sched._grid_energy_blocks_sale(ctx, 18) is None, sched._grid_energy_at(ctx, 18))
    ctx2 = dict(ctx, grid_hours=set(), grid_kwh=0.0, grid_batt=3.0)
    check("plan: licznik 3 kWh teraz → sprzedaż za 2 h zablokowana", bool(sched._grid_energy_blocks_sale(ctx2, 3)))
    check("plan: tolerancja 0 → bez blokady", sched._grid_energy_blocks_sale(dict(ctx2, tol=0), 3) is None)
    print(f"GRIDBATT PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
